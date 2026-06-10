# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the promoted environment boundary + environment authoring."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes import docker as docker_mod
from nemo_evaluator_sdk.agent_eval.runtimes.environment import (
    DockerEnvironmentHandle,
    DockerEnvironmentProvider,
    EnvRunSpec,
    default_image_tag,
)
from nemo_evaluator_sdk.agent_eval.runtimes.environment_spec import load_environment_spec, plan_task_build
from nemo_evaluator_sdk.agent_eval.types import AgentEvalTask


@pytest.mark.asyncio
async def test_docker_handle_routes_roles_through_single_run(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_docker_run(image: str, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((image, command))
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr(docker_mod, "docker_run", fake_docker_run)

    handle = DockerEnvironmentHandle("img:latest")
    spec = EnvRunSpec(command=["echo", "hi"])
    assert (await handle.run_agent(spec)).ok
    assert (await handle.run_verifier(spec)).ok
    assert calls == [("img:latest", ["echo", "hi"]), ("img:latest", ["echo", "hi"])]


@pytest.mark.asyncio
async def test_docker_handle_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_docker_run(image: str, command: list[str], **kwargs: object):
        raise subprocess.TimeoutExpired(cmd=command, timeout=1)

    monkeypatch.setattr(docker_mod, "docker_run", fake_docker_run)
    result = await DockerEnvironmentHandle("img").run(EnvRunSpec(command=["sleep"]), "agent")
    assert result.timed_out and result.exit_code == 124 and not result.ok


@pytest.mark.asyncio
async def test_provider_uses_injected_image_tag_fn() -> None:
    assert default_image_tag("t") == "t:latest"
    provider = DockerEnvironmentProvider(image_tag_fn=lambda task_id: f"custom-{task_id}")
    handle = await provider.prepare(AgentEvalTask(id="demo", intent="x", inputs={}))
    assert isinstance(handle, DockerEnvironmentHandle)
    assert handle.image == "custom-demo"


def test_environment_spec_yaml_dockerfile_and_plan(tmp_path: Path) -> None:
    (tmp_path / "environment.yaml").write_text(
        "environment:\n  image: base:1\n  dependencies:\n    python: [pytest]\n  setup: [seed]\n",
        encoding="utf-8",
    )
    spec = load_environment_spec(tmp_path)
    assert spec.image == "base:1" and spec.python_dependencies == ["pytest"]

    plan = plan_task_build(tmp_path, "img:latest", generated_dir=tmp_path / "build")
    content = plan.dockerfile.read_text(encoding="utf-8")
    assert plan.generated and plan.base_image == "base:1"
    assert content.startswith("FROM base:1") and "pip install --no-cache-dir pytest" in content

    # Dockerfile escape hatch wins when no yaml present.
    other = tmp_path / "task2" / "environment"
    other.mkdir(parents=True)
    (other / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    escape = load_environment_spec(tmp_path / "task2")
    assert escape.dockerfile == other / "Dockerfile" and escape.image is None
