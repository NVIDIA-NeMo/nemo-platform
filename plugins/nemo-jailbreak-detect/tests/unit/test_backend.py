# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the deployment backends (docker CLI mocked)."""

from __future__ import annotations

import pytest
from nemo_jailbreak_detect.deployment import backend as backend_mod
from nemo_jailbreak_detect.deployment.backend import (
    DeploymentSpec,
    DockerBackend,
    JobsBackend,
    get_backend,
)

_SPEC = DeploymentSpec(
    name="jbd",
    workspace="default",
    image="nemo/jailbreak-detect:0.1.0",
    device="cpu",
    port=8123,
    model_cache_dir="/tmp/c",
)


def _fake_run(results: list[tuple[int, str, str]]):
    calls: list[list[str]] = []

    async def _run(*args: str):
        calls.append(list(args))
        return results.pop(0)

    return _run, calls


def test_get_backend_resolution():
    assert isinstance(get_backend("docker"), DockerBackend)
    assert isinstance(get_backend("jobs"), JobsBackend)
    with pytest.raises(ValueError):
        get_backend("nope")


async def test_docker_ensure_started_runs_container(monkeypatch):
    # ps (no running container) -> rm -> run (returns id)
    run, calls = _fake_run([(0, "", ""), (0, "", ""), (0, "abc123", "")])
    monkeypatch.setattr(backend_mod, "_run", run)

    result = await DockerBackend().ensure_started(_SPEC)

    assert result.handle == "abc123"
    assert result.endpoint_url == "http://localhost:8123"
    # last call is the docker run with the right port mapping
    run_cmd = calls[-1]
    assert run_cmd[:3] == ["docker", "run", "-d"]
    assert "8123:8000" in run_cmd
    # container name is scoped by workspace so deployments don't collide
    assert "nemo-jailbreak-detect-default-jbd" in run_cmd


async def test_docker_ensure_started_idempotent_when_running(monkeypatch):
    # ps reports a running container id immediately
    run, calls = _fake_run([(0, "existing", "")])
    monkeypatch.setattr(backend_mod, "_run", run)

    result = await DockerBackend().ensure_started(_SPEC)

    assert result.handle == "existing"
    assert len(calls) == 1  # no rm / run issued


async def test_docker_ensure_started_gpu_flags(monkeypatch):
    gpu_spec = DeploymentSpec(
        name="jbd", workspace="default", image="img", device="cuda:0", port=9000, model_cache_dir="/tmp/c"
    )
    run, calls = _fake_run([(0, "", ""), (0, "", ""), (0, "gpuid", "")])
    monkeypatch.setattr(backend_mod, "_run", run)

    await DockerBackend().ensure_started(gpu_spec)

    run_cmd = calls[-1]
    assert "--gpus" in run_cmd and "all" in run_cmd


async def test_jobs_backend_not_implemented():
    with pytest.raises(NotImplementedError):
        await JobsBackend().ensure_started(_SPEC)
