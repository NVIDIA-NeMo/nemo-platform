# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NemoJob wrapper for one insights analyst run."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import ClassVar

from nemo_insights_plugin.analyst.run import run_analyst
from nemo_insights_plugin.entities import AnalysisConfigStatus
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.constants import (
    DEFAULT_JOB_STORAGE_PATH,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

REPORT_RESULT_NAME = "analysis-report"
REPORT_FILE_NAME = "analysis-report.txt"


class AnalyzeSpec(BaseModel):
    """Canonical input for one insights analyst run."""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(description="Agent under test.")
    agent_spec: str | None = Field(
        default=None,
        description="Optional markdown spec content for the agent under test.",
    )
    base_url: str | None = Field(
        default=None,
        description="Optional platform base URL. Unset uses the active platform context.",
    )
    insights_output: str | None = Field(
        default=None,
        description="Optional local JSON output path for Insight writes.",
    )
    since: datetime | None = Field(
        default=None,
        description="Optional lower bound for incremental trace/span analysis.",
    )
    update_analysis_config: bool = Field(
        default=True,
        description="Update the matching AnalysisRunStatus with run metadata.",
    )
    inference_api_key_secret_name: str | None = Field(
        default=None,
        description=("Optional platform secret exposed as INFERENCE_API_KEY for the current analyst model path."),
    )


class AnalyzeJob(NemoJob):
    """Run the insights analyst once for a single agent."""

    name: ClassVar[str] = "analyze-job"
    description: ClassVar[str] = "Run the insights analyst once for a single agent."
    container: ClassVar[str] = "cpu-tasks"
    spec_schema: ClassVar[type[BaseModel] | None] = AnalyzeSpec

    @classmethod
    async def compile(
        cls,
        *,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Compile the analyzer run into one CPU task step."""
        del workspace, entity_client, job_name, async_sdk, options
        canonical = _as_analyze_spec(spec)
        environment = [
            EnvironmentVariable(
                name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
                value=DEFAULT_JOB_STORAGE_PATH,
            )
        ]
        if canonical.inference_api_key_secret_name:
            environment.append(
                EnvironmentVariable(
                    name="INFERENCE_API_KEY",
                    from_secret=EnvironmentVariableFromSecret(name=canonical.inference_api_key_secret_name),
                )
            )
        elif inference_api_key := os.environ.get("INFERENCE_API_KEY"):
            # Local smoke-test fallback until FP-202 moves analyst model
            # execution onto platform-registered models/secrets.
            environment.append(EnvironmentVariable(name="INFERENCE_API_KEY", value=inference_api_key))

        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="insights-analyze",
                    executor=CPUExecutionProviderSpec(
                        profile=profile or "default",
                        provider="cpu",
                        container=ContainerSpec(
                            image=get_qualified_image("nmp-cpu-tasks"),
                            entrypoint=["python", "-m"],
                            command=["nemo_insights_plugin.jobs.bridge"],
                        ),
                    ),
                    config=canonical.model_dump(mode="json"),
                    environment=environment,
                )
            ],
        )

    def run(
        self,
        config: dict,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict:
        """Run analysis and persist a small report artifact."""
        spec = AnalyzeSpec.model_validate(config)
        started_at = datetime.now(timezone.utc)
        self._record_analysis_run_status(
            sdk=sdk,
            ctx=ctx,
            spec=spec,
            status=AnalysisConfigStatus.RUNNING,
            last_attempted_at=started_at,
            last_error="",
        )

        try:
            report = asyncio.run(
                run_analyst(
                    agent=spec.agent,
                    agent_spec=spec.agent_spec,
                    workspace=ctx.workspace,
                    base_url=spec.base_url,
                    insights_output=spec.insights_output,
                    since=spec.since,
                )
            )
        except Exception as exc:  # pragma: no cover - exercised by integration paths
            completed_at = datetime.now(timezone.utc)
            self._record_analysis_run_status(
                sdk=sdk,
                ctx=ctx,
                spec=spec,
                status=AnalysisConfigStatus.ERROR,
                last_completed_at=completed_at,
                last_error=str(exc),
            )
            logger.exception("Insights analyst job failed for agent '%s'", spec.agent)
            return {
                "status": "failed",
                "agent": spec.agent,
                "workspace": ctx.workspace,
                "error": str(exc),
            }

        completed_at = datetime.now(timezone.utc)
        artifact = self._save_report(ctx, report)
        self._record_analysis_run_status(
            sdk=sdk,
            ctx=ctx,
            spec=spec,
            status=AnalysisConfigStatus.IDLE,
            last_successful_run_at=started_at,
            last_completed_at=completed_at,
            last_error="",
        )
        return {
            "status": "completed",
            "agent": spec.agent,
            "workspace": ctx.workspace,
            "since": spec.since.isoformat() if spec.since else None,
            "last_successful_run_at": started_at.isoformat(),
            "artifact": artifact.model_dump() if artifact is not None else None,
        }

    def _save_report(self, ctx: JobContext, report: str):
        report_path = ctx.storage.persistent / REPORT_FILE_NAME
        report_path.write_text(report, encoding="utf-8")
        return ctx.results.save(REPORT_RESULT_NAME, report_path)

    def _record_analysis_run_status(
        self,
        *,
        sdk: NeMoPlatform | None,
        ctx: JobContext,
        spec: AnalyzeSpec,
        status: AnalysisConfigStatus,
        last_successful_run_at: datetime | None = None,
        last_attempted_at: datetime | None = None,
        last_completed_at: datetime | None = None,
        last_error: str | None = None,
    ) -> None:
        """Best-effort update of the per-agent run status entity."""
        if sdk is None or not spec.update_analysis_config:
            return
        try:
            sdk.insights.analysis_run_statuses.update(
                workspace=ctx.workspace,
                agent=spec.agent,
                status=status,
                last_successful_run_at=last_successful_run_at,
                last_attempted_at=last_attempted_at,
                last_completed_at=last_completed_at,
                last_submitted_job=ctx.job_id,
                last_error=last_error,
            )
        except Exception:
            logger.exception("Failed to update analysis run status for agent '%s'", spec.agent)


def _as_analyze_spec(spec: BaseModel) -> AnalyzeSpec:
    """Narrow a generic BaseModel to a validated :class:`AnalyzeSpec`."""
    if isinstance(spec, AnalyzeSpec):
        return spec
    return AnalyzeSpec.model_validate(spec.model_dump())
