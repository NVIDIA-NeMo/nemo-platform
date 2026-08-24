# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OptimizeJob — Agents numeric HPO (``nemo agents optimize``).

Implementation lives in ``nemo_optimization``; registration and HTTP mounting
are owned by the agents plugin (``agents.optimize``).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, ClassVar

import yaml
from nemo_platform_plugin.client.client import NemoClient
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from pydantic import BaseModel

from nemo_optimization.agents import resolve_agent_config
from nemo_optimization.preflight import preflight_validate_llm_models
from nemo_optimization.router import OptimizeRouter
from nemo_optimization.schemas.optimize import OptimizeSpec

logger = logging.getLogger(__name__)


class OptimizeJob(NemoJob):
    """Run a Fabric-native numeric optimize study via the Agents optimize job."""

    name: ClassVar[str] = "optimize"
    description: ClassVar[str] = "Optimize a Fabric agent workflow (numeric HPO)."
    container: ClassVar[str] = "cpu-tasks"
    job_collection_path: ClassVar[str | None] = None
    spec_schema: ClassVar[type[BaseModel]] = OptimizeSpec

    @classmethod
    async def compile(  # type: ignore[override]
        cls,
        *,
        workspace: str,
        spec: OptimizeSpec,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        from nemo_platform_plugin.jobs.api_factory import (
            EnvironmentVariable,
            PlatformJobStep,
            SubprocessExecutionProviderSpec,
        )
        from nemo_platform_plugin.jobs.constants import (
            DEFAULT_JOB_STORAGE_PATH,
            PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
        )

        if not Path(spec.optimize_config).is_absolute():
            raise PlatformJobCompilationError("optimize_config must be an absolute path.")

        spec_dict = spec.model_dump(mode="json")
        spec_dict["workspace"] = workspace

        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="optimize",
                    executor=SubprocessExecutionProviderSpec(
                        provider="subprocess",
                        command=["python", "-m", "nemo_optimization.tasks.optimize"],
                    ),
                    config=spec_dict,
                    environment=[
                        EnvironmentVariable(
                            name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
                            value=DEFAULT_JOB_STORAGE_PATH,
                        ),
                    ],
                ),
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: NemoClient | None = None) -> dict:
        spec = OptimizeSpec.model_validate(config)
        optimize_config = _load_yaml(Path(spec.optimize_config))
        agent_config = resolve_agent_config(spec.agent, workspace=spec.workspace, sdk=sdk)
        preflight_validate_llm_models(
            optimize_config,
            workspace=spec.workspace,
            sdk=sdk,
            agent_config=agent_config,
        )
        logger.info("Dispatching agents optimize study via OptimizeRouter")
        return OptimizeRouter.dispatch(
            agent_config=agent_config,
            optimize_config=optimize_config,
            ctx=ctx,
            sdk=sdk,
        )


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"optimize config must be a mapping: {path}")
    return _expand_env(raw)


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value
