# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the agent-evaluation executor behind ``client.evaluator.evaluate``."""

from __future__ import annotations

import io
import json
import tarfile
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_evaluator.jobs.agent_spec import AgentEvalTaskInput, AgentTarget, ModelTarget
from nemo_evaluator.sdk._agent_eval_bundle import assemble_result, read_bundle
from nemo_evaluator.sdk._agent_eval_executor import (
    _AsyncAgentEvalExecutor,
    _SyncAgentEvalExecutor,
    build_spec,
)
from nemo_evaluator.sdk.resources import AsyncEvaluator, Evaluator
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundlePackagerPolicyError
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.enums import AgentFormat
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.protocol import (
    Metric,
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)
from nemo_evaluator_sdk.values import (
    GenericAgent,
    Model,
    RunConfigOnline,
    RunConfigOnlineModel,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from pytest_mock import MockerFixture

_RUN_ID = "run-abc"
_MODEL = Model(url="https://model.test/v1", name="model-a")
_AGENT = GenericAgent(
    url="https://agent.test/invoke",
    name="my-agent",
    format=AgentFormat.GENERIC,
    body={"question": "{{task.inputs.instruction}}"},
    response_path="$.answer",
)


class _SyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "platform-ws"
        self.default_headers = {"Authorization": "Bearer sync-platform-token"}
        self.timeout = httpx.Timeout(42.0)
        self._client = MagicMock(spec=httpx.Client)


class _AsyncPlatform:
    def __init__(self) -> None:
        self.base_url = "http://test:8000"
        self.workspace = "platform-ws"
        self.default_headers = {"Authorization": "Bearer platform-token"}
        self.timeout = httpx.Timeout(43.0)
        self._client = AsyncMock(spec=httpx.AsyncClient)


class _CustomMetric:
    """Protocol-satisfying metric outside MetricsUnion: cloudpickle is the only way to bundle it."""

    type = "custom-score"
    description = "custom metric"
    labels: dict[str, str] = {}

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        del input
        return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])


def _metric() -> Metric:
    return ExactMatchMetric(reference="{{task.reference.answer}}", candidate="{{trial.output.output_text}}")


def _task(task_id: str = "task-1", **overrides: Any) -> AgentEvalTask:
    fields: dict[str, Any] = {
        "id": task_id,
        "intent": "answer the question",
        "inputs": {"instruction": "What is the capital of France?"},
        "reference": {"answer": "Paris"},
        "metrics": [_metric()],
    }
    fields.update(overrides)
    return AgentEvalTask(**fields)


def _bundle_bytes(**overrides: str) -> bytes:
    """Build a run-bundle tarball with a minimal one-task, one-trial run."""
    files = {
        "run.json": json.dumps({"run_id": _RUN_ID}),
        "trials.jsonl": json.dumps(
            {"id": "trial-1", "task_id": "task-1", "status": "completed", "output": {"output_text": "Paris"}}
        ),
        "scores.jsonl": json.dumps(
            {
                "id": "score-1",
                "run_id": _RUN_ID,
                "task_id": "task-1",
                "trial_id": "trial-1",
                "metric_type": "exact-match",
                "status": "completed",
                "outputs": [{"name": "exact-match", "value": 1.0}],
            }
        ),
        "summary.json": json.dumps({}),
        "metadata.json": json.dumps({}),
        "tasks.jsonl": json.dumps({"id": "task-1", "metrics": [{"type": "exact-match"}]}),
    }
    files.update(overrides)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, payload in files.items():
            raw = payload.encode("utf-8")
            info = tarfile.TarInfo(name=f"agent-eval-results/{name}")
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return buffer.getvalue()


class TestBuildSpec:
    def test_packages_task_metrics_inline(self) -> None:
        spec = build_spec(taskset=[_task()], target=_MODEL, trials=None, config=None, metric_bundle_packager=None)

        # Everything is sent inline; a TasksetRef would mean a stored entity, which is out of scope.
        assert isinstance(spec.tasks, list)
        task = spec.tasks[0]
        assert isinstance(task, AgentEvalTaskInput)
        assert task.id == "task-1"
        assert task.inputs.instruction == "What is the capital of France?"
        assert task.reference == {"answer": "Paris"}
        assert len(task.metrics) == 1

    def test_rejects_an_empty_taskset(self) -> None:
        with pytest.raises(ValueError, match="at least one task"):
            build_spec(taskset=[], target=_MODEL, trials=None, config=None, metric_bundle_packager=None)

    def test_rejects_task_inputs_the_wire_schema_cannot_carry(self) -> None:
        task = _task(inputs={"instruction": "do it", "context": "extra"})

        with pytest.raises(ValueError, match="cannot be submitted with inputs \\['context'\\]"):
            build_spec(taskset=[task], target=_MODEL, trials=None, config=None, metric_bundle_packager=None)

    @pytest.mark.parametrize("inputs", [{}, {"instruction": ""}, {"instruction": None}])
    def test_rejects_a_task_with_no_instruction(self, inputs: dict[str, Any]) -> None:
        """The wire schema allows a null instruction; a job that reaches the agent with one is waste."""
        task = _task(inputs=inputs)

        with pytest.raises(ValueError, match="has no 'instruction' input"):
            build_spec(taskset=[task], target=_MODEL, trials=None, config=None, metric_bundle_packager=None)

    def test_rejects_model_target_carrying_agent_params(self) -> None:
        config = AgentEvalRunConfig(params=RunConfigOnline(parallelism=9))

        with pytest.raises(TypeError, match="Model target requires RunConfigOnlineModel params"):
            build_spec(taskset=[_task()], target=_MODEL, trials=None, config=config, metric_bundle_packager=None)

    def test_rejects_agent_target_carrying_model_params(self) -> None:
        """``RunConfigOnlineModel`` subclasses ``RunConfigOnline``, so this needs an exact-type check."""
        config = AgentEvalRunConfig(params=RunConfigOnlineModel(parallelism=9))

        with pytest.raises(TypeError, match="GenericAgent target requires RunConfigOnline params"):
            build_spec(taskset=[_task()], target=_AGENT, trials=None, config=config, metric_bundle_packager=None)

    def test_rejects_non_string_task_metadata(self) -> None:
        task = _task(metadata={"attempt": 3})

        with pytest.raises(ValueError, match="metadata 'attempt' is int"):
            build_spec(taskset=[task], target=_MODEL, trials=None, config=None, metric_bundle_packager=None)

    def test_requires_explicit_opt_in_for_a_cloudpickled_metric(self) -> None:
        task = _task(metrics=[cast(Metric, _CustomMetric())])

        with pytest.raises(MetricBundlePackagerPolicyError, match="requires an explicit metric_bundle_packager"):
            build_spec(taskset=[task], target=_MODEL, trials=None, config=None, metric_bundle_packager=None)

    def test_config_drives_run_level_settings(self) -> None:
        config = AgentEvalRunConfig(parallelism=7, fail_fast=True, labels={"suite": "smoke"})

        spec = build_spec(taskset=[_task()], target=_MODEL, trials=None, config=config, metric_bundle_packager=None)

        assert spec.max_concurrent_tasks == 7
        assert spec.fail_fast is True
        assert spec.labels == {"suite": "smoke"}

    def test_defaults_run_level_settings_without_a_config(self) -> None:
        spec = build_spec(taskset=[_task()], target=_MODEL, trials=None, config=None, metric_bundle_packager=None)

        assert spec.max_concurrent_tasks == 4
        assert spec.fail_fast is False
        assert spec.labels == {}

    def test_model_target_carries_the_request_shape_from_the_run_config(self) -> None:
        """Prompt template and inference params live on the config SDK-side, on the target wire-side."""
        model = Model(url="https://model.test/v1", name="model-a")
        params = RunConfigOnlineModel(parallelism=2)
        config = AgentEvalRunConfig(prompt_template="{{task.inputs.instruction}}", params=params)

        spec = build_spec(taskset=[_task()], target=model, trials=None, config=config, metric_bundle_packager=None)

        assert isinstance(spec.target, ModelTarget)
        assert spec.target.model == model
        assert spec.target.prompt_template == "{{task.inputs.instruction}}"
        assert spec.target.params == params

    def test_agent_target_forwards_online_params(self) -> None:
        params = RunConfigOnline(parallelism=3)

        spec = build_spec(
            taskset=[_task()],
            target=_AGENT,
            trials=None,
            config=AgentEvalRunConfig(params=params),
            metric_bundle_packager=None,
        )

        assert isinstance(spec.target, AgentTarget)
        assert spec.target.params == params

    def test_rejects_an_unsupported_target(self) -> None:
        with pytest.raises(TypeError, match="unsupported agent-evaluation target"):
            build_spec(
                taskset=[_task()],
                target=cast(Any, object()),
                trials=None,
                config=None,
                metric_bundle_packager=None,
            )


class TestReadBundle:
    def test_reads_wanted_files_and_ignores_the_rest(self) -> None:
        contents = read_bundle(_bundle_bytes())

        assert set(contents) == {"run.json", "trials.jsonl", "scores.jsonl", "summary.json", "metadata.json"}

    def test_matches_on_base_name_so_a_traversal_path_cannot_escape(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            raw = b'{"run_id": "run-abc"}'
            info = tarfile.TarInfo(name="../../../../etc/run.json")
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))

        contents = read_bundle(buffer.getvalue())

        # Read into memory under its base name; no path was ever used.
        assert contents == {"run.json": '{"run_id": "run-abc"}'}


class TestAssembleResult:
    def test_rebuilds_the_result_from_the_bundle_and_the_submitted_tasks(self) -> None:
        tasks = [_task()]

        result = assemble_result(read_bundle(_bundle_bytes()), tasks=tasks, job_name="job-1")

        assert isinstance(result, AgentEvalResult)
        assert result.run_id == _RUN_ID
        assert [trial.id for trial in result.trials] == ["trial-1"]
        assert [score.id for score in result.scores] == ["score-1"]

    def test_takes_tasks_from_the_caller_not_the_bundle(self) -> None:
        """A persisted task's metrics are descriptors; the caller's live ``Metric`` objects survive."""
        tasks = [_task()]

        result = assemble_result(read_bundle(_bundle_bytes()), tasks=tasks, job_name="job-1")

        assert result.tasks[0] is tasks[0]
        assert isinstance(result.tasks[0].metrics[0], ExactMatchMetric)

    def test_falls_back_to_the_job_name_when_the_bundle_has_no_run_id(self) -> None:
        contents = read_bundle(_bundle_bytes(**{"run.json": json.dumps({})}))

        assert assemble_result(contents, tasks=[_task()], job_name="job-1").run_id == "job-1"

    @pytest.mark.parametrize("missing", ["run.json", "trials.jsonl", "scores.jsonl", "summary.json", "metadata.json"])
    def test_names_the_bundle_file_it_could_not_find(self, missing: str) -> None:
        contents = {name: payload for name, payload in read_bundle(_bundle_bytes()).items() if name != missing}

        with pytest.raises(ValueError, match=f"job 'job-1' has no {missing}"):
            assemble_result(contents, tasks=[_task()], job_name="job-1")


def _status(status: str, **extra: Any) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/status"),
        json={"status": status, **extra},
    )


def _created() -> httpx.Response:
    return httpx.Response(
        201,
        request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/agent-evaluate/jobs"),
        json={"name": "job-123", "status": "created"},
    )


def _summary_response() -> httpx.Response:
    return httpx.Response(200, request=httpx.Request("GET", "http://test:8000/summary"), json={})


def _bundle_response() -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("GET", "http://test:8000/download"),
        content=_bundle_bytes(),
    )


class TestSyncExecutor:
    def test_creates_the_job_and_returns_a_handle(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        executor = _SyncAgentEvalExecutor(platform=cast(NeMoPlatform, platform))

        job = executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")

        # submit creates and returns; nothing is polled until the caller waits.
        assert job.name == "job-123"
        platform._client.get.assert_not_called()
        create_url = platform._client.post.call_args.args[0]
        assert create_url.endswith("/v2/workspaces/ws/agent-evaluate/jobs")
        assert platform._client.post.call_args.kwargs["json"]["spec"]["tasks"][0]["id"] == "task-1"

    def test_handle_waits_then_rebuilds_the_result(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("completed"), _bundle_response()]
        executor = _SyncAgentEvalExecutor(platform=cast(NeMoPlatform, platform))

        job = executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")
        job.wait_until_done()
        result = job.get_result()

        assert result.run_id == _RUN_ID

    def test_keeps_polling_until_the_job_is_terminal(self, mocker: MockerFixture) -> None:
        sleep = mocker.patch("nemo_evaluator.sdk.agent_eval_job_resources.time.sleep")
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("running"), _status("running"), _status("completed")]
        executor = _SyncAgentEvalExecutor(platform=cast(NeMoPlatform, platform))

        executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws").wait_until_done()

        assert sleep.call_count == 2

    def test_raises_with_the_error_details_when_the_job_fails(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("failed", error_details="metric blew up")]
        executor = _SyncAgentEvalExecutor(platform=cast(NeMoPlatform, platform))

        with pytest.raises(RuntimeError, match="finished with status 'failed': metric blew up"):
            executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws").wait_until_done()

    def test_raises_when_the_create_response_carries_no_job_name(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = httpx.Response(
            201,
            request=httpx.Request("POST", "http://test:8000/apis/evaluator/v2/workspaces/ws/agent-evaluate/jobs"),
            json={"status": "created"},
        )
        executor = _SyncAgentEvalExecutor(platform=cast(NeMoPlatform, platform))

        with pytest.raises(ValueError, match="carried no job name"):
            executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")

    def test_defaults_to_the_platform_workspace(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        executor = _SyncAgentEvalExecutor(platform=cast(NeMoPlatform, platform))

        executor.evaluate(taskset=[_task()], target=_MODEL)

        assert platform._client.post.call_args.args[0].endswith("/v2/workspaces/platform-ws/agent-evaluate/jobs")


class TestAsyncExecutor:
    @pytest.mark.asyncio
    async def test_creates_polls_and_returns_the_completed_result(self) -> None:
        platform = _AsyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("completed"), _bundle_response()]
        executor = _AsyncAgentEvalExecutor(platform=cast(AsyncNeMoPlatform, platform))

        job = await executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")
        await job.wait_until_done()
        result = await job.get_result()

        assert result.run_id == _RUN_ID
        assert platform._client.post.call_args.args[0].endswith("/v2/workspaces/ws/agent-evaluate/jobs")

    @pytest.mark.asyncio
    async def test_keeps_polling_until_the_job_is_terminal(self, mocker: MockerFixture) -> None:
        sleep = mocker.patch("nemo_evaluator.sdk.agent_eval_job_resources.asyncio.sleep", new_callable=AsyncMock)
        platform = _AsyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("running"), _status("completed")]
        executor = _AsyncAgentEvalExecutor(platform=cast(AsyncNeMoPlatform, platform))

        job = await executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")
        await job.wait_until_done()

        assert sleep.await_count == 1

    @pytest.mark.asyncio
    async def test_raises_with_the_error_details_when_the_job_fails(self) -> None:
        platform = _AsyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("cancelled", error_details="stopped by user")]
        executor = _AsyncAgentEvalExecutor(platform=cast(AsyncNeMoPlatform, platform))

        job = await executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")
        with pytest.raises(RuntimeError, match="finished with status 'cancelled': stopped by user"):
            await job.wait_until_done()


class TestResourceEvaluate:
    """``evaluate`` is the resource's taskset entrypoint; it holds no logic of its own."""

    def test_sync_resource_forwards_to_the_executor(self, mocker: MockerFixture) -> None:
        resource = Evaluator(cast(NeMoPlatform, _SyncPlatform()))
        submit = mocker.patch.object(resource._agent_eval_executor, "evaluate")
        tasks = [_task()]
        config = AgentEvalRunConfig(parallelism=2)

        resource.evaluate(taskset=tasks, target=_MODEL, config=config, workspace="ws")

        # Only the seam that was supplied is forwarded; the other is not mentioned at all.
        submit.assert_called_once_with(
            taskset=tasks,
            target=_MODEL,
            config=config,
            metric_bundle_packager=None,
            workspace="ws",
        )

    @pytest.mark.asyncio
    async def test_async_resource_forwards_to_the_executor(self, mocker: MockerFixture) -> None:
        resource = AsyncEvaluator(cast(AsyncNeMoPlatform, _AsyncPlatform()))
        submit = mocker.patch.object(resource._agent_eval_executor, "evaluate", new_callable=AsyncMock)
        tasks = [_task()]

        await resource.evaluate(taskset=tasks, target=_MODEL)

        submit.assert_awaited_once_with(
            taskset=tasks,
            target=_MODEL,
            config=None,
            metric_bundle_packager=None,
            workspace=None,
        )

    def test_sync_resource_returns_a_handle_that_yields_the_result(self) -> None:
        """End to end through the resource: a handle, then the finished result."""
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("completed"), _bundle_response()]
        resource = Evaluator(cast(NeMoPlatform, platform))

        job = resource.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")
        job.wait_until_done()
        result = job.get_result()

        assert isinstance(result, AgentEvalResult)
        assert result.run_id == _RUN_ID

    def test_the_handle_carries_the_taskset_so_metrics_stay_live(self) -> None:
        """The caller never hands their tasks back; the handle kept them."""
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("completed"), _bundle_response()]
        tasks = [_task()]
        resource = Evaluator(cast(NeMoPlatform, platform))

        job = resource.evaluate(taskset=tasks, target=_MODEL, workspace="ws")
        job.wait_until_done()
        result = job.get_result()

        assert result.tasks[0] is tasks[0]
        assert isinstance(result.tasks[0].metrics[0], ExactMatchMetric)


class TestTargetOnlyConfig:
    """Settings that only make sense with a target must not vanish when there isn't one."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [("params", RunConfigOnlineModel(parallelism=3)), ("prompt_template", "{{task.inputs.instruction}}")],
    )
    def test_rejects_generation_settings_without_a_target(self, field: str, value: Any) -> None:
        config = AgentEvalRunConfig(**{field: value})

        with pytest.raises(ValueError, match=f"config carries {field} but no target"):
            build_spec(
                taskset=[_task()],
                target=None,
                trials=[],
                config=config,
                metric_bundle_packager=None,
            )

    def test_accepts_trials_with_a_config_that_carries_neither(self) -> None:
        spec = build_spec(
            taskset=[_task()],
            target=None,
            trials=[],
            config=AgentEvalRunConfig(parallelism=2),
            metric_bundle_packager=None,
        )

        assert spec.target is None
        assert spec.max_concurrent_tasks == 2


class TestHandleRequestsAreBounded:
    """Every handle request carries the platform timeout.

    Without one, a stalled status or download call hangs and the poll loop never reaches its own
    ``job_timeout_seconds`` check, so that ceiling would not actually bound the call.
    """

    def test_status_and_downloads_pass_a_timeout(self) -> None:
        platform = _SyncPlatform()
        platform._client.post.return_value = _created()
        platform._client.get.side_effect = [_status("completed"), _bundle_response(), _summary_response()]
        executor = _SyncAgentEvalExecutor(platform=cast(NeMoPlatform, platform))

        job = executor.evaluate(taskset=[_task()], target=_MODEL, workspace="ws")
        job.wait_until_done()
        job.get_result()
        job.get_summary()

        assert platform._client.get.call_count == 3
        for call in platform._client.get.call_args_list:
            assert call.kwargs["timeout"] == platform.timeout
