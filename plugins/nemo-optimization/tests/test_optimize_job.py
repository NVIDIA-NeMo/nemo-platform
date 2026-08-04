# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from nemo_optimization.jobs.optimize import OptimizeJob
from nemo_optimization.schemas.optimize import OptimizeSpec
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nemo_platform_plugin.run_dependencies import LocalRunError


FABRIC_AGENT = {
    "schema_version": "fabric.agent/v1alpha1",
    "metadata": {"name": "hermes-optimize-demo"},
}


@pytest.mark.asyncio
async def test_compile_produces_customization_optimize_task() -> None:
    spec = OptimizeSpec(optimize_config="/abs/optimize.yml")
    platform_spec = await OptimizeJob.compile(
        workspace="staging",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    step = next(iter(platform_spec["steps"]))
    assert step["name"] == "optimize"
    assert step["executor"]["command"] == ["python", "-m", "nemo_optimization.tasks.optimize"]
    assert step["config"]["workspace"] == "staging"


@pytest.mark.asyncio
async def test_compile_rejects_relative_optimize_config() -> None:
    spec = OptimizeSpec(optimize_config="./relative.yml")
    with pytest.raises(PlatformJobCompilationError, match="optimize_config must be an absolute path"):
        await OptimizeJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )


def test_run_dispatches_inline_fabric_config(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text(
        yaml.safe_dump(
            {
                "schema_version": "fabric.agent/v1alpha1",
                "metadata": {"name": "inline"},
                "optimizer": {"numeric": {"enabled": True}},
            }
        )
    )

    with patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}) as dispatch:
        result = OptimizeJob().run(
            {"optimize_config": str(optimize_yaml), "workspace": "default"},
            ctx=ctx,
        )

    assert result["status"] == "completed"
    kwargs = dispatch.call_args.kwargs
    assert kwargs["agent_config"] is None
    assert kwargs["optimize_config"]["optimizer"]["numeric"]["enabled"] is True


def test_run_resolves_platform_agent_before_dispatch(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text("optimizer:\n  numeric:\n    enabled: true\n")

    class _StubAgents:
        def get(self, *, name: str, workspace: str) -> dict[str, Any]:
            assert name == "react-agent"
            assert workspace == "default"
            return {"config": FABRIC_AGENT}

    class _StubSDK:
        agents = _StubAgents()

    with patch("nemo_optimization.jobs.optimize.OptimizeRouter.dispatch", return_value={"status": "completed"}) as dispatch:
        OptimizeJob().run(
            {
                "optimize_config": str(optimize_yaml),
                "workspace": "default",
                "agent": "react-agent",
            },
            ctx=ctx,
            sdk=_StubSDK(),  # type: ignore[arg-type]
        )

    assert dispatch.call_args.kwargs["agent_config"] == FABRIC_AGENT


def test_run_rejects_endpoint_agent(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text("optimizer:\n  numeric:\n    enabled: true\n")

    with pytest.raises(LocalRunError, match="Endpoint URL optimize mode has been removed"):
        OptimizeJob().run(
            {
                "optimize_config": str(optimize_yaml),
                "workspace": "default",
                "agent": "http://localhost:8080",
            },
            ctx=ctx,
        )
