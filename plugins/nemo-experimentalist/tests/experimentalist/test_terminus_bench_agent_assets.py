# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest.mock import patch

import harbor
import pytest

_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "terminus-bench-agent"
_WRAPPER = _EXAMPLE_DIR / "harbor_wrapper.py"
_PREPARE = _EXAMPLE_DIR / "prepare-candidate-source.sh"


def _load_staged_wrapper(tmp_path: Path) -> ModuleType:
    staged = tmp_path / "candidate"
    staged.mkdir()
    source_root = Path(harbor.__file__).resolve().parent.parent
    (staged / "src").symlink_to(source_root, target_is_directory=True)
    shutil.copy2(_WRAPPER, staged / "harbor_wrapper.py")

    module_name = "_test_terminus_bench_harbor_wrapper"
    spec = importlib.util.spec_from_file_location(module_name, staged / "harbor_wrapper.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_wrapper_loads_candidate_source_and_pins_opus_streaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INFERENCE_API_KEY", "test-inference-key")
    wrapper = _load_staged_wrapper(tmp_path)
    candidate_terminus = wrapper.WrappedAgent.__mro__[1]

    terminus_path = Path(candidate_terminus.__init__.__code__.co_filename).resolve()
    assert terminus_path.is_relative_to((tmp_path / "candidate" / "src").resolve())

    with patch.object(candidate_terminus, "__init__", return_value=None) as init:
        wrapper.WrappedAgent(logs_dir=tmp_path)
    assert init.call_args.kwargs == {
        "logs_dir": tmp_path,
        "model_name": "openai/azure/anthropic/claude-opus-4-8",
        "api_base": "https://inference-api.nvidia.com/v1",
        "stream": True,
        "llm_kwargs": {"api_key": "test-inference-key"},
    }


class _ExecResult:
    return_code = 0


class _Environment:
    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str]] = []

    async def exec(self, command: str) -> _ExecResult:
        assert command == "mkdir -p /app/traces"
        return _ExecResult()

    async def upload_file(self, source: Path, target: str) -> None:
        self.uploads.append((source, target))


@pytest.mark.asyncio
async def test_wrapper_publishes_harbor_trajectory_as_atif(tmp_path: Path) -> None:
    wrapper = _load_staged_wrapper(tmp_path)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    trajectory = logs_dir / "trajectory.json"
    trajectory.write_text('{"schema_version": "ATIF-v1.7"}', encoding="utf-8")
    agent = object.__new__(wrapper.WrappedAgent)
    agent.logs_dir = logs_dir
    agent.logger = logging.getLogger("test-terminus-bench-wrapper")
    environment = _Environment()

    await agent._publish_atif_artifact(cast(Any, environment))

    assert environment.uploads == [(trajectory, "/app/traces/trajectory.atif.json")]


def test_prepare_script_builds_an_external_candidate_source(tmp_path: Path) -> None:
    harbor_checkout = tmp_path / "harbor"
    terminus = harbor_checkout / "src" / "harbor" / "agents" / "terminus_2" / "terminus_2.py"
    terminus.parent.mkdir(parents=True)
    terminus.write_text("# candidate marker\n", encoding="utf-8")
    (harbor_checkout / ".git").mkdir()
    destination = tmp_path / "staged"

    subprocess.run([_PREPARE, harbor_checkout, destination], check=True)

    assert (destination / "src" / "harbor" / "agents" / "terminus_2" / "terminus_2.py").is_file()
    assert (destination / "harbor_wrapper.py").read_bytes() == _WRAPPER.read_bytes()
    assert not (destination / ".git").exists()
