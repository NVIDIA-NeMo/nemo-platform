# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the plugin evaluator's task-driven backend (``evaluate_taskset`` + ``as_backend``).

Proves the "single plugin backend that matches the SDK protocol" story: the executor implements
``evaluate_taskset`` (task-driven) alongside ``evaluate_dataset`` (dataset-driven), and
is injectable into ``Evaluator`` via ``client.evaluator.as_backend()``. The conversion helpers and the
end-to-end local run path are exercised directly.
"""

from __future__ import annotations

import asyncio
import json
import re
import tarfile
from collections.abc import Callable, Sequence
from io import BytesIO
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from urllib.parse import unquote

import httpx
import pytest
from nemo_evaluator.jobs.agent_evaluate import DEFAULT_RESULT_NAME as AGENT_EVAL_RESULT_NAME
from nemo_evaluator.jobs.agent_evaluate import SUMMARY_RESULT_NAME
from nemo_evaluator.jobs.agent_spec import (
    AgentTarget,
    CodexRunnerTarget,
    FabricRunnerTarget,
    ModelTarget,
)
from nemo_evaluator.jobs.runner_targets import UnsubmittableRunnerError
from nemo_evaluator.sdk._executor import (
    _agent_eval_target_to_spec,
    _agent_task_to_input,
    _build_agent_eval_input_spec,
    _find_agent_eval_bundle,
    _read_agent_eval_bundle,
    _SyncEvaluatorPluginExecutor,
)
from nemo_evaluator.sdk.resources import Evaluator as EvaluatorResource
from nemo_evaluator_sdk.agent_eval.persistence import persist_run
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import CodexCliAgentRuntime
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.container_runtime import FabricContainerRuntime
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.runtime import FabricAgentRuntime
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.skills import AgentSkill
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.providers.docker import DockerSandboxProvider
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.enums import AgentFormat
from nemo_evaluator_sdk.execution.evaluator import Evaluator
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.values import Agent, GenericAgent, Model, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.common import SecretRef
from nemo_platform import NeMoPlatform

#: Minimal Fabric agent config: the harness is selected by ``adapter_id``, never inferred.
_FABRIC_CONFIG = {"metadata": {"name": "a"}, "harness": {"adapter_id": "nvidia.fabric.codex"}}


class _StubPlatform:
    """Minimal sync platform stub sufficient for local (in-process) agent-eval execution."""

    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "test-ws"
        self.default_headers = {"Authorization": "Bearer stub-token"}
        self.timeout = httpx.Timeout(30.0)
        self._client = MagicMock(spec=httpx.Client)


class _FakeRunner:
    """A live ``AgentTaskRunner`` the plugin has no target mapping for."""

    async def run_tasks(
        self, tasks: Sequence[AgentEvalTask], config: AgentEvalRunConfig | None = None
    ) -> list[AgentEvalTrial]:
        del tasks, config
        return []


class _SubmittingStubPlatform:
    """Platform stub whose HTTP client serves a complete agent-eval job lifecycle from memory.

    Backed by a real ``httpx.Client`` over a ``MockTransport`` so the routes the executor builds are
    genuinely exercised — a create posted to the wrong job collection fails the test rather than
    being absorbed by a mock.
    """

    def __init__(self, bundle_tarball: bytes) -> None:
        self.base_url = "http://platform.test"
        self.workspace = "test-ws"
        self.default_headers: dict[str, str] = {}
        self.timeout = httpx.Timeout(30.0)
        self.requests: list[httpx.Request] = []
        # Keyed by the result names ``AgentEvalJob`` actually saves. Every other name 404s, exactly
        # as the platform's generic ``results/{name}/download`` lookup does — asking for a result the
        # job never registered (such as "artifacts") must fail the test, not be quietly served.
        self._results = {AGENT_EVAL_RESULT_NAME: bundle_tarball, SUMMARY_RESULT_NAME: b"{}"}
        self._client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST":
            return httpx.Response(200, json={"name": "agent-eval-job-1", "spec": json.loads(request.content)["spec"]})
        if path.endswith("/status"):
            return httpx.Response(
                200,
                json={
                    "id": "job-id-1",
                    "name": "agent-eval-job-1",
                    "status": "completed",
                    "status_details": {},
                    "error_details": None,
                    "steps": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            )
        download = re.fullmatch(r".*/results/([^/]+)/download", path)
        if download:
            payload = self._results.get(unquote(download.group(1)))
            if payload is None:
                return httpx.Response(404, json={"detail": f"no result named {download.group(1)!r}"})
            return httpx.Response(200, content=payload)
        return httpx.Response(404)


def _bundle_tarball(tmp_path: Path) -> bytes:
    """Persist a real run bundle and tar it the way the job artifact route delivers one."""
    result = AgentEvalResult(
        run_id="run-1",
        tasks=[_task()],
        trials=[_trial()],
        scores=[
            AgentEvalTaskScore(
                id="s-1",
                run_id="run-1",
                task_id="task-1",
                trial_id="t-1",
                metric_type="exact_match",
                status=AgentEvalScoreStatus.COMPLETED,
            )
        ],
        summary=AgentEvalSummary(),
    )
    bundle_dir = tmp_path / "bundle" / "agent-eval"
    persist_run(result, bundle_dir)

    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        # Nested under a directory, as the Jobs result serializer packs it — the loader must find
        # the bundle by its contents rather than assuming it sits at the archive root.
        tar.add(bundle_dir, arcname="agent-eval")
    return buffer.getvalue()


def _submitting_platform(tmp_path: Path) -> _SubmittingStubPlatform:
    return _SubmittingStubPlatform(_bundle_tarball(tmp_path))


def _model() -> Model:
    return Model(url="http://model.test/v1/chat/completions", name="test-model")


def _agent() -> Agent:
    return GenericAgent(
        url="http://agent.test",
        name="test-agent",
        format=AgentFormat.GENERIC,
        body={"question": "{{item.prompt}}"},
        response_path="$.answer",
    )


def _task() -> AgentEvalTask:
    return AgentEvalTask(
        id="task-1",
        intent="Answer the question.",
        inputs={"instruction": "What is 2+2?", "domain": "math"},
        reference={"expected": "4"},
        metrics=[ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")],
        metadata={"benchmark": "demo"},
    )


def _trial() -> AgentEvalTrial:
    return AgentEvalTrial(
        id="t-1",
        task_id="task-1",
        status=AgentEvalTrialStatus.COMPLETED,
        output=AgentOutput(output_text="4"),
    )


# --- target conversion (runtime -> wire) -----------------------------------


def test_target_to_spec_maps_model_and_folds_run_config() -> None:
    config = AgentEvalRunConfig(prompt_template={"prompt": "{{item.instruction}}"}, params=RunConfigOnlineModel())
    spec = _agent_eval_target_to_spec(_model(), config)

    assert isinstance(spec, ModelTarget)
    assert spec.model.name == "test-model"
    assert spec.prompt_template == {"prompt": "{{item.instruction}}"}
    assert isinstance(spec.params, RunConfigOnlineModel)


def test_target_to_spec_maps_agent() -> None:
    spec = _agent_eval_target_to_spec(_agent(), AgentEvalRunConfig(params=RunConfigOnline()))

    assert isinstance(spec, AgentTarget)
    assert spec.agent.name == "test-agent"
    assert isinstance(spec.params, RunConfigOnline)


def test_target_to_spec_none_is_none() -> None:
    assert _agent_eval_target_to_spec(None, None) is None


def test_target_to_spec_rejects_runner_without_wire_form() -> None:
    """A runner type the plugin has no mapping for cannot be submitted."""
    with pytest.raises(UnsubmittableRunnerError, match="has no target spec"):
        _agent_eval_target_to_spec(_FakeRunner(), None)


def test_target_to_spec_serializes_codex_runner() -> None:
    """A codex runner's declarative knobs travel; its host work_root does not."""
    runtime = CodexCliAgentRuntime(model="gpt-5.5", timeout_s=900, work_root="/tmp/host-only")
    spec = _agent_eval_target_to_spec(runtime, None)

    assert spec == CodexRunnerTarget(model="gpt-5.5", timeout_s=900)


def test_target_to_spec_serializes_fabric_runner() -> None:
    runtime = FabricAgentRuntime(
        config=_FABRIC_CONFIG,
        model="openai/gpt-5.4",
        timeout_s=900,
        capture_trajectory=False,
        work_root="/tmp/host-only",
    )
    spec = _agent_eval_target_to_spec(runtime, None)

    assert isinstance(spec, FabricRunnerTarget)
    assert (spec.config, spec.model, spec.timeout_s, spec.capture_trajectory) == (
        _FABRIC_CONFIG,
        "openai/gpt-5.4",
        900,
        False,
    )
    # The host runtime selects no sandbox; that is what distinguishes it from its container sibling.
    assert spec.sandbox is None


def test_target_to_spec_serializes_fabric_container_runner() -> None:
    """The container runner names its provider and carries secrets as unresolved refs."""
    runtime = FabricContainerRuntime(
        _FABRIC_CONFIG,
        provider=DockerSandboxProvider(),
        secrets={"NVIDIA_API_KEY": SecretRef(root="nvidia-api-key")},
        image="fabric-sandbox:test",
    )
    spec = _agent_eval_target_to_spec(runtime, None)

    assert isinstance(spec, FabricRunnerTarget)
    assert spec.config == _FABRIC_CONFIG
    assert spec.sandbox is not None
    assert spec.sandbox.provider == "docker"
    assert spec.sandbox.image == "fabric-sandbox:test"
    assert spec.sandbox.secrets == {"NVIDIA_API_KEY": SecretRef(root="nvidia-api-key")}


def test_target_to_spec_container_runner_omits_resolved_secret_values() -> None:
    """Resolving secrets before submission must not leak the values into the spec."""

    class _StubResolver:
        async def resolve_secret(self, secret_ref: SecretRef) -> str:
            del secret_ref
            return "super-secret-value"

    runtime = FabricContainerRuntime(
        _FABRIC_CONFIG,
        provider=DockerSandboxProvider(),
        secrets={"NVIDIA_API_KEY": SecretRef(root="nvidia-api-key")},
    )
    asyncio.run(runtime.resolve_secrets(_StubResolver()))
    spec = _agent_eval_target_to_spec(runtime, None)

    assert "super-secret-value" not in spec.model_dump_json()


@pytest.mark.parametrize(
    "runtime_factory",
    [
        pytest.param(
            lambda skill: FabricAgentRuntime(config=_FABRIC_CONFIG).with_skill(skill),
            id="host",
        ),
        pytest.param(
            lambda skill: FabricContainerRuntime(_FABRIC_CONFIG, provider=DockerSandboxProvider()).with_skill(skill),
            id="container",
        ),
    ],
)
def test_target_to_spec_rejects_fabric_runner_with_skills(
    runtime_factory: Callable[[AgentSkill], object], tmp_path: Path
) -> None:
    """Skills have no wire form, so submitting would silently produce a skill-free arm."""
    skill_dir = tmp_path / "supercool-guidelines"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# guidelines", encoding="utf-8")

    runtime = runtime_factory(AgentSkill(name="supercool-guidelines", directory=skill_dir))

    with pytest.raises(UnsubmittableRunnerError, match="supercool-guidelines"):
        _agent_eval_target_to_spec(runtime, None)


def test_target_to_spec_rejects_codex_runner_with_unrepresentable_knob() -> None:
    """A custom codex binary has no field on the wire DTO, so it must not be dropped."""
    runtime = CodexCliAgentRuntime(model="gpt-5.5", codex_bin="/opt/custom/codex")

    with pytest.raises(UnsubmittableRunnerError, match="codex_bin"):
        _agent_eval_target_to_spec(runtime, None)


# --- task conversion (runtime -> wire) -------------------------------------


def test_task_to_input_bundles_metrics_and_narrows_inputs() -> None:
    from nemo_evaluator.shared.metric_bundles.defaults import resolve_default_metric_bundle_packager

    task = _task()
    packager = resolve_default_metric_bundle_packager(
        task.metrics, None, allow_cloudpickle_fallback=True, action="Running"
    )
    wire = _agent_task_to_input(task, metric_bundle_packager=packager)

    assert wire.id == "task-1"
    # Only wire-recognized inputs survive (``instruction``); ``domain`` is dropped.
    assert wire.inputs.instruction == "What is 2+2?"
    assert not hasattr(wire.inputs, "domain")
    assert len(wire.metrics) == 1
    assert {item.key: item.value for item in wire.metadata} == {"benchmark": "demo"}


def test_build_input_spec_carries_trials_and_run_config() -> None:
    from nemo_evaluator.shared.metric_bundles.defaults import resolve_default_metric_bundle_packager

    task = _task()
    packager = resolve_default_metric_bundle_packager(
        task.metrics, None, allow_cloudpickle_fallback=True, action="Running"
    )
    spec = _build_agent_eval_input_spec(
        tasks=[task],
        target=None,
        trials=[_trial()],
        config=AgentEvalRunConfig(parallelism=7, fail_fast=True, benchmark={"suite": "demo"}),
        metric_bundle_packager=packager,
    )

    assert spec.target is None
    assert spec.trials is not None and [t.id for t in spec.trials] == ["t-1"]
    assert spec.max_concurrent_tasks == 7
    assert spec.fail_fast is True
    assert spec.benchmark == {"suite": "demo"}


# --- bundle -> AgentEvalResult reconstruction ------------------------------


def test_read_agent_eval_bundle_rebuilds_result(tmp_path: Path) -> None:
    original = AgentEvalResult(
        run_id="run-42",
        tasks=[_task()],
        trials=[_trial()],
        scores=[
            AgentEvalTaskScore(
                id="s-1",
                run_id="run-42",
                task_id="task-1",
                trial_id="t-1",
                metric_type="exact_match",
                status=AgentEvalScoreStatus.COMPLETED,
            )
        ],
        summary=AgentEvalSummary(),
        benchmark={"suite": "demo"},
    )
    bundle_dir = tmp_path / "artifacts" / "nested" / "agent-eval"
    persist_run(original, bundle_dir)

    # The bundle is found by its contents, wherever the artifact archive nested it.
    loaded = _read_agent_eval_bundle(_find_agent_eval_bundle(tmp_path / "artifacts"), tasks=[_task()])

    assert loaded.run_id == "run-42"
    assert [t.id for t in loaded.trials] == ["t-1"]
    assert [s.id for s in loaded.scores] == ["s-1"]
    assert loaded.benchmark == {"suite": "demo"}
    # Tasks come from the caller's originals (bundle tasks don't round-trip live metrics).
    assert [t.id for t in loaded.tasks] == ["task-1"]


# --- injectable backend seam -----------------------------------------------


def test_as_backend_returns_protocol_compatible_executor_usable_by_evaluator() -> None:
    resource = EvaluatorResource(cast(NeMoPlatform, _StubPlatform()))
    backend = resource.as_backend()

    assert callable(backend.evaluate_dataset)
    assert callable(backend.evaluate_taskset)
    # Injecting it into the SDK Evaluator must be accepted (validated as a sync backend).
    Evaluator(backend)


def test_evaluate_taskset_submits_to_the_agent_evaluate_collection(tmp_path: Path) -> None:
    """The backend protocol method submits: create -> poll -> read the bundle from job artifacts."""
    platform = _submitting_platform(tmp_path)
    executor = _SyncEvaluatorPluginExecutor(platform=cast(NeMoPlatform, platform))

    result = executor.evaluate_taskset(taskset=[_task()], trials=[_trial()])

    # The create call must land on the agent-evaluate collection, not the dataset 'evaluate' one.
    create_url = str(platform.requests[0].url)
    assert create_url.endswith("/v2/workspaces/test-ws/agent-evaluate/jobs")
    # Status and result routes are scoped under the same collection, and the bundle is fetched by the
    # name the job saves it under — not a generic "artifacts" result, which agent-eval jobs never save.
    assert all("/agent-evaluate/jobs/agent-eval-job-1/" in str(request.url) for request in platform.requests[1:])
    assert any(str(request.url).endswith(f"results/{AGENT_EVAL_RESULT_NAME}/download") for request in platform.requests)
    assert isinstance(result, AgentEvalResult)
    assert [t.id for t in result.trials] == ["t-1"]
    assert [t.id for t in result.tasks] == ["task-1"]


def test_unified_evaluator_run_taskset_eval_through_plugin_backend(tmp_path: Path) -> None:
    """`Evaluator(resource.as_backend())` reaches the platform for task-driven eval."""
    resource = EvaluatorResource(cast(NeMoPlatform, _submitting_platform(tmp_path)))
    evaluator = Evaluator(resource.as_backend())

    result = evaluator.run_taskset_eval_sync(taskset=[_task()], trials=[_trial()])

    assert isinstance(result, AgentEvalResult)
    assert [t.id for t in result.trials] == ["t-1"]
