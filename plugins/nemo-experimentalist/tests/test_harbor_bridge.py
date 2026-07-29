# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
import io
import sys
import tarfile
from pathlib import Path

import httpx
import pytest
from harbor.models.task.config import VerifierEnvironmentMode
from harbor.models.task.task import Task as HarborTask
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import EvaluatorFactory
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborDependencyRuntime,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    CommandSpec,
    DependencyRuntime,
    DependencyRuntimeError,
    EvaluationResult,
    MetricResult,
    MetricSpec,
    ResourceRef,
    Task,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.remote_harbor import (
    RemoteHarborDependencyRuntime,
    RemoteHarborEvaluator,
    RemoteHarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.harbor_bridge import dependencies as dependency_module
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    create_directory_archive,
    create_result_archive,
    extract_directory_archive,
    materialize_result_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    DEPENDENCY_OUTPUT_LIMIT_CHARS,
    HarborBridgeRequest,
    HarborDependencyExecRequest,
    HarborDependencyExecResponse,
    HarborDependencyRequest,
)
from nemo_experimentalist_plugin.harbor_bridge.runner import _harden_task
from nemo_experimentalist_plugin.harbor_bridge.service import HarborBridgeSettings, create_app
from nemo_experimentalist_plugin.harbor_bridge.trusted_agent import (
    TrustedCandidateAgent,
    candidate_agent_import,
)
from pydantic import ValidationError


def _completed_result(trace_path: Path) -> EvaluationResult:
    return EvaluationResult(
        id="bridge-evaluation",
        aggregate_metrics={"reward": 1.0},
        trials=[
            TrialResult(
                id="trial-1",
                task_id="task-1",
                status="completed",
                trace=ResourceRef(uri=trace_path.as_uri()),
            )
        ],
    )


def _candidate(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "main.py").write_text("print('candidate')\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='candidate'\nversion='0.1.0'\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\nrevision = 3\n", encoding="utf-8")
    return root


def _complete_task_files(task_dir: Path) -> None:
    (task_dir / "instruction.md").write_text("Do the task.\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    (tests_dir / "test.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")


def test_bridge_contract_rejects_execution_authority() -> None:
    with pytest.raises(ValidationError, match="import_path"):
        HarborBridgeRequest.model_validate(
            {
                "request_id": "request-1",
                "task_ids": ["task-1"],
                "import_path": "candidate:Agent",
            }
        )


def test_dependency_contract_rejects_docker_authority() -> None:
    with pytest.raises(ValidationError, match="environment_type"):
        HarborDependencyRequest.model_validate(
            {
                "request_id": "dependency-task-1",
                "task_id": "task-1",
                "environment_type": "docker",
            }
        )


@pytest.mark.parametrize("task_ids", [["task-a", "task-a"], ["../escape"], ["task/a"]])
def test_bridge_contract_rejects_unsafe_task_ids(task_ids: list[str]) -> None:
    with pytest.raises(ValidationError, match="task_ids"):
        HarborBridgeRequest(request_id="request-1", task_ids=task_ids)


def test_directory_archive_rejects_links_and_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "target.txt").write_text("target", encoding="utf-8")
    (source / "link.txt").symlink_to(source / "target.txt")

    with pytest.raises(ValueError, match="symbolic link"):
        create_directory_archive(source, tmp_path / "source.tar.gz")

    malicious = tmp_path / "malicious.tar.gz"
    with tarfile.open(malicious, mode="w:gz") as archive:
        info = tarfile.TarInfo("../escape.txt")
        payload = b"escape"
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError, match="Unsafe archive member path"):
        extract_directory_archive(malicious, tmp_path / "extract")
    assert not (tmp_path / "escape.txt").exists()


def test_directory_archive_rejects_duplicate_paths(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        for payload in (b"first", b"second"):
            info = tarfile.TarInfo("duplicate.txt")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(ValueError, match="duplicate member paths"):
        extract_directory_archive(archive_path, tmp_path / "extract")


def test_result_archive_rewrites_artifacts_to_local_paths(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    trace = artifact_root / "trial-1" / "trace.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text('{"span":"ok"}\n', encoding="utf-8")

    archive = tmp_path / "result.tar.gz"
    create_result_archive(_completed_result(trace), artifact_root, archive)

    materialized = materialize_result_archive(archive, tmp_path / "materialized")
    materialized_trace_ref = materialized.trials[0].trace
    assert materialized_trace_ref is not None
    materialized_trace = Path(materialized_trace_ref.uri.removeprefix("file://"))
    assert materialized_trace.read_text(encoding="utf-8") == '{"span":"ok"}\n'


def test_result_archive_enforces_uncompressed_size_limit(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    trace = artifact_root / "trial-1" / "trace.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text("large trace", encoding="utf-8")

    with pytest.raises(ValueError, match="uncompressed bytes"):
        create_result_archive(
            _completed_result(trace),
            artifact_root,
            tmp_path / "result.tar.gz",
            max_bytes=1,
        )


def test_result_archive_bundles_allowed_dataset_resources(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    trace = artifact_root / "trial-1" / "trace.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text('{"span":"ok"}\n', encoding="utf-8")
    dataset_root = tmp_path / "dataset"
    verifier = dataset_root / "task-a" / "tests"
    verifier.mkdir(parents=True)
    (verifier / "test.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    result = _completed_result(trace)
    result.trials[0].metrics["reward"] = MetricResult(
        name="reward",
        value=1.0,
        spec=MetricSpec(
            name="reward",
            description="Harbor verifier reward.",
            ref=ResourceRef(uri=verifier.as_uri()),
        ),
    )

    archive = tmp_path / "result.tar.gz"
    create_result_archive(
        result,
        artifact_root,
        archive,
        additional_resource_roots={"dataset": dataset_root},
    )
    materialized = materialize_result_archive(archive, tmp_path / "materialized")

    metric_spec = materialized.trials[0].metrics["reward"].spec
    assert metric_spec is not None
    metric_ref = metric_spec.ref
    assert metric_ref is not None
    metric_path = Path(metric_ref.uri.removeprefix("file://"))
    assert (metric_path / "test.sh").read_text(encoding="utf-8") == "#!/bin/sh\n"


def test_factory_selects_remote_harbor_evaluator(tmp_path: Path) -> None:
    evaluator = EvaluatorFactory().build_evaluator(
        "harbor",
        {"bridge_url": "http://bridge.test:8765"},
        experiment_dir=tmp_path,
    )

    assert isinstance(evaluator, RemoteHarborEvaluator)
    assert evaluator.options == RemoteHarborEvaluatorConfig.model_validate({"bridge_url": "http://bridge.test:8765"})


def test_factory_selects_remote_harbor_evaluator_from_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL", "http://bridge.test:8765")

    evaluator = EvaluatorFactory().build_evaluator("harbor", {}, experiment_dir=tmp_path)

    assert isinstance(evaluator, RemoteHarborEvaluator)
    assert evaluator.options == RemoteHarborEvaluatorConfig.model_validate({"bridge_url": "http://bridge.test:8765"})


def test_remote_evaluator_replaces_local_harbor_dependency_runtime(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-1"
    task_dir.mkdir()
    dataset = HarborDataset(
        id="dataset",
        source=ResourceRef(uri=tmp_path.as_uri()),
        tasks=[
            Task(
                id="task-1",
                dependencies=HarborDependencyRuntime(
                    task_path=ResourceRef(uri=task_dir.as_uri()),
                    force_build=False,
                    run_healthcheck=False,
                    build_timeout_sec=120,
                ),
            )
        ],
    )
    evaluator = RemoteHarborEvaluator(
        RemoteHarborEvaluatorConfig(bridge_url="http://bridge.test:8765"),
        experiment_dir=tmp_path,
    )

    assert evaluator.prepare_dataset(dataset) is dataset
    runtime = dataset.tasks[0].dependencies
    assert isinstance(runtime, RemoteHarborDependencyRuntime)
    assert runtime.task_path.uri == task_dir.as_uri()
    assert runtime.force_build is False
    assert runtime.run_healthcheck is False
    assert runtime.build_timeout_sec == 120
    assert runtime.start is None
    assert runtime.readiness is None
    assert runtime.stop is None


@pytest.mark.parametrize(
    ("runtime_options", "match"),
    [
        ({"environment_type": "podman"}, "environment_type='docker'"),
        ({"delete": False}, "delete=true"),
        ({"start": CommandSpec(argv=["echo", "unsupported"])}, "custom lifecycle commands"),
    ],
)
def test_remote_evaluator_rejects_unsupported_dependency_runtime_options(
    tmp_path: Path,
    runtime_options: dict[str, object],
    match: str,
) -> None:
    task_dir = tmp_path / "task-1"
    task_dir.mkdir()
    dataset = HarborDataset(
        id="dataset",
        source=ResourceRef(uri=tmp_path.as_uri()),
        tasks=[
            Task(
                id="task-1",
                dependencies=HarborDependencyRuntime(
                    task_path=ResourceRef(uri=task_dir.as_uri()),
                    **runtime_options,
                ),
            )
        ],
    )
    evaluator = RemoteHarborEvaluator(
        RemoteHarborEvaluatorConfig(bridge_url="http://bridge.test:8765"),
        experiment_dir=tmp_path,
    )

    with pytest.raises(DependencyRuntimeError, match=match):
        evaluator.prepare_dataset(dataset)


def test_remote_evaluator_rejects_non_harbor_dependency_runtime(tmp_path: Path) -> None:
    dataset = HarborDataset(
        id="dataset",
        source=ResourceRef(uri=tmp_path.as_uri()),
        tasks=[
            Task(
                id="task-1",
                dependencies=DependencyRuntime(start=CommandSpec(argv=["docker", "run", "untrusted"])),
            )
        ],
    )
    evaluator = RemoteHarborEvaluator(
        RemoteHarborEvaluatorConfig(bridge_url="http://bridge.test:8765"),
        experiment_dir=tmp_path,
    )

    with pytest.raises(DependencyRuntimeError, match="will not run unsupported task dependencies locally"):
        evaluator.prepare_dataset(dataset)


@pytest.mark.asyncio
async def test_remote_dependency_runtime_starts_executes_and_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_dir = tmp_path / "task-1"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("", encoding="utf-8")
    requests: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        requests.append((request.method, request.url.path))
        assert request.headers["authorization"] == "Bearer dependency-token"
        if request.url.path == "/v1/dependencies":
            assert b'"task_id":"task-1"' in body
            assert b"docker.sock" not in body
            return httpx.Response(201, json={"session_id": "dependency-session-1"})
        if request.url.path == "/v1/dependencies/dependency-session-1/exec":
            assert b'"command":"pwd"' in body
            return httpx.Response(
                200,
                json={"stdout": "/app\n", "stderr": "", "returncode": 0},
            )
        if request.url.path == "/v1/dependencies/dependency-session-1":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRIDGE_TOKEN", "dependency-token")
    runtime = RemoteHarborDependencyRuntime(
        task_id="task-1",
        task_path=ResourceRef(uri=task_dir.as_uri()),
        bridge_url="http://bridge.test:8765",
        bridge_token_env="BRIDGE_TOKEN",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        runtime._client = client
        async with runtime.context() as entered:
            assert isinstance(entered, RemoteHarborDependencyRuntime)
            assert entered is not runtime
            result = await entered.execute("pwd")

    assert result.stdout == "/app\n"
    assert result.returncode == 0
    assert requests == [
        ("POST", "/v1/dependencies"),
        ("POST", "/v1/dependencies/dependency-session-1/exec"),
        ("DELETE", "/v1/dependencies/dependency-session-1"),
    ]
    assert runtime._session_id is None
    assert not list((tmp_path / "tmp" / "harbor-bridge").glob("*"))

    first_context = runtime.context()
    second_context = runtime.context()
    assert first_context._runtime is not second_context._runtime


@pytest.mark.asyncio
async def test_dependency_session_manager_executes_inside_environment_and_tracks_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeExecResult:
        stdout: str
        stderr = None
        return_code = 0

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    class FakeContext:
        calls: list[tuple[str, str | None, int | None]] = []
        stopped = False

        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, traceback):
            self.stopped = True
            return False

        async def execute(self, command: str, *, cwd: str | None, timeout_sec: int | None):
            self.calls.append((command, cwd, timeout_sec))
            marker_prefix = "__NEMO_DEPENDENCY_CWD_"
            marker_start = command.index(marker_prefix)
            marker_end = command.index("__", marker_start + len(marker_prefix)) + 2
            marker = command[marker_start:marker_end]
            return FakeExecResult(f"command output\n\x1e{marker}/workspace\x1e")

    context = FakeContext()
    monkeypatch.setattr(dependency_module, "_harden_task", lambda task_dir: None)
    monkeypatch.setattr(
        dependency_module,
        "HarborDependencyContext",
        lambda runtime, temp_root: context,
    )
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    manager = dependency_module.HarborDependencySessionManager(max_concurrent_sessions=1)
    session_id = await manager.start(
        HarborDependencyRequest(request_id="dependency-task-a", task_id="task-a"),
        task_dir=task_dir,
    )

    first = await manager.execute(
        session_id,
        HarborDependencyExecRequest(command="cd /workspace", timeout_sec=12),
    )
    second = await manager.execute(
        session_id,
        HarborDependencyExecRequest(command="pwd"),
    )
    await manager.stop(session_id)

    assert first.stdout == "command output\n"
    assert second.stdout == "command output\n"
    assert context.calls[0][1:] == ("/app", 12)
    assert context.calls[1][1] == "/workspace"
    assert context.stopped


def test_dependency_output_is_bounded() -> None:
    value = "x" * (DEPENDENCY_OUTPUT_LIMIT_CHARS + 1)
    truncated = dependency_module._truncate_output(value, stream="output")

    assert truncated.endswith("... (output truncated)")
    assert len(truncated) <= DEPENDENCY_OUTPUT_LIMIT_CHARS + 64


@pytest.mark.asyncio
async def test_remote_evaluator_submits_bundles_and_materializes_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "main.py").write_text("print('candidate')\n", encoding="utf-8")
    dataset_path = tmp_path / "dataset"
    dataset_path.mkdir()
    (dataset_path / "task.toml").write_text("version = '1.0'\n", encoding="utf-8")
    dataset = HarborDataset(
        id="dataset",
        source=ResourceRef(uri=dataset_path.as_uri()),
        tasks=[Task(id="task-1")],
    )

    async def validate() -> None:
        return None

    monkeypatch.setattr(dataset, "validate", validate)

    bridge_artifacts = tmp_path / "bridge-artifacts"
    trace = bridge_artifacts / "trial-1" / "trace.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text('{"span":"bridge"}\n', encoding="utf-8")
    response_archive = tmp_path / "bridge-response.tar.gz"
    create_result_archive(_completed_result(trace), bridge_artifacts, response_archive)

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.url == httpx.URL("http://bridge.test:8765/v1/evaluations")
        assert b'"task_ids":["task-1"]' in body
        assert b"import_path" not in body
        assert b"docker.sock" not in body
        return httpx.Response(
            200,
            headers={"content-type": "application/gzip"},
            content=response_archive.read_bytes(),
        )

    monkeypatch.setenv("NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN", "test-token")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        evaluator = RemoteHarborEvaluator(
            RemoteHarborEvaluatorConfig.model_validate(
                {
                    "bridge_url": "http://bridge.test:8765",
                    "force_rerun": True,
                }
            ),
            experiment_dir=tmp_path / "experiment",
            client=client,
        )
        trials = await evaluator._run(agent, dataset, evaluator.options)

    assert trials[0].status == "completed"
    assert trials[0].trace is not None
    local_trace = Path(trials[0].trace.uri.removeprefix("file://"))
    assert local_trace.read_text(encoding="utf-8") == '{"span":"bridge"}\n'


def test_candidate_agent_import_uses_trusted_code(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path / "candidate")
    (candidate / "harbor_wrapper.py").write_text("raise RuntimeError('candidate code imported')\n", encoding="utf-8")

    with candidate_agent_import(candidate) as import_path:
        module_name, class_name = import_path.split(":")
        adapter = getattr(importlib.import_module(module_name), class_name)

        assert issubclass(adapter, TrustedCandidateAgent)
        assert adapter.candidate_dir == candidate.resolve()

    assert module_name not in sys.modules


def test_harden_task_forces_separate_verifier(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("", encoding="utf-8")
    _complete_task_files(task_dir)

    _harden_task(task_dir)

    assert HarborTask(task_dir).config.verifier.environment_mode == VerifierEnvironmentMode.SEPARATE


def test_harden_task_requires_separate_verifier_definition(tmp_path: Path) -> None:
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("", encoding="utf-8")
    (task_dir / "instruction.md").write_text("Do the task.\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="separate verifier requires tests/Dockerfile"):
        _harden_task(task_dir)


@pytest.mark.parametrize(
    ("relative_path", "content", "message"),
    [
        ("environment/compose.yaml", "services: {}\n", "Docker Compose"),
        ("task.toml", '[environment.env]\nSECRET = "${HOST_SECRET}"\n', "host environment variables"),
    ],
)
def test_harden_task_rejects_host_authority(
    tmp_path: Path,
    relative_path: str,
    content: str,
    message: str,
) -> None:
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("", encoding="utf-8")
    _complete_task_files(task_dir)
    target = task_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _harden_task(task_dir)


@pytest.mark.asyncio
async def test_bridge_service_authenticates_and_returns_materialized_result(tmp_path: Path) -> None:
    class RecordingRunner:
        requests: list[HarborBridgeRequest] = []

        async def run(
            self,
            request: HarborBridgeRequest,
            *,
            candidate_dir: Path,
            dataset_dir: Path,
            work_dir: Path,
        ) -> EvaluationResult:
            self.requests.append(request)
            assert (candidate_dir / "main.py").read_text(encoding="utf-8") == "print('candidate')\n"
            assert (dataset_dir / "task-a" / "task.toml").is_file()
            trace = work_dir / "results" / "trial-1" / "trace.jsonl"
            trace.parent.mkdir(parents=True)
            trace.write_text('{"span":"service"}\n', encoding="utf-8")
            return _completed_result(trace)

    candidate = _candidate(tmp_path / "candidate")
    dataset = tmp_path / "dataset"
    (dataset / "task-a").mkdir(parents=True)
    (dataset / "task-a" / "task.toml").write_text("", encoding="utf-8")
    candidate_archive = tmp_path / "candidate.tar.gz"
    dataset_archive = tmp_path / "dataset.tar.gz"
    create_directory_archive(candidate, candidate_archive)
    create_directory_archive(dataset, dataset_archive)

    runner = RecordingRunner()
    storage_root = tmp_path / "bridge-work"
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=storage_root,
            token="test-token-is-long-enough",
        ),
        runner=runner,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge.test") as client:
        unauthorized = await client.post("/v1/evaluations")
        assert unauthorized.status_code == 401

        with candidate_archive.open("rb") as candidate_file, dataset_archive.open("rb") as dataset_file:
            response = await client.post(
                "/v1/evaluations",
                headers={"authorization": "Bearer test-token-is-long-enough"},
                data={
                    "request": HarborBridgeRequest(
                        request_id="request-1",
                        task_ids=["task-a"],
                    ).model_dump_json()
                },
                files={
                    "candidate": ("candidate.tar.gz", candidate_file, "application/gzip"),
                    "dataset": ("dataset.tar.gz", dataset_file, "application/gzip"),
                },
            )

    assert response.status_code == 200
    response_archive = tmp_path / "response.tar.gz"
    response_archive.write_bytes(response.content)
    result = materialize_result_archive(response_archive, tmp_path / "materialized")
    assert result.trials[0].trace is not None
    trace = Path(result.trials[0].trace.uri.removeprefix("file://"))
    assert trace.read_text(encoding="utf-8") == '{"span":"service"}\n'
    assert runner.requests == [HarborBridgeRequest(request_id="request-1", task_ids=["task-a"])]
    assert list(storage_root.iterdir()) == []


@pytest.mark.asyncio
async def test_bridge_service_owns_dependency_session_lifecycle(tmp_path: Path) -> None:
    class RecordingDependencySessions:
        starts: list[HarborDependencyRequest] = []
        commands: list[tuple[str, HarborDependencyExecRequest]] = []
        stops: list[str] = []

        async def start(self, request: HarborDependencyRequest, *, task_dir: Path) -> str:
            self.starts.append(request)
            assert (task_dir / "task.toml").read_text(encoding="utf-8") == ""
            return "dependency-session-1"

        async def execute(
            self,
            session_id: str,
            request: HarborDependencyExecRequest,
        ) -> HarborDependencyExecResponse:
            self.commands.append((session_id, request))
            return HarborDependencyExecResponse(stdout="/app\n", returncode=0)

        async def stop(self, session_id: str) -> None:
            self.stops.append(session_id)

        async def close(self) -> None:
            return None

    task = tmp_path / "task-a"
    task.mkdir()
    (task / "task.toml").write_text("", encoding="utf-8")
    task_archive = tmp_path / "task.tar.gz"
    create_directory_archive(task, task_archive)

    sessions = RecordingDependencySessions()
    storage_root = tmp_path / "bridge-work"
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=storage_root,
            token="test-token-is-long-enough",
        ),
        dependency_sessions=sessions,
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"authorization": "Bearer test-token-is-long-enough"}
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge.test") as client:
        with task_archive.open("rb") as task_file:
            started = await client.post(
                "/v1/dependencies",
                headers=headers,
                data={
                    "request": HarborDependencyRequest(
                        request_id="dependency-task-a",
                        task_id="task-a",
                    ).model_dump_json()
                },
                files={"task": ("task.tar.gz", task_file, "application/gzip")},
            )
        executed = await client.post(
            "/v1/dependencies/dependency-session-1/exec",
            headers=headers,
            json=HarborDependencyExecRequest(command="pwd").model_dump(),
        )
        stopped = await client.delete(
            "/v1/dependencies/dependency-session-1",
            headers=headers,
        )

    assert started.status_code == 201
    assert started.json() == {"session_id": "dependency-session-1"}
    assert executed.status_code == 200
    assert executed.json() == {"stdout": "/app\n", "stderr": "", "returncode": 0}
    assert stopped.status_code == 204
    assert sessions.starts == [
        HarborDependencyRequest(
            request_id="dependency-task-a",
            task_id="task-a",
        )
    ]
    assert sessions.commands == [
        (
            "dependency-session-1",
            HarborDependencyExecRequest(command="pwd"),
        )
    ]
    assert sessions.stops == ["dependency-session-1"]
    assert list(storage_root.iterdir()) == []
