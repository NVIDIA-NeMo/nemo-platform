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
from nemo_platform_plugin.run_dependencies import LocalRunError


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


def test_resolve_optimize_config_local_path_pass_through(tmp_path: Path, ctx: JobContext) -> None:
    job = OptimizeAgentJob()
    spec = OptimizeAgentSpec(optimize_config=str(tmp_path / "config.yml"), optimize_config_fileset=None)
    with job._resolve_optimize_config(spec, ctx=ctx, sdk=None) as resolved:
        assert resolved == Path(str(tmp_path / "config.yml"))


def test_resolve_optimize_config_fileset_downloads_via_sdk(tmp_path: Path, ctx: JobContext) -> None:
    job = OptimizeAgentJob()
    spec = OptimizeAgentSpec(
        optimize_config="config.yml",
        optimize_config_fileset=FilesetRef("nemo-agent-optimizer-configs"),
        workspace="default",
    )

    sdk = MagicMock()

    def _fake_download(local_path: str, fileset: str, workspace: str) -> None:
        Path(local_path, "config.yml").write_text("optimizer: {}")

    sdk.files.download.side_effect = _fake_download

    with job._resolve_optimize_config(spec, ctx=ctx, sdk=sdk) as resolved:
        assert resolved.exists()
        assert resolved.name == "config.yml"
        assert resolved.read_text() == "optimizer: {}"

    sdk.files.download.assert_called_once()
    kwargs = sdk.files.download.call_args.kwargs
    assert kwargs["fileset"] == "nemo-agent-optimizer-configs"
    assert kwargs["workspace"] == "default"


def test_resolve_optimize_config_fileset_without_sdk_raises(tmp_path: Path, ctx: JobContext) -> None:
    job = OptimizeAgentJob()
    spec = OptimizeAgentSpec(
        optimize_config="config.yml",
        optimize_config_fileset=FilesetRef("nemo-agent-optimizer-configs"),
    )
    with pytest.raises(LocalRunError, match="sdk"):
        with job._resolve_optimize_config(spec, ctx=ctx, sdk=None):
            pass


def test_resolve_optimize_config_fileset_tempdir_lands_under_ctx_ephemeral(tmp_path: Path, ctx: JobContext) -> None:
    job = OptimizeAgentJob()
    spec = OptimizeAgentSpec(
        optimize_config="config.yml",
        optimize_config_fileset=FilesetRef("nemo-agent-optimizer-configs"),
        workspace="default",
    )
    sdk = MagicMock()

    seen: dict[str, Path] = {}

    def _fake_download(local_path: str, fileset: str, workspace: str) -> None:
        seen["local_path"] = Path(local_path)
        Path(local_path, "config.yml").write_text("optimizer: {}")

    sdk.files.download.side_effect = _fake_download

    with job._resolve_optimize_config(spec, ctx=ctx, sdk=sdk):
        pass

    assert seen["local_path"].parent == ctx.storage.ephemeral


def test_resolve_optimize_config_fileset_rejects_path_traversal(tmp_path: Path, ctx: JobContext) -> None:
    job = OptimizeAgentJob()
    spec = OptimizeAgentSpec(
        optimize_config="../escape.yml",
        optimize_config_fileset=FilesetRef("nemo-agent-optimizer-configs"),
        workspace="default",
    )
    sdk = MagicMock()

    def _fake_download(local_path: str, fileset: str, workspace: str) -> None:
        # Plant the traversal target outside the download dir so the guard,
        # not a missing file, is what rejects it.
        Path(local_path).parent.joinpath("escape.yml").write_text("optimizer: {}")

    sdk.files.download.side_effect = _fake_download

    with pytest.raises(ValueError, match="resolves outside the downloaded fileset"):
        with job._resolve_optimize_config(spec, ctx=ctx, sdk=sdk):
            pass


def test_resolve_optimize_config_fileset_missing_file_raises(tmp_path: Path, ctx: JobContext) -> None:
    job = OptimizeAgentJob()
    spec = OptimizeAgentSpec(
        optimize_config="config.yml",
        optimize_config_fileset=FilesetRef("nemo-agent-optimizer-configs"),
        workspace="default",
    )
    sdk = MagicMock()

    def _fake_download(local_path: str, fileset: str, workspace: str) -> None:
        # Fileset downloads, but the requested config isn't among its files.
        Path(local_path, "other.yml").write_text("optimizer: {}")

    sdk.files.download.side_effect = _fake_download

    with pytest.raises(FileNotFoundError, match="was not found in fileset"):
        with job._resolve_optimize_config(spec, ctx=ctx, sdk=sdk):
            pass
