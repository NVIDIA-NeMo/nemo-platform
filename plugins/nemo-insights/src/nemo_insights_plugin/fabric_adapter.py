# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fabric adapter for running the Insights analyst without persistence side effects."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from nemo_fabric_adapter_contract import models as contract
from nemo_fabric_adapters.common import lifecycle
from nemo_insights_plugin.analyst.run import run_analyst_change_set
from nemo_platform_plugin.nooa_model_client import ConfiguredModelRefs
from nemo_platform_plugin.sdk_provider import get_async_task_sdk


class AnalystAdapterConfigError(ValueError):
    """The Fabric-projected analyst adapter configuration is invalid."""


class InsightsAnalystRuntime:
    """Adapter-owned runtime for one Fabric-managed analyst process."""

    def __init__(self) -> None:
        self._settings: dict[str, Any] = {}
        self._models: dict[str, contract.AgentModelConfig] = {}

    async def start(self, payload: dict[str, Any]) -> None:
        config: contract.AgentConfig = payload["config"]
        self._settings = dict(config.harness.settings if config.harness else {})
        self._models = dict(config.models)

    async def invoke(
        self,
        request: contract.AgentRunRequest,
        context: contract.RuntimeContext,
    ) -> contract.AgentRunResult:
        del context
        try:
            result = await self._run_analysis(request)
        except Exception as error:
            return contract.AgentRunResult(
                status=contract.AgentRunStatus.FAILED,
                output={"response": str(error)},
                error=contract.AgentRunError(
                    code="insights_analyst_failed",
                    message=str(error),
                    retryable=False,
                ),
            )

        return contract.AgentRunResult(
            status=contract.AgentRunStatus.SUCCEEDED,
            output={
                "response": result.summary,
                "analyst_result": result.model_dump(mode="json"),
            },
        )

    async def _run_analysis(self, request: contract.AgentRunRequest):
        target_agent = _string_setting(self._settings, "agent") or _string_setting(self._settings, "target_agent")
        if target_agent is None:
            raise AnalystAdapterConfigError("harness.settings.agent is required for the Insights analyst adapter")

        workspace = (
            _string_setting(self._settings, "workspace")
            or _string_context(request.context, "job_workspace")
            or os.environ.get("NMP_WORKSPACE")
            or "default"
        )
        base_url = (
            _string_setting(self._settings, "base_url")
            or os.environ.get("NMP_BASE_URL")
            or os.environ.get("NEMO_BASE_URL")
        )
        # Every settings read can raise, so resolve them before opening the
        # client: nothing is worth a live SDK handle that no one closes.
        agent_spec = _string_setting(self._settings, "agent_spec")
        since = _datetime_setting(self._settings, "since")
        evaluation_id = _string_setting(self._settings, "evaluation_id")
        enable_observability = bool(self._settings.get("enable_observability", True))
        model_refs = ConfiguredModelRefs(
            default=_default_model_ref(self._settings, self._models),
            fast=_fast_model_ref(self._settings, self._models),
        )
        async with get_async_task_sdk("insights") as client:
            result, _backend = await run_analyst_change_set(
                agent=target_agent,
                agent_spec=agent_spec,
                workspace=workspace,
                base_url=base_url,
                client=client,
                since=since,
                evaluation_id=evaluation_id,
                enable_observability=enable_observability,
                model_refs=model_refs,
            )
        return result

    async def stop(self) -> None:
        self.__init__()


def _string_setting(settings: dict[str, Any], key: str) -> str | None:
    value = settings.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AnalystAdapterConfigError(f"harness.settings.{key} must be a non-empty string")
    return value


def _string_context(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _datetime_setting(settings: dict[str, Any], key: str) -> datetime | None:
    value = settings.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AnalystAdapterConfigError(f"harness.settings.{key} must be an ISO-8601 datetime string")
    return datetime.fromisoformat(value)


def _default_model_ref(
    settings: dict[str, Any],
    models: dict[str, contract.AgentModelConfig],
) -> str:
    configured = _string_setting(settings, "default_model")
    if configured is not None:
        return configured
    model = models.get("default")
    if model is None:
        raise AnalystAdapterConfigError("models.default or harness.settings.default_model is required")
    return model.model


def _fast_model_ref(
    settings: dict[str, Any],
    models: dict[str, contract.AgentModelConfig],
) -> str:
    configured = _string_setting(settings, "fast_model")
    if configured is not None:
        return configured
    model = models.get("fast")
    if model is not None:
        return model.model
    return _default_model_ref(settings, models)


def main() -> None:
    """Serve the persistent local-host lifecycle protocol."""
    lifecycle.serve(InsightsAnalystRuntime, config_loader=contract.AgentConfig.from_mapping)


if __name__ == "__main__":
    main()
