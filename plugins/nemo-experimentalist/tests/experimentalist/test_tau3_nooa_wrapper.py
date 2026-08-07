# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Behavioral tests for the tau3 NOOA agent's Harbor wrapper.

The example is a standalone uv project, so the wrapper is loaded by path
rather than imported as a package.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO_ROOT / "examples" / "tau3-nooa-agent"


def _load_wrapper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tau3_harbor_wrapper", AGENT_DIR / "harbor_wrapper.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CrashedAgentEnvironment:
    """An environment whose agent died before writing any traces.

    ``download_dir`` then fails the way Harbor's Docker backend does: the
    traces directory was never created, so the copy has no source.
    """

    def __init__(self) -> None:
        self.default_user = "root"

    async def exec(self, command, user=None, env=None, cwd=None, timeout_sec=None):
        return SimpleNamespace(
            stdout="",
            stderr="IndentationError: unexpected indent (main.py, line 69)",
            return_code=1,
        )

    async def download_dir(self, source_dir, target_dir):
        raise RuntimeError(f"Docker compose command failed. Could not find the file {source_dir}/. in container abc123")


async def test_crashed_agent_reports_its_own_failure_not_the_missing_traces_dir(tmp_path):
    # A missing /app/traces is a symptom of the agent dying, never the cause. If the
    # copy failure escapes, it masks the traceback that explains the run.
    wrapper = _load_wrapper()
    agent = wrapper.WrappedAgent(logs_dir=tmp_path)
    context = SimpleNamespace(n_input_tokens=None, n_output_tokens=None, n_cache_tokens=None, metadata=None)

    with pytest.raises(RuntimeError, match="Agent process failed with exit code 1"):
        await agent.run("do the task", _CrashedAgentEnvironment(), context)


async def test_crashed_agent_surfaces_the_agent_stderr(tmp_path):
    wrapper = _load_wrapper()
    agent = wrapper.WrappedAgent(logs_dir=tmp_path)
    context = SimpleNamespace(n_input_tokens=None, n_output_tokens=None, n_cache_tokens=None, metadata=None)

    with pytest.raises(RuntimeError, match="IndentationError"):
        await agent.run("do the task", _CrashedAgentEnvironment(), context)


async def test_missing_traces_is_recorded_as_a_metrics_error(tmp_path):
    wrapper = _load_wrapper()
    agent = wrapper.WrappedAgent(logs_dir=tmp_path)
    context = SimpleNamespace(n_input_tokens=None, n_output_tokens=None, n_cache_tokens=None, metadata=None)

    with pytest.raises(RuntimeError):
        await agent.run("do the task", _CrashedAgentEnvironment(), context)

    assert context.metadata is not None
    assert "Trace metrics unavailable" in context.metadata["metrics_error"]
    assert context.metadata["returncode"] == 1
