# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
import io
import json
import sys
import tarfile
from pathlib import Path
from urllib.parse import parse_qs

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
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    ENVELOPE_DESCRIPTOR_FILENAME,
    EnvelopeTaskSelection,
    TaskDataSlot,
    TaskEnvelopePolicy,
    TrustedEnvelopeCatalog,
    register_dataset_envelope,
    transport_tree_digest,
)
from nemo_experimentalist_plugin.harbor_bridge.preparation import prepare_trusted_inputs
from nemo_experimentalist_plugin.harbor_bridge.runner import _harden_task
from nemo_experimentalist_plugin.harbor_bridge.service import HarborBridgeSettings, create_app
from nemo_experimentalist_plugin.harbor_bridge.trusted_agent import (
    TrustedCandidateAgent,
    candidate_agent_import,
)
from nemo_experimentalist_plugin.resolve import build_effective_experiment_plan
from pydantic import ValidationError

_DIGEST = "sha256:" + "a" * 64


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
    environment_dir = task_dir / "environment"
    environment_dir.mkdir()
    (environment_dir / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    tests_dir = task_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "Dockerfile").write_text("FROM ubuntu:24.04\n", encoding="utf-8")
    (tests_dir / "test.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")


def _registered_dataset(tmp_path: Path, *, mutable: bool = False):
    source = tmp_path / "trusted-source"
    task_dir = source / "task-1"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        'schema_version = "1.1"\n[task]\nname = "example/task-1"\n',
        encoding="utf-8",
    )
    _complete_task_files(task_dir)
    if mutable:
        (task_dir / "nemo-task-envelope.json").write_text(
            TaskEnvelopePolicy(
                task_data=[
                    TaskDataSlot(
                        path="instruction.md",
                        media_type="text/plain",
                        max_bytes=4096,
                    )
                ],
                verifier_paths=["tests/test.sh", "tests/metrics"],
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
    catalog_root = tmp_path / "catalog"
    registered = register_dataset_envelope(source, catalog_root=catalog_root, name="test")
    return registered, TrustedEnvelopeCatalog(catalog_root)


def test_bridge_contract_rejects_execution_authority() -> None:
    with pytest.raises(ValidationError, match="import_path"):
        HarborBridgeRequest.model_validate(
            {
                "request_id": "request-1",
                "envelope_id": "envelope-1",
                "envelope_digest": _DIGEST,
                "tasks": [{"task_id": "task-1", "base_task_id": "task-1"}],
                "candidate_digest": _DIGEST,
                "import_path": "candidate:Agent",
            }
        )


def test_dependency_contract_rejects_docker_authority() -> None:
    with pytest.raises(ValidationError, match="environment_type"):
        HarborDependencyRequest.model_validate(
            {
                "request_id": "dependency-task-1",
                "envelope_id": "envelope-1",
                "envelope_digest": _DIGEST,
                "task_id": "task-1",
                "base_task_id": "task-1",
                "environment_type": "docker",
            }
        )


@pytest.mark.parametrize(
    "tasks",
    [
        [
            {"task_id": "task-a", "base_task_id": "task-a"},
            {"task_id": "task-a", "base_task_id": "task-a"},
        ],
        [{"task_id": "../escape", "base_task_id": "task-a"}],
        [{"task_id": "task/a", "base_task_id": "task-a"}],
    ],
)
def test_bridge_contract_rejects_unsafe_task_ids(tasks: list[dict[str, str]]) -> None:
    with pytest.raises(ValidationError, match="tasks|task_id"):
        HarborBridgeRequest.model_validate(
            {
                "request_id": "request-1",
                "envelope_id": "envelope-1",
                "envelope_digest": _DIGEST,
                "tasks": tasks,
                "candidate_digest": _DIGEST,
            }
        )


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


def test_trusted_envelope_materializes_only_declared_overlays(tmp_path: Path) -> None:
    registered, catalog = _registered_dataset(tmp_path, mutable=True)
    overlay = tmp_path / "overlay"
    task_overlay = overlay / "derived-task"
    (task_overlay / "tests").mkdir(parents=True)
    (task_overlay / "instruction.md").write_text("Derived instruction.\n", encoding="utf-8")
    (task_overlay / "tests" / "test.sh").write_text("#!/bin/sh\necho metric\n", encoding="utf-8")

    output = catalog.materialize(
        envelope_id=registered.manifest.envelope_id,
        envelope_digest=registered.manifest.envelope_digest,
        selections=[EnvelopeTaskSelection(task_id="derived-task", base_task_id="task-1")],
        destination=tmp_path / "materialized",
        overlay_dir=overlay,
    )
    task = output / "derived-task"

    assert (task / "instruction.md").read_text(encoding="utf-8") == "Derived instruction.\n"
    assert (task / "tests" / "test.sh").read_text(encoding="utf-8") == "#!/bin/sh\necho metric\n"
    assert (task / "tests" / "Dockerfile").read_text(encoding="utf-8") == "FROM ubuntu:24.04\n"
    assert not (task / ENVELOPE_DESCRIPTOR_FILENAME).exists()
    task_config = HarborTask(task).config.task
    assert task_config is not None
    assert task_config.name == "example/task-1__derived-task"


def test_trusted_envelope_detects_catalog_tampering(tmp_path: Path) -> None:
    registered, catalog = _registered_dataset(tmp_path)
    (registered.dataset_path / "task-1" / "environment" / "Dockerfile").write_text(
        "FROM tampered\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="content changed after registration"):
        catalog.materialize(
            envelope_id=registered.manifest.envelope_id,
            envelope_digest=registered.manifest.envelope_digest,
            selections=[EnvelopeTaskSelection(task_id="task-1", base_task_id="task-1")],
            destination=tmp_path / "materialized",
        )


def test_trusted_envelope_registration_rejects_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "task.toml").write_text(
        'schema_version = "1.1"\n[task]\nname = "example/task"\n',
        encoding="utf-8",
    )
    _complete_task_files(source)
    (source / "linked-Dockerfile").symlink_to(source / "environment" / "Dockerfile")

    with pytest.raises(ValueError, match="symbolic link"):
        register_dataset_envelope(source, catalog_root=tmp_path / "catalog", name="unsafe")


def test_tau_template_is_a_trusted_multi_container_envelope(tmp_path: Path) -> None:
    template = Path(__file__).parents[1] / "examples" / "tau2-nemo-oo-agent" / "dataset" / "template" / "task_template"
    registered = register_dataset_envelope(
        template,
        catalog_root=tmp_path / "catalog",
        name="tau-template",
    )
    base_task_id = registered.manifest.tasks[0].task_id
    task = (
        TrustedEnvelopeCatalog(tmp_path / "catalog").materialize(
            envelope_id=registered.manifest.envelope_id,
            envelope_digest=registered.manifest.envelope_digest,
            selections=[EnvelopeTaskSelection(task_id="tau-derived", base_task_id=base_task_id)],
            destination=tmp_path / "materialized",
        )
        / "tau-derived"
    )

    _harden_task(task)

    assert (task / "environment" / "docker-compose.yaml").is_file()
    assert HarborTask(task).config.environment.mcp_servers[0].name == "tau3-runtime"
    assert HarborTask(task).config.verifier.environment_mode == VerifierEnvironmentMode.SEPARATE


def test_tau_envelope_rejects_invalid_typed_task_data(tmp_path: Path) -> None:
    template = Path(__file__).parents[1] / "examples" / "tau2-nemo-oo-agent" / "dataset" / "template" / "task_template"
    registered = register_dataset_envelope(
        template,
        catalog_root=tmp_path / "catalog",
        name="tau-template",
    )
    base_task_id = registered.manifest.tasks[0].task_id
    overlay = tmp_path / "overlay"
    invalid = overlay / "tau-derived" / "environment" / "runtime-server" / "task_config.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        TrustedEnvelopeCatalog(tmp_path / "catalog").materialize(
            envelope_id=registered.manifest.envelope_id,
            envelope_digest=registered.manifest.envelope_digest,
            selections=[EnvelopeTaskSelection(task_id="tau-derived", base_task_id=base_task_id)],
            destination=tmp_path / "materialized",
            overlay_dir=overlay,
        )


@pytest.mark.asyncio
async def test_host_prepares_trusted_inputs_without_a_sandbox_registration_api(tmp_path: Path) -> None:
    agent = _candidate(tmp_path / "agent")
    train_source = tmp_path / "train-source"
    validation_source = tmp_path / "validation-source"
    for source, task_name in ((train_source, "train-task"), (validation_source, "validation-task")):
        task = source / task_name
        task.mkdir(parents=True)
        (task / "task.toml").write_text(
            f'schema_version = "1.1"\n[task]\nname = "example/{task_name}"\n',
            encoding="utf-8",
        )
        _complete_task_files(task)
    plan = build_effective_experiment_plan(
        profile=None,
        agent=str(agent),
        no_insight=True,
        train_dataset=str(train_source),
        validation_dataset=str(validation_source),
    )

    prepared = await prepare_trusted_inputs(plan, workspace=tmp_path)

    assert prepared.catalog_root.is_dir()
    assert (prepared.train_dataset / ENVELOPE_DESCRIPTOR_FILENAME).is_file()
    assert (prepared.validation_dataset / ENVELOPE_DESCRIPTOR_FILENAME).is_file()
    assert prepared.task_template is None
    assert list((prepared.catalog_root / "envelopes").glob("*/manifest.json"))


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
    registered, _catalog = _registered_dataset(tmp_path)
    task_dir = registered.dataset_path / "task-1"
    dataset = HarborDataset(
        id="dataset",
        source=ResourceRef(uri=registered.dataset_path.as_uri()),
        tasks=[
            Task(
                id="task-1",
                uri=task_dir.as_uri(),
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
    assert runtime.envelope_id == registered.manifest.envelope_id
    assert runtime.envelope_digest == registered.manifest.envelope_digest
    assert runtime.base_task_id == "task-1"
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
            payload = json.loads(parse_qs(body.decode())["request"][0])
            assert payload["task_id"] == "task-1"
            assert payload["base_task_id"] == "task-1"
            assert payload["envelope_id"] == "envelope-1"
            assert b'name="task"' not in body
            assert b"docker.sock" not in body
            return httpx.Response(
                201,
                json={
                    "session_id": "dependency-session-1",
                    "capability_token": "session-capability-token",
                },
            )
        if request.url.path == "/v1/dependencies/dependency-session-1/exec":
            assert request.headers["x-nemo-dependency-capability"] == "session-capability-token"
            assert b'"command":"pwd"' in body
            return httpx.Response(
                200,
                json={"stdout": "/app\n", "stderr": "", "returncode": 0},
            )
        if request.url.path == "/v1/dependencies/dependency-session-1":
            assert request.headers["x-nemo-dependency-capability"] == "session-capability-token"
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BRIDGE_TOKEN", "dependency-token")
    runtime = RemoteHarborDependencyRuntime(
        task_id="task-1",
        base_task_id="task-1",
        envelope_id="envelope-1",
        envelope_digest=_DIGEST,
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
        HarborDependencyRequest(
            request_id="dependency-task-a",
            envelope_id="envelope-1",
            envelope_digest=_DIGEST,
            task_id="task-a",
            base_task_id="task-a",
        ),
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
    registered, _catalog = _registered_dataset(tmp_path)
    dataset_path = registered.dataset_path
    task_path = dataset_path / "task-1"
    dataset = HarborDataset(
        id="dataset",
        source=ResourceRef(uri=dataset_path.as_uri()),
        tasks=[Task(id="task-1", uri=task_path.as_uri())],
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
        assert b'"tasks":[{"task_id":"task-1","base_task_id":"task-1"}]' in body
        assert b'"envelope_id":"' + registered.manifest.envelope_id.encode() + b'"' in body
        assert b'name="dataset"' not in body
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
    ("relative_path", "content"),
    [
        ("environment/compose.yaml", "services: {}\n"),
        ("task.toml", '[environment.env]\nSECRET = "${HOST_SECRET}"\n'),
    ],
)
def test_harden_task_accepts_host_registered_runtime_configuration(
    tmp_path: Path,
    relative_path: str,
    content: str,
) -> None:
    task_dir = tmp_path / "task-a"
    task_dir.mkdir()
    (task_dir / "task.toml").write_text("", encoding="utf-8")
    _complete_task_files(task_dir)
    target = task_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    _harden_task(task_dir)


def test_trusted_envelope_rejects_runtime_overlay(tmp_path: Path) -> None:
    registered, catalog = _registered_dataset(tmp_path, mutable=True)
    overlay = tmp_path / "overlay"
    malicious = overlay / "task-derived" / "environment" / "Dockerfile"
    malicious.parent.mkdir(parents=True)
    malicious.write_text("FROM malicious\n", encoding="utf-8")

    with pytest.raises(ValueError, match="runtime-control file"):
        catalog.materialize(
            envelope_id=registered.manifest.envelope_id,
            envelope_digest=registered.manifest.envelope_digest,
            selections=[EnvelopeTaskSelection(task_id="task-derived", base_task_id="task-1")],
            destination=tmp_path / "materialized",
            overlay_dir=overlay,
        )


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
            assert (dataset_dir / "task-1" / "task.toml").is_file()
            trace = work_dir / "results" / "trial-1" / "trace.jsonl"
            trace.parent.mkdir(parents=True)
            trace.write_text('{"span":"service"}\n', encoding="utf-8")
            return _completed_result(trace)

    candidate = _candidate(tmp_path / "candidate")
    registered, catalog = _registered_dataset(tmp_path)
    candidate_archive = tmp_path / "candidate.tar.gz"
    create_directory_archive(candidate, candidate_archive)

    runner = RecordingRunner()
    storage_root = tmp_path / "bridge-work"
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=storage_root,
            catalog_root=catalog.root,
            token="test-token-is-long-enough",
        ),
        runner=runner,
        catalog=catalog,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge.test") as client:
        unauthorized = await client.post("/v1/evaluations")
        assert unauthorized.status_code == 401

        with candidate_archive.open("rb") as candidate_file:
            response = await client.post(
                "/v1/evaluations",
                headers={"authorization": "Bearer test-token-is-long-enough"},
                data={
                    "request": HarborBridgeRequest(
                        request_id="request-1",
                        envelope_id=registered.manifest.envelope_id,
                        envelope_digest=registered.manifest.envelope_digest,
                        tasks=[EnvelopeTaskSelection(task_id="task-1", base_task_id="task-1")],
                        candidate_digest=transport_tree_digest(candidate),
                    ).model_dump_json()
                },
                files={
                    "candidate": ("candidate.tar.gz", candidate_file, "application/gzip"),
                },
            )
        with candidate_archive.open("rb") as candidate_file, candidate_archive.open("rb") as legacy_dataset:
            legacy = await client.post(
                "/v1/evaluations",
                headers={"authorization": "Bearer test-token-is-long-enough"},
                data={
                    "request": HarborBridgeRequest(
                        request_id="request-legacy",
                        envelope_id=registered.manifest.envelope_id,
                        envelope_digest=registered.manifest.envelope_digest,
                        tasks=[EnvelopeTaskSelection(task_id="task-1", base_task_id="task-1")],
                        candidate_digest=transport_tree_digest(candidate),
                    ).model_dump_json()
                },
                files={
                    "candidate": ("candidate.tar.gz", candidate_file, "application/gzip"),
                    "dataset": ("dataset.tar.gz", legacy_dataset, "application/gzip"),
                },
            )

    assert response.status_code == 200
    assert legacy.status_code == 422
    assert "dataset" in legacy.text
    response_archive = tmp_path / "response.tar.gz"
    response_archive.write_bytes(response.content)
    result = materialize_result_archive(response_archive, tmp_path / "materialized")
    assert result.trials[0].trace is not None
    trace = Path(result.trials[0].trace.uri.removeprefix("file://"))
    assert trace.read_text(encoding="utf-8") == '{"span":"service"}\n'
    assert runner.requests == [
        HarborBridgeRequest(
            request_id="request-1",
            envelope_id=registered.manifest.envelope_id,
            envelope_digest=registered.manifest.envelope_digest,
            tasks=[EnvelopeTaskSelection(task_id="task-1", base_task_id="task-1")],
            candidate_digest=transport_tree_digest(candidate),
        )
    ]
    assert list(storage_root.iterdir()) == []


@pytest.mark.asyncio
async def test_bridge_service_owns_dependency_session_lifecycle(tmp_path: Path) -> None:
    class RecordingDependencySessions:
        starts: list[HarborDependencyRequest] = []
        commands: list[tuple[str, HarborDependencyExecRequest]] = []
        stops: list[str] = []

        async def start(self, request: HarborDependencyRequest, *, task_dir: Path) -> str:
            self.starts.append(request)
            assert (task_dir / "task.toml").is_file()
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

    registered, catalog = _registered_dataset(tmp_path)
    legacy_task_archive = tmp_path / "legacy-task.tar.gz"
    create_directory_archive(registered.dataset_path / "task-1", legacy_task_archive)

    sessions = RecordingDependencySessions()
    storage_root = tmp_path / "bridge-work"
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=storage_root,
            catalog_root=catalog.root,
            token="test-token-is-long-enough",
        ),
        dependency_sessions=sessions,
        catalog=catalog,
    )
    transport = httpx.ASGITransport(app=app)
    headers = {"authorization": "Bearer test-token-is-long-enough"}
    async with httpx.AsyncClient(transport=transport, base_url="http://bridge.test") as client:
        started = await client.post(
            "/v1/dependencies",
            headers=headers,
            data={
                "request": HarborDependencyRequest(
                    request_id="dependency-task-a",
                    envelope_id=registered.manifest.envelope_id,
                    envelope_digest=registered.manifest.envelope_digest,
                    task_id="task-1",
                    base_task_id="task-1",
                ).model_dump_json()
            },
        )
        with legacy_task_archive.open("rb") as legacy_task:
            legacy = await client.post(
                "/v1/dependencies",
                headers=headers,
                data={
                    "request": HarborDependencyRequest(
                        request_id="dependency-legacy",
                        envelope_id=registered.manifest.envelope_id,
                        envelope_digest=registered.manifest.envelope_digest,
                        task_id="task-1",
                        base_task_id="task-1",
                    ).model_dump_json()
                },
                files={"task": ("task.tar.gz", legacy_task, "application/gzip")},
            )
        missing = await client.post(
            "/v1/dependencies/dependency-session-1/exec",
            headers=headers,
            json=HarborDependencyExecRequest(command="pwd").model_dump(),
        )
        denied = await client.post(
            "/v1/dependencies/dependency-session-1/exec",
            headers={**headers, "X-Nemo-Dependency-Capability": "wrong-capability-token"},
            json=HarborDependencyExecRequest(command="pwd").model_dump(),
        )
        capability = started.json()["capability_token"]
        executed = await client.post(
            "/v1/dependencies/dependency-session-1/exec",
            headers={**headers, "X-Nemo-Dependency-Capability": capability},
            json=HarborDependencyExecRequest(command="pwd").model_dump(),
        )
        stopped = await client.delete(
            "/v1/dependencies/dependency-session-1",
            headers={**headers, "X-Nemo-Dependency-Capability": capability},
        )

    assert started.status_code == 201
    assert legacy.status_code == 422
    assert "task" in legacy.text
    assert started.json()["session_id"] == "dependency-session-1"
    assert len(started.json()["capability_token"]) >= 16
    assert missing.status_code == 403
    assert denied.status_code == 403
    assert executed.status_code == 200
    assert executed.json() == {"stdout": "/app\n", "stderr": "", "returncode": 0}
    assert stopped.status_code == 204
    assert sessions.starts == [
        HarborDependencyRequest(
            request_id="dependency-task-a",
            envelope_id=registered.manifest.envelope_id,
            envelope_digest=registered.manifest.envelope_digest,
            task_id="task-1",
            base_task_id="task-1",
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
