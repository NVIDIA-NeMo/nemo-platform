# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Remote evaluator and dependency-session boundary tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import HarborDataset
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    EvaluationResult,
    MetricResult,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.remote_harbor import (
    BRIDGE_TOKEN_ENV,
    BRIDGE_URL_ENV,
    OPEN_SHELL_RUNTIME_ENV,
    RemoteHarborDependencyRuntime,
    RemoteHarborEvaluator,
    RemoteHarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    DependencyExecResponse,
    DependencyStartRequest,
)
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    RegisteredEnvelope,
    register_dataset_envelope,
)
from nemo_experimentalist_plugin.harbor_bridge.service import HarborBridgeSettings, create_app

_TOKEN = "remote-bridge-token-long-enough"


def _registered_dataset(tmp_path: Path, *, single_task_root: bool = False) -> RegisteredEnvelope:
    dataset = tmp_path / "source"
    task = dataset if single_task_root else dataset / "base-task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "task.toml").write_text(
        '[task]\nname = "fixture/base-task"\n[environment]\ntype = "docker"\n[verifier]\n',
        encoding="utf-8",
    )
    (task / "instruction.md").write_text("trusted instruction\n", encoding="utf-8")
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (task / "tests" / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (task / "nemo-task-envelope.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task_data": [
                    {
                        "path": "instruction.md",
                        "media_type": "text/plain",
                        "max_bytes": 65536,
                    }
                ],
                "verifier_paths": ["tests/test.sh"],
            }
        ),
        encoding="utf-8",
    )
    return register_dataset_envelope(dataset, catalog_root=tmp_path / "catalog", name="fixture")


class _RecordingRunner:
    calls = 0

    async def run(self, **kwargs: Any) -> EvaluationResult:
        self.calls += 1
        dataset_dir = cast(Path, kwargs["dataset_dir"])
        candidate_dir = cast(Path, kwargs["candidate_dir"])
        assert (candidate_dir / "main.py").is_file()
        assert (dataset_dir / "base-task" / "instruction.md").read_text(encoding="utf-8") == "changed\n"
        return EvaluationResult(
            id="bridge-result",
            trials=[
                TrialResult(
                    id="base-task__0",
                    task_id="base-task",
                    attempt=0,
                    status="completed",
                    metrics={"reward": MetricResult(name="reward", value=1.0)},
                )
            ],
        )


async def test_remote_evaluator_submits_and_translates_trials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registered = _registered_dataset(tmp_path)
    sandbox_dataset = tmp_path / "sandbox-dataset"
    shutil.copytree(registered.dataset_path, sandbox_dataset)
    (sandbox_dataset / "base-task" / "instruction.md").write_text("changed\n", encoding="utf-8")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "main.py").write_text("raise AssertionError('host import')\n", encoding="utf-8")
    runner = _RecordingRunner()
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=tmp_path / "jobs",
            catalog_root=tmp_path / "catalog",
            token=_TOKEN,
        ),
        runner=runner,
    )
    monkeypatch.setenv(BRIDGE_TOKEN_ENV, _TOKEN)
    evaluator = RemoteHarborEvaluator(
        RemoteHarborEvaluatorConfig(
            bridge_url="http://bridge.test",
            run_profile="smoke",
            poll_interval_sec=0.01,
        ),
        experiment_dir=tmp_path / "experiment",
        transport=httpx.ASGITransport(app=app),
    )
    dataset = HarborDataset.from_ref(DatasetRef(uri=sandbox_dataset.as_uri()))
    evaluator.prepare_dataset(dataset)

    result = await evaluator.run(candidate, dataset)

    assert runner.calls == 1
    assert result.aggregate_metrics == {"reward": 1.0}
    assert result.trials[0].task_id == "base-task"
    assert isinstance(dataset.tasks[0].dependencies, RemoteHarborDependencyRuntime)


def test_copied_template_automatically_uses_remote_dependency_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registered = _registered_dataset(tmp_path, single_task_root=True)
    generated_suite = tmp_path / "generated"
    shutil.copytree(registered.dataset_path, generated_suite / "trace-task")
    monkeypatch.setenv(OPEN_SHELL_RUNTIME_ENV, "1")
    monkeypatch.setenv(BRIDGE_URL_ENV, "http://bridge.test")

    dataset = HarborDataset.from_path(generated_suite)

    runtime = dataset.tasks[0].dependencies
    assert isinstance(runtime, RemoteHarborDependencyRuntime)
    assert runtime.base_task_id == "source"
    assert runtime.task_id == "trace-task"


class _FakeDependencySessions:
    def __init__(self) -> None:
        self.started: DependencyStartRequest | None = None
        self.stopped: str | None = None

    async def start(
        self,
        request: DependencyStartRequest,
        *,
        task_dir: Path,
        work_dir: Path,
    ) -> str:
        assert task_dir.is_dir()
        assert work_dir.is_dir()
        self.started = request
        return "dependency-session"

    async def execute(self, session_id: str, request) -> DependencyExecResponse:
        assert session_id == "dependency-session"
        return DependencyExecResponse(stdout=request.command, stderr="", returncode=0)

    async def stop(self, session_id: str) -> None:
        self.stopped = session_id

    async def close(self) -> None:
        return None


def test_dependency_api_uses_opaque_capability_and_rejects_authority(tmp_path: Path) -> None:
    registered = _registered_dataset(tmp_path)
    sessions = _FakeDependencySessions()
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=tmp_path / "jobs",
            catalog_root=tmp_path / "catalog",
            token=_TOKEN,
        ),
        dependency_sessions=cast(Any, sessions),
    )
    metadata = DependencyStartRequest(
        request_id="dependency-test",
        envelope_id=registered.manifest.envelope_id,
        envelope_digest=registered.manifest.envelope_digest,
        task_id="generated-task",
        base_task_id="base-task",
    )
    auth = {"Authorization": f"Bearer {_TOKEN}"}
    with TestClient(app) as client:
        rejected = metadata.model_dump()
        rejected["image"] = "attacker/image:latest"
        assert (
            client.post(
                "/v1/dependencies",
                data={"metadata": json.dumps(rejected)},
                headers=auth,
            ).status_code
            == 422
        )

        started = client.post(
            "/v1/dependencies",
            data={"metadata": metadata.model_dump_json()},
            headers=auth,
        )
        assert started.status_code == 201
        capability = started.json()["capability_token"]
        assert (
            client.post(
                "/v1/dependencies/dependency-session/exec",
                json={"command": "pwd"},
                headers=auth,
            ).status_code
            == 403
        )
        executed = client.post(
            "/v1/dependencies/dependency-session/exec",
            json={"command": "pwd"},
            headers={**auth, "X-Nemo-Dependency-Capability": capability},
        )
        assert executed.json() == {"stdout": "pwd", "stderr": "", "returncode": 0}
        stopped = client.delete(
            "/v1/dependencies/dependency-session",
            headers={**auth, "X-Nemo-Dependency-Capability": capability},
        )
        assert stopped.status_code == 204
    assert sessions.started == metadata
    assert sessions.stopped == "dependency-session"
