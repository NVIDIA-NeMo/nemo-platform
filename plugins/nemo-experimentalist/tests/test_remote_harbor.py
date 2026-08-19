# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Remote evaluator and dependency-session boundary tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import httpx
import nemo_experimentalist_plugin.harbor_bridge.dependencies as dependency_module
import pytest
from fastapi.testclient import TestClient
from nemo_experimentalist_plugin.entities import (
    DatasetRef,
    DependencyRuntimeError,
    EvaluationResult,
    MetricResult,
    ResourceRef,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import EvaluatorFactory
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborDependencyRuntime,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.remote_harbor import (
    BRIDGE_TOKEN_ENV,
    RemoteHarborDependencyContext,
    RemoteHarborDependencyRuntime,
    RemoteHarborEvaluatorConfig,
    RemoteHarborOutcomeEvaluator,
    _bridge_headers,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    IDENTIFIER_MAX_LENGTH,
    DependencyExecResponse,
    DependencyStartRequest,
)
from nemo_experimentalist_plugin.harbor_bridge.dependencies import HarborDependencySessionManager
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    RegisteredEnvelope,
    register_dataset_envelope,
)
from nemo_experimentalist_plugin.harbor_bridge.service import HarborBridgeSettings, create_app
from pydantic import ValidationError

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
        work_dir = cast(Path, kwargs["work_dir"])
        assert (candidate_dir / "main.py").is_file()
        assert (dataset_dir / "base-task" / "instruction.md").read_text(encoding="utf-8") == "changed\n"
        trace = work_dir / "results" / "trace.jsonl"
        trace.parent.mkdir()
        trace.write_text('{"resourceSpans":[]}\n', encoding="utf-8")
        return EvaluationResult(
            id="bridge-result",
            trials=[
                TrialResult(
                    id="base-task__0",
                    task_id="base-task",
                    attempt=0,
                    status="completed",
                    trace=ResourceRef(uri=trace.as_uri(), description="trace"),
                    metrics={"reward": MetricResult(name="reward", value=1.0)},
                )
            ],
        )


async def test_remote_evaluator_submits_and_translates_trials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    registered = _registered_dataset(tmp_path)
    sandbox_dataset = tmp_path / "sandbox-dataset"
    shutil.copytree(registered.dataset_path, sandbox_dataset)
    (sandbox_dataset / "base-task" / "instruction.md").write_text("changed\n", encoding="utf-8")
    candidates = [tmp_path / "baseline", tmp_path / "candidate"]
    for candidate in candidates:
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
    config = RemoteHarborEvaluatorConfig(
        bridge_url="http://bridge.test",
        run_profile="smoke",
        poll_interval_sec=0.01,
        max_archive_bytes=4096,
    )
    evaluator = RemoteHarborOutcomeEvaluator(
        config,
        experiment_dir=Path("experiment"),
        transport=httpx.ASGITransport(app=app),
    )
    dataset = HarborDataset.from_ref(DatasetRef(uri=sandbox_dataset.as_uri()))

    baseline_result = await evaluator.run(candidates[0], dataset)
    result = await evaluator.run(candidates[1], dataset)

    assert runner.calls == 2
    assert baseline_result.aggregate_metrics == {"reward": 1.0}
    assert result.aggregate_metrics == {"reward": 1.0}
    assert result.trials[0].task_id == "base-task"
    assert result.trials[0].trace is not None
    assert Path(result.trials[0].trace.uri.removeprefix("file://")).read_text(encoding="utf-8") == (
        '{"resourceSpans":[]}\n'
    )
    assert isinstance(dataset.tasks[0].dependencies, HarborDependencyRuntime)
    runtime = evaluator._dependency_runtime(dataset, dataset.tasks[0])
    assert isinstance(runtime, RemoteHarborDependencyRuntime)
    assert runtime.max_archive_bytes == 4096


async def test_dependency_command_extends_client_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_timeout: dict[str, float] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured_timeout.update(request.extensions["timeout"])
        return httpx.Response(200, json={"stdout": "", "stderr": "", "returncode": 0})

    monkeypatch.setenv(BRIDGE_TOKEN_ENV, _TOKEN)
    registered = _registered_dataset(tmp_path)
    config = RemoteHarborEvaluatorConfig(
        bridge_url="http://bridge.test",
        request_timeout_sec=5,
    )
    evaluator = RemoteHarborOutcomeEvaluator(config, transport=httpx.MockTransport(respond))
    dataset = HarborDataset.from_ref(DatasetRef(uri=registered.dataset_path.as_uri()))
    runtime = evaluator._dependency_runtime(dataset, dataset.tasks[0])
    assert isinstance(runtime, RemoteHarborDependencyRuntime)
    runtime._session_id = "dependency-session"
    runtime._capability = "capability"

    await runtime.execute("pwd", timeout=120)

    assert captured_timeout["read"] == 130


def test_remote_evaluator_binds_static_template_to_bridge_runtime(tmp_path: Path) -> None:
    registered = _registered_dataset(tmp_path, single_task_root=True)
    generated_suite = tmp_path / "generated"
    shutil.copytree(registered.dataset_path, generated_suite / "trace-task")

    evaluator = RemoteHarborOutcomeEvaluator(RemoteHarborEvaluatorConfig(bridge_url="http://bridge.test"))
    dataset = HarborDataset.from_ref(DatasetRef(uri=generated_suite.as_uri()))
    assert isinstance(dataset.tasks[0].dependencies, HarborDependencyRuntime)
    runtime = evaluator._dependency_runtime(dataset, dataset.tasks[0])
    assert isinstance(runtime, RemoteHarborDependencyRuntime)
    assert runtime.base_task_id == "source"
    assert runtime.task_id == "trace-task"


def test_factory_selects_remote_evaluator_without_local_fallback() -> None:
    evaluator = EvaluatorFactory().build_evaluator("remote-harbor", {"bridge_url": "http://bridge.test"})

    assert isinstance(evaluator, RemoteHarborOutcomeEvaluator)


def test_factory_fails_closed_when_bridge_url_is_missing() -> None:
    with pytest.raises(ValidationError, match="bridge_url"):
        EvaluatorFactory().build_evaluator("remote-harbor", {})


def test_openshell_bridge_request_uses_provider_placeholder(monkeypatch) -> None:
    placeholder = "openshell:resolve:env:NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN"
    monkeypatch.setenv(BRIDGE_TOKEN_ENV, placeholder)

    assert _bridge_headers(BRIDGE_TOKEN_ENV) == {"Authorization": f"Bearer {placeholder}"}


def test_openshell_bridge_request_fails_without_provider_placeholder(monkeypatch) -> None:
    monkeypatch.delenv(BRIDGE_TOKEN_ENV, raising=False)

    with pytest.raises(DependencyRuntimeError, match=BRIDGE_TOKEN_ENV):
        _bridge_headers(BRIDGE_TOKEN_ENV)


async def test_dependency_shutdown_preserves_body_error_and_clears_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BRIDGE_TOKEN_ENV, _TOKEN)
    registered = _registered_dataset(tmp_path)
    config = RemoteHarborEvaluatorConfig(bridge_url="http://bridge.test")
    evaluator = RemoteHarborOutcomeEvaluator(
        config, transport=httpx.MockTransport(lambda _request: httpx.Response(500))
    )
    dataset = HarborDataset.from_ref(DatasetRef(uri=registered.dataset_path.as_uri()))
    runtime = evaluator._dependency_runtime(dataset, dataset.tasks[0])
    assert isinstance(runtime, RemoteHarborDependencyRuntime)
    context = RemoteHarborDependencyContext(runtime)

    runtime._session_id = "dependency-session"
    runtime._capability = "capability"
    body_error = RuntimeError("body failed")
    assert await context.__aexit__(RuntimeError, body_error, None) is False
    assert runtime._session_id is None
    assert runtime._capability is None

    runtime._session_id = "dependency-session"
    runtime._capability = "capability"
    with pytest.raises(DependencyRuntimeError, match="shutdown failed"):
        await context.__aexit__(None, None, None)
    assert runtime._session_id is None
    assert runtime._capability is None


async def test_dependency_session_id_is_bounded_and_runtime_is_stopped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts: list[Any] = []

    class FakeContext:
        def __init__(self, runtime: Any, *, temp_root: Path) -> None:
            del runtime, temp_root
            self.stopped = False
            contexts.append(self)

        async def __aenter__(self) -> FakeContext:
            return self

        async def __aexit__(self, *args: object) -> bool:
            del args
            self.stopped = True
            return False

    monkeypatch.setattr(dependency_module, "HarborDependencyContext", FakeContext)
    manager = HarborDependencySessionManager()
    request = DependencyStartRequest(
        request_id="r" * IDENTIFIER_MAX_LENGTH,
        envelope_id="envelope",
        envelope_digest=f"sha256:{'0' * 64}",
        task_id="task",
        base_task_id="base-task",
    )

    session_id = await manager.start(
        request,
        task_dir=tmp_path / "task",
        work_dir=tmp_path / "work",
    )

    assert len(session_id) == IDENTIFIER_MAX_LENGTH
    assert session_id.startswith("r")
    await manager.stop(session_id)
    assert contexts[0].stopped is True


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
        assert (
            client.post(
                "/v1/dependencies/dependency-session/exec",
                json={"command": "pwd"},
                headers=[
                    (b"Authorization", f"Bearer {_TOKEN}".encode()),
                    (b"X-Nemo-Dependency-Capability", "café".encode("latin-1")),
                ],
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
