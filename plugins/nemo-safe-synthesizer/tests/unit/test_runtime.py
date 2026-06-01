# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from subprocess import CompletedProcess

import pytest
from nemo_safe_synthesizer_plugin import runtime
from nemo_safe_synthesizer_plugin.config import SafeSynthesizerConfig


def test_runtime_paths_are_repo_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "repo_root", lambda: tmp_path)
    config = SafeSynthesizerConfig.model_validate({"runtime_venv": "runtime/nss"})

    assert runtime.runtime_venv_path(config) == tmp_path / "runtime/nss"
    assert runtime.runtime_python_path(config) == tmp_path / "runtime/nss/bin/python"


def test_runtime_task_command_requires_runtime_python(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "repo_root", lambda: tmp_path)
    config = SafeSynthesizerConfig.model_validate({"runtime_venv": "missing-runtime"})

    with pytest.raises(RuntimeError, match="runtime Python was not found"):
        runtime.runtime_task_command(config)


def test_runtime_task_command_uses_configured_python(tmp_path):
    python = tmp_path / "bin/python"
    python.parent.mkdir()
    python.touch()
    config = SafeSynthesizerConfig.model_validate({"runtime_python": str(python)})

    command = runtime.runtime_task_command(config, ["run-local", "--workspace", "default"])

    assert command == [
        str(python),
        "-m",
        runtime.TASK_MODULE,
        "run-local",
        "--workspace",
        "default",
    ]


def test_cuda_runtime_package_adds_cu129_sources():
    runtime_package = "nemo-safe-synthesizer[engine,cu129]==0.1.0rc0"

    assert runtime.runtime_package_index_options(runtime_package) == [
        "--extra-index-url",
        runtime.FLASHINFER_CU129_INDEX_URL,
        "--extra-index-url",
        runtime.PYTORCH_CU129_INDEX_URL,
    ]
    assert runtime.runtime_package_extra_requirements(runtime_package) == [runtime.vllm_cu129_wheel()]


def test_non_cu129_runtime_package_does_not_add_cu129_sources():
    runtime_package = "nemo-safe-synthesizer[engine]==0.1.0rc0"

    assert runtime.runtime_package_index_options(runtime_package) == []
    assert runtime.runtime_package_extra_requirements(runtime_package) == []


def test_setup_runtime_uses_separate_uv_install_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "repo_root", lambda: tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return CompletedProcess(command, 0)

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    config = SafeSynthesizerConfig.model_validate(
        {"runtime_venv": "runtime", "runtime_package": "nemo-safe-synthesizer[engine,cu129]"}
    )

    runtime_python = runtime.setup_runtime(config)

    assert runtime_python == tmp_path / "runtime/bin/python"
    assert calls[0][0] == ["uv", "venv", "--python", "3.11", "--allow-existing", str(tmp_path / "runtime")]
    assert calls[1][0][:5] == ["uv", "pip", "install", "--python", str(runtime_python)]
    assert "hatchling==1.26.3" in calls[1][0]
    assert "hatch-fancy-pypi-readme" in calls[1][0]
    assert "editables" in calls[1][0]
    assert "setuptools" in calls[1][0]
    assert "uv-dynamic-versioning" in calls[1][0]
    assert calls[2][0][:6] == ["uv", "pip", "install", "--python", str(runtime_python), "--no-build-isolation"]
    assert "--extra-index-url" in calls[2][0]
    assert runtime.FLASHINFER_CU129_INDEX_URL in calls[2][0]
    assert runtime.PYTORCH_CU129_INDEX_URL in calls[2][0]
    assert runtime.vllm_cu129_wheel() in calls[2][0]
    assert str(tmp_path / "plugins/nemo-safe-synthesizer") not in calls[2][0]
    assert "nemo-safe-synthesizer[engine,cu129]" in calls[2][0]
    assert calls[3][0] == [
        "uv",
        "pip",
        "install",
        "--python",
        str(runtime_python),
        "--no-build-isolation",
        "--no-deps",
        "-e",
        str(tmp_path / "plugins/nemo-safe-synthesizer"),
    ]


def test_setup_runtime_refuses_to_delete_repo_root(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "repo_root", lambda: tmp_path)
    config = SafeSynthesizerConfig.model_validate({"runtime_venv": "."})

    with pytest.raises(RuntimeError, match="Refusing to delete protected path"):
        runtime.setup_runtime(config, force=True)


def test_runtime_info_does_not_probe_missing_python(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "repo_root", lambda: tmp_path)
    config = SafeSynthesizerConfig.model_validate({"runtime_venv": "missing-runtime"})

    info = runtime.runtime_info(config)

    assert info["python_exists"] is False
    assert info["python"] == str(Path(tmp_path / "missing-runtime/bin/python"))
