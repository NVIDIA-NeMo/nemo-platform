# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``OptimizeAgentJob`` local runner behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import yaml
from nemo_agents_plugin.jobs.optimize_agent import OptimizeAgentJob, OptimizeAgentSpec
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.refs import FilesetRef


def test_run_repoints_outputs_to_persistent_results(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text(
        """
llms:
  llm:
    _type: openai
    model_name: test-model
eval:
  general:
    output_dir: eval/calculator
optimizer:
  output_path: optimizer_results/calculator
""".strip()
    )

    captured: dict[str, Any] = {}

    def _fake_run(cmd: list[str], *, check: bool, cwd: Path) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["check"] = check
        captured["cwd"] = cwd
        captured["injected_config"] = yaml.safe_load((cwd / cmd[3]).read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(cmd, 0)

    with patch("nemo_agents_plugin.jobs.optimize_agent.subprocess.run", side_effect=_fake_run):
        result = OptimizeAgentJob().run({"optimize_config": str(optimize_yaml), "workspace": "default"}, ctx=ctx)

    assert result == {"status": "completed", "returncode": 0}
    assert captured["check"] is True
    assert captured["cwd"] == optimize_yaml.parent
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:3] == ["nat", "optimize", "--config_file"]
    assert str(cmd[3]).startswith(".injected-optimize-")
    assert cmd[4:] == []

    injected_config = cast(dict[str, Any], captured["injected_config"])
    assert injected_config["eval"]["general"]["output_dir"] == str(
        ctx.storage.persistent / "results" / "eval" / "calculator"
    )
    assert injected_config["optimizer"]["output_path"] == str(
        ctx.storage.persistent / "results" / "optimizer_results" / "calculator"
    )


_MINIMAL_OPTIMIZE_YAML = """
llms:
  llm:
    _type: openai
    model_name: test-model
eval:
  general:
    output_dir: eval/calculator
optimizer:
  output_path: optimizer_results/calculator
""".strip()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("optimize_config_fileset", ""),
        ("optimize_config_fileset", "workspace/"),
        ("output", ""),
        ("output", "workspace/"),
    ],
)
def test_spec_rejects_invalid_fileset_refs(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="invalid entity reference"):
        OptimizeAgentSpec.model_validate({"optimize_config": "/tmp/optimize.yml", field: value})


def test_spec_allows_local_output_path() -> None:
    spec = OptimizeAgentSpec.model_validate({"optimize_config": "/tmp/optimize.yml", "output": "./results"})
    assert str(spec.output) == "./results"


@pytest.mark.asyncio
async def test_compile_requires_absolute_without_fileset() -> None:
    spec = OptimizeAgentSpec(optimize_config="relative.yml", workspace="default")
    with pytest.raises(Exception, match="absolute"):
        await OptimizeAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )


@pytest.mark.asyncio
async def test_compile_allows_relative_config_with_fileset() -> None:
    spec = OptimizeAgentSpec(
        optimize_config="optimize.yml",
        optimize_config_fileset=FilesetRef("nemo-agent-optimize-calc"),
        workspace="default",
    )
    platform_spec = await OptimizeAgentJob.compile(
        workspace="default",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )
    config = next(iter(platform_spec["steps"]))["config"]
    assert config["optimize_config"] == "optimize.yml"
    assert config["optimize_config_fileset"] == "nemo-agent-optimize-calc"


@pytest.mark.asyncio
async def test_compile_rejects_absolute_config_with_fileset() -> None:
    spec = OptimizeAgentSpec(
        optimize_config="/abs/optimize.yml",
        optimize_config_fileset=FilesetRef("nemo-agent-optimize-calc"),
        workspace="default",
    )
    with pytest.raises(ValueError, match="relative"):
        await OptimizeAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )


def test_run_stages_config_from_fileset(tmp_path: Path, ctx: JobContext) -> None:
    sdk = MagicMock()

    def _fake_download(local_path: str, fileset: str, workspace: str) -> None:
        Path(local_path, "optimize.yml").write_text(_MINIMAL_OPTIMIZE_YAML)

    sdk.files.download.side_effect = _fake_download

    captured: dict[str, Any] = {}

    def _fake_run(cmd: list[str], *, check: bool, cwd: Path) -> subprocess.CompletedProcess[str]:
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0)

    with (
        patch("nemo_agents_plugin.jobs.optimize_agent.subprocess.run", side_effect=_fake_run),
        patch("nemo_agents_plugin.jobs.optimize_agent.preflight_validate_llm_models"),
    ):
        result = OptimizeAgentJob().run(
            {
                "optimize_config": "optimize.yml",
                "optimize_config_fileset": "nemo-agent-optimize-calc",
                "workspace": "default",
            },
            ctx=ctx,
            sdk=sdk,
        )

    assert result == {"status": "completed", "returncode": 0}
    sdk.files.download.assert_called_once()
    # nat optimize ran with cwd inside the downloaded fileset tempdir, not the source tree.
    assert str(captured["cwd"]).startswith(str(ctx.storage.ephemeral))


def test_run_uploads_output_to_fileset_on_success(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text(_MINIMAL_OPTIMIZE_YAML)

    sdk = MagicMock()
    sdk.files.upload.return_value = MagicMock(name="fake-fileset")

    with (
        patch(
            "nemo_agents_plugin.jobs.optimize_agent.subprocess.run",
            side_effect=lambda cmd, *, check, cwd: subprocess.CompletedProcess(cmd, 0),
        ),
        patch("nemo_agents_plugin.jobs.optimize_agent.preflight_validate_llm_models"),
    ):
        result = OptimizeAgentJob().run(
            {"optimize_config": str(optimize_yaml), "output": "optimizer-out", "workspace": "default"},
            ctx=ctx,
            sdk=sdk,
        )

    assert result == {"status": "completed", "returncode": 0}
    sdk.files.upload.assert_called_once()
    assert sdk.files.upload.call_args.kwargs["fileset"] == "optimizer-out"


def test_run_failed_subprocess_skips_output_upload(tmp_path: Path, ctx: JobContext) -> None:
    optimize_yaml = tmp_path / "optimize.yml"
    optimize_yaml.write_text(_MINIMAL_OPTIMIZE_YAML)

    sdk = MagicMock()

    def _boom(cmd: list[str], *, check: bool, cwd: Path) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=2, cmd=cmd)

    with (
        patch("nemo_agents_plugin.jobs.optimize_agent.subprocess.run", side_effect=_boom),
        patch("nemo_agents_plugin.jobs.optimize_agent.preflight_validate_llm_models"),
    ):
        result = OptimizeAgentJob().run(
            {"optimize_config": str(optimize_yaml), "output": "optimizer-out", "workspace": "default"},
            ctx=ctx,
            sdk=sdk,
        )

    assert result == {"status": "failed", "returncode": 2}
    sdk.files.upload.assert_not_called()
