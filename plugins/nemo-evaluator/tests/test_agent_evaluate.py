# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the agent-evaluation job (AALGO-297)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.jobs.agent_evaluate import (
    AGENT_BUNDLE_DIR,
    DEFAULT_RESULT_NAME,
    SUMMARY_RESULT_NAME,
    AgentEvalJob,
    _to_runtime_task,
)
from nemo_evaluator.jobs.agent_spec import (
    AgentEvalInputSpec,
    AgentEvalSpec,
    AgentEvalTaskInput,
    AgentEvalTaskSpec,
    AgentTarget,
    CodexRunnerTarget,
    ModelTarget,
    Target,
)
from nemo_evaluator.metric_refs import MetricRef
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator.tasks.agent_evaluate import main as agent_eval_task_main
from nemo_evaluator.tasks.runner import SDK_INITIALIZATION_EXIT_CODE
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime import CodexCliAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import (
    AgentEvalTarget,
    AgentEvalTrial,
    AgentEvalTrialStatus,
    AgentOutput,
)
from nemo_evaluator_sdk.enums import AgentFormat
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.values import Agent, GenericAgent, Model, RunConfigOnline, RunConfigOnlineModel, SecretRef
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.types.jobs.platform_job_spec import PlatformJobSpec
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults
from nemo_platform_plugin.jobs.constants import PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nemo_platform_plugin.scheduler import NemoJobScheduler
from pytest_mock import MockerFixture


def _inline_metric() -> MetricInline:
    bundle = bundle_metric(
        ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}"),
        CloudpickleMetricBundlePackager(),
    )
    return MetricInline.model_validate(bundle.model_dump(mode="json"))


def _task_spec() -> AgentEvalTaskSpec:
    return AgentEvalTaskSpec(
        id="task-1",
        intent="Answer the question.",
        inputs={"prompt": "What is 2+2?"},
        metrics=[_inline_metric()],
    )


def _job_context(tmp_path: Path) -> JobContext:
    storage = StoragePaths(ephemeral=tmp_path / "ephemeral", persistent=tmp_path / "persistent")
    storage.ephemeral.mkdir()
    storage.persistent.mkdir()
    return JobContext(
        workspace="dev",
        storage=storage,
        results=LocalJobResults(root=storage.persistent / "results"),
    )


class _FakeEvaluator:
    """Stand-in for AgentEvaluator: records the tasks it was handed and returns canned trials."""

    def __init__(self) -> None:
        self.received_tasks: list[AgentEvalTask] = []
        self.received_trials: list[AgentEvalTrial] | None = None
        self.received_target: AgentEvalTarget | None = None
        self.received_config: AgentEvalRunConfig | None = None

    def run_sync(
        self,
        *,
        tasks: Sequence[AgentEvalTask],
        trials: Sequence[AgentEvalTrial] | None = None,
        target: AgentEvalTarget | None = None,
        config: AgentEvalRunConfig | None = None,
    ) -> AgentEvalResult:
        self.received_tasks = list(tasks)
        self.received_trials = list(trials) if trials is not None else None
        self.received_target = target
        self.received_config = config
        generated_trials = [
            AgentEvalTrial(
                id=f"{task.id}:trial",
                task_id=task.id,
                status=AgentEvalTrialStatus.COMPLETED,
                output=AgentOutput(output_text="4"),
            )
            for task in tasks
        ]
        return AgentEvalResult(
            run_id="run-1", tasks=list(tasks), trials=generated_trials, scores=[], summary=AgentEvalSummary()
        )


def test_to_runtime_task_reconstructs_runtime_metric_instances() -> None:
    task = _to_runtime_task(_task_spec())
    assert isinstance(task, AgentEvalTask)
    assert task.id == "task-1"
    assert len(task.metrics) == 1
    assert isinstance(task.metrics[0], ExactMatchMetric)


def test_agent_eval_job_reconstructs_tasks_and_persists_bundle(tmp_path: Path, mocker: MockerFixture) -> None:
    fake = _FakeEvaluator()
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=fake)
    ctx = _job_context(tmp_path)

    spec = AgentEvalSpec(tasks=[_task_spec()], target=CodexRunnerTarget(model="gpt-5.5"))
    result = AgentEvalJob().run(spec.model_dump(), ctx=ctx)

    # The job reconstructed runtime tasks (bundled metric round-tripped) before handing off.
    assert [task.id for task in fake.received_tasks] == ["task-1"]
    assert isinstance(fake.received_tasks[0].metrics[0], ExactMatchMetric)

    # The run bundle is persisted under job storage and registered as artifacts.
    assert result["status"] == "completed"
    bundle = ctx.storage.persistent / AGENT_BUNDLE_DIR
    assert (bundle / "trials.jsonl").exists()
    assert (bundle / "scores.jsonl").exists()
    assert (bundle / "summary.json").exists()
    assert (ctx.storage.persistent / "results" / DEFAULT_RESULT_NAME).exists()
    assert (ctx.storage.persistent / "results" / SUMMARY_RESULT_NAME).exists()
    assert result["artifact"]["name"] == DEFAULT_RESULT_NAME


def test_agent_eval_job_survives_result_persistence_failure(tmp_path: Path, mocker: MockerFixture) -> None:
    # The queryable result record is a best-effort convenience index; the authoritative output (bundle
    # + summary artifacts) is already saved. A persistence failure must not fail a successful eval.
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=_FakeEvaluator())
    persist = mocker.patch(
        "nemo_evaluator.jobs.agent_evaluate.persist_agent_eval_result",
        side_effect=RuntimeError("entity store unavailable"),
    )
    ctx = _job_context(tmp_path)

    spec = AgentEvalSpec(tasks=[_task_spec()], target=CodexRunnerTarget(model="gpt-5.5"))
    result = AgentEvalJob().run(spec.model_dump(), ctx=ctx)

    # Persistence was attempted and raised, yet the job still completed with its artifacts intact.
    persist.assert_called_once()
    assert result["status"] == "completed"
    assert result["artifact"]["name"] == DEFAULT_RESULT_NAME
    assert (ctx.storage.persistent / "results" / DEFAULT_RESULT_NAME).exists()


def test_agent_eval_spec_requires_at_least_one_task() -> None:
    with pytest.raises(ValueError, match="at least 1 item|too_short|min_length"):
        AgentEvalSpec(tasks=[])


def _agent() -> Agent:
    return GenericAgent(
        url="http://agent.test",
        name="test-agent",
        format=AgentFormat.GENERIC,
        body={"question": "{{item.prompt}}"},
        response_path="$.answer",
    )


def test_resolve_target_builds_codex_runtime_from_runner_target(tmp_path: Path) -> None:
    ctx = _job_context(tmp_path)
    target, prompt_template, params = AgentEvalJob._resolve_target(CodexRunnerTarget(model="gpt-5.5"), ctx)
    # A runner shapes its own request, so it contributes no prompt template or inference params.
    assert isinstance(target, CodexCliAgentRuntime)
    assert prompt_template is None
    assert params is None


def test_resolve_target_unpacks_model_target_request_config(tmp_path: Path) -> None:
    ctx = _job_context(tmp_path)
    model = Model(url="http://model.test/v1/chat/completions", name="m")
    target, prompt_template, params = AgentEvalJob._resolve_target(
        ModelTarget(model=model, prompt_template="{{item.prompt}}", params=RunConfigOnlineModel()), ctx
    )
    assert target is model
    assert prompt_template == "{{item.prompt}}"
    assert isinstance(params, RunConfigOnlineModel)


def test_resolve_target_agent_carries_no_prompt_template(tmp_path: Path) -> None:
    ctx = _job_context(tmp_path)
    agent = _agent()
    target, prompt_template, params = AgentEvalJob._resolve_target(AgentTarget(agent=agent), ctx)
    # The agent shapes its own request via body/response_path — no separate prompt template.
    assert target is agent
    assert prompt_template is None
    assert isinstance(params, RunConfigOnline)


def test_resolve_target_resolves_none_to_no_target(tmp_path: Path) -> None:
    ctx = _job_context(tmp_path)
    assert AgentEvalJob._resolve_target(None, ctx) == (None, None, None)


def test_runner_target_is_accepted(tmp_path: Path) -> None:
    spec = AgentEvalSpec(tasks=[_task_spec()], target=CodexRunnerTarget(model="gpt-5.5"))
    assert isinstance(spec.target, CodexRunnerTarget)


def _sdk_with_identity(sdk_cls: type[NeMoPlatform | AsyncNeMoPlatform]) -> NeMoPlatform | AsyncNeMoPlatform:
    return sdk_cls(
        base_url="http://platform",
        default_headers={
            "X-NMP-Principal-Id": "service:evaluator",
            "X-NMP-Principal-On-Behalf-Of": "user-1",
            "X-NMP-Principal-On-Behalf-Of-Email": "user@corp.test",  # PII — must stay in-platform
            "X-NMP-Internal": "true",
            "X-NMP-Trace-Id": "must-not-forward",  # non-identity X-NMP-* must be dropped
            "Authorization": "Bearer super-secret",  # bearer must never reach any endpoint
        },
    )


def _model_target(url: str) -> ModelTarget:
    return ModelTarget(model=Model(url=url, name="m"))


@pytest.mark.parametrize("sdk_cls", [NeMoPlatform, AsyncNeMoPlatform])
def test_build_evaluator_forwards_identity_headers_to_platform_routed_target(
    sdk_cls: type[NeMoPlatform | AsyncNeMoPlatform],
) -> None:
    """A platform-routed target (same host as the SDK base URL, e.g. an IGW route) must act as the
    job's principal, so identity headers are forwarded. Forwarding is an explicit allowlist: the
    service principal id and on-behalf-of go through, but transport noise and other ``X-NMP-*`` (e.g.
    trace) headers and the bearer do not."""
    sdk = _sdk_with_identity(sdk_cls)
    target = _model_target("http://platform/apis/inference-gateway/v2/workspaces/default/model/m/-/v1/chat/completions")

    evaluator = AgentEvalJob._build_evaluator(sdk, target)

    assert evaluator.default_headers == {
        "X-NMP-Principal-Id": "service:evaluator",
        "X-NMP-Principal-On-Behalf-Of": "user-1",
        "X-NMP-Principal-On-Behalf-Of-Email": "user@corp.test",
        "X-NMP-Internal": "true",
    }


@pytest.mark.parametrize("sdk_cls", [NeMoPlatform, AsyncNeMoPlatform])
def test_build_evaluator_sends_no_identity_to_third_party_target(
    sdk_cls: type[NeMoPlatform | AsyncNeMoPlatform],
) -> None:
    """A third-party target the user configured must receive no on-behalf-of identity — that would
    leak the delegated user's id/email/groups PII to an external host (it authenticates via its own
    api key anyway)."""
    sdk = _sdk_with_identity(sdk_cls)
    target = _model_target("https://api.openai.com/v1/chat/completions")

    assert AgentEvalJob._build_evaluator(sdk, target).default_headers is None


def test_build_evaluator_runner_target_forwards_no_headers() -> None:
    # A runner (Codex CLI) has no platform HTTP endpoint, so there's no identity to forward.
    sdk = _sdk_with_identity(NeMoPlatform)
    assert AgentEvalJob._build_evaluator(sdk, CodexRunnerTarget(model="gpt-5.5")).default_headers is None


def test_build_evaluator_without_platform_forwards_no_headers() -> None:
    target = _model_target("http://platform/apis/inference-gateway/v2/workspaces/default/model/m/-/v1/chat/completions")
    assert AgentEvalJob._build_evaluator(None, target).default_headers is None


def test_input_spec_accepts_stored_metric_reference() -> None:
    spec = AgentEvalInputSpec(
        tasks=[AgentEvalTaskInput(id="task-1", intent="Answer.", inputs={}, metrics=[MetricRef("stored-metric")])],
        target=CodexRunnerTarget(model="gpt-5.5"),
    )
    assert isinstance(spec.tasks[0].metrics[0], MetricRef)


async def test_to_spec_resolves_inline_task_metrics_without_a_platform() -> None:
    # Inline metrics need no entity client/SDK; refs would, but none are used here.
    input_spec = AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="task-1",
                intent="Answer the question.",
                inputs={"prompt": "What is 2+2?"},
                metrics=[_inline_metric()],
            )
        ],
        target=CodexRunnerTarget(model="gpt-5.5"),
    )

    spec = await AgentEvalJob.to_spec(input_spec, workspace="dev", entity_client=None, async_sdk=None, is_local=True)

    assert isinstance(spec, AgentEvalSpec)
    assert len(spec.tasks) == 1
    assert isinstance(spec.tasks[0].metrics[0], MetricInline)
    # Canonical metrics reconstruct to runtime instances.
    assert isinstance(_to_runtime_task(spec.tasks[0]).metrics[0], ExactMatchMetric)


async def test_to_spec_requires_platform_to_resolve_a_metric_reference() -> None:
    # A stored MetricRef can only be loaded with an entity store + SDK; without one, to_spec must
    # fail loudly rather than silently drop the metric.
    input_spec = AgentEvalInputSpec(
        tasks=[AgentEvalTaskInput(id="task-1", intent="Answer.", inputs={}, metrics=[MetricRef("stored-metric")])],
        target=CodexRunnerTarget(model="gpt-5.5"),
    )
    with pytest.raises(ValueError, match="platform connection"):
        await AgentEvalJob.to_spec(input_spec, workspace="dev", entity_client=None, async_sdk=None, is_local=True)


# --- compile: the submit/service-side path ----------------------------------


def _assert_agent_eval_step_entrypoint(job_spec: PlatformJobSpec) -> None:
    step = job_spec.steps[0]
    container = cast(Any, step.executor).container
    assert container.entrypoint == ["python", "-m"]
    assert container.command == ["nemo_evaluator.tasks.agent_evaluate"]


@pytest.mark.parametrize(
    ("target", "expected_kind", "expected_endpoint_name"),
    [
        (CodexRunnerTarget(model="gpt-5.5"), "codex", None),
        (
            ModelTarget(
                model=Model(url="http://model.test/v1/chat/completions", name="test-model"),
                params=RunConfigOnlineModel(),
            ),
            "model",
            "test-model",
        ),
        (AgentTarget(agent=_agent(), params=RunConfigOnline()), "agent", "test-agent"),
    ],
)
async def test_compile_produces_cpu_task_step_carrying_each_target(
    target: Target,
    expected_kind: str,
    expected_endpoint_name: str | None,
) -> None:
    spec = AgentEvalSpec(tasks=[_task_spec()], target=target)

    compiled = await AgentEvalJob.compile(
        workspace="default", spec=spec, entity_client=object(), job_name=None, async_sdk=None
    )

    job_spec = PlatformJobSpec.model_validate(compiled)
    assert len(job_spec.steps) == 1
    step = job_spec.steps[0]
    assert step.name == "agent-evaluate"
    _assert_agent_eval_step_entrypoint(job_spec)
    config = cast(dict[str, Any], step.config)
    assert len(config["tasks"]) == 1
    assert config["target"]["kind"] == expected_kind
    if expected_endpoint_name is not None:
        endpoint = config["target"].get("model") or config["target"].get("agent")
        assert endpoint["name"] == expected_endpoint_name


async def test_compile_injects_target_api_key_secret() -> None:
    spec = AgentEvalSpec(
        tasks=[_task_spec()],
        target=ModelTarget(
            model=Model(
                url="https://integrate.api.nvidia.com/v1/chat/completions",
                name="nvidia/model",
                api_key_secret=SecretRef(root="NVIDIA_API_KEY"),
            ),
            params=RunConfigOnlineModel(),
        ),
    )

    compiled = await AgentEvalJob.compile(
        workspace="default", spec=spec, entity_client=object(), job_name=None, async_sdk=None
    )

    step = PlatformJobSpec.model_validate(compiled).steps[0]
    secrets = {env.name: env.from_secret.name for env in step.environment or [] if env.from_secret}
    assert secrets == {"NVIDIA_API_KEY": "NVIDIA_API_KEY"}


async def test_compile_rejects_reserved_secret_env_name() -> None:
    spec = AgentEvalSpec(
        tasks=[_task_spec()],
        target=ModelTarget(
            model=Model(
                url="https://integrate.api.nvidia.com/v1/chat/completions",
                name="nvidia/model",
                api_key_secret=SecretRef(root=PERSISTENT_JOB_STORAGE_PATH_ENVVAR),
            ),
            params=RunConfigOnlineModel(),
        ),
    )

    with pytest.raises(ValueError, match="reserved"):
        await AgentEvalJob.compile(
            workspace="default", spec=spec, entity_client=object(), job_name=None, async_sdk=None
        )


# --- run_local: the in-process run path, across target types ----------------


@pytest.mark.parametrize(
    "target",
    [
        ModelTarget(
            model=Model(url="http://model.test/v1/chat/completions", name="test-model"), params=RunConfigOnlineModel()
        ),
        AgentTarget(agent=_agent(), params=RunConfigOnline()),
        CodexRunnerTarget(model="gpt-5.5"),
    ],
)
def test_run_local_executes_each_target_type(target: Target, mocker: MockerFixture) -> None:
    # run_local drives the full validate -> to_spec -> run path. The evaluator is faked so the target
    # is threaded (a runner resolved to its runtime, an endpoint passed through) without real inference.
    fake = _FakeEvaluator()
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=fake)
    input_spec = AgentEvalInputSpec(
        tasks=[
            AgentEvalTaskInput(
                id="task-1", intent="Answer.", inputs={"prompt": "What is 2+2?"}, metrics=[_inline_metric()]
            )
        ],
        target=target,
    )

    result = NemoJobScheduler().run_local(AgentEvalJob, input_spec.model_dump(mode="json"))

    assert result["status"] == "completed"
    assert result["artifact"]["name"] == DEFAULT_RESULT_NAME
    assert [task.id for task in fake.received_tasks] == ["task-1"]
    assert fake.received_trials is None  # online generation, not precomputed
    if isinstance(target, CodexRunnerTarget):
        assert isinstance(fake.received_target, CodexCliAgentRuntime)
    elif isinstance(target, ModelTarget):
        assert getattr(fake.received_target, "name", None) == target.model.name
    else:
        assert getattr(fake.received_target, "name", None) == target.agent.name


def test_run_local_scores_precomputed_trials_offline(mocker: MockerFixture) -> None:
    # Offline eval: precomputed trials are scored directly, with no target / no generation.
    fake = _FakeEvaluator()
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=fake)
    precomputed = [
        AgentEvalTrial(
            id="t-1", task_id="task-1", status=AgentEvalTrialStatus.COMPLETED, output=AgentOutput(output_text="4")
        )
    ]
    input_spec = AgentEvalInputSpec(
        tasks=[AgentEvalTaskInput(id="task-1", intent="Answer.", inputs={}, metrics=[_inline_metric()])],
        trials=precomputed,
    )

    result = NemoJobScheduler().run_local(AgentEvalJob, input_spec.model_dump(mode="json"))

    assert result["status"] == "completed"
    assert fake.received_target is None
    assert [trial.id for trial in fake.received_trials or []] == ["t-1"]


def test_spec_requires_exactly_one_of_target_or_trials() -> None:
    trial = AgentEvalTrial(
        id="t-1", task_id="task-1", status=AgentEvalTrialStatus.COMPLETED, output=AgentOutput(output_text="4")
    )
    with pytest.raises(ValueError, match="exactly one"):
        AgentEvalSpec(tasks=[_task_spec()])  # neither target nor trials
    with pytest.raises(ValueError, match="exactly one"):
        AgentEvalSpec(tasks=[_task_spec()], target=CodexRunnerTarget(model="gpt-5.5"), trials=[trial])  # both


# --- container task entrypoint ----------------------------------------------


class TestAgentEvalTask:
    """Coverage for the compiled container/subprocess task entrypoint."""

    def test_main_dispatches_agent_eval_job_with_task_sdk(self, mocker: MockerFixture) -> None:
        sdk = object()
        async_sdk = object()
        get_task_sdk = mocker.patch("nemo_evaluator.tasks.runner.get_task_sdk", return_value=sdk)
        get_async_task_sdk = mocker.patch("nemo_evaluator.tasks.runner.get_async_task_sdk", return_value=async_sdk)
        run_task = mocker.patch("nemo_evaluator.tasks.runner.run_task", return_value=0)

        exit_code = agent_eval_task_main()

        assert exit_code == 0
        get_task_sdk.assert_called_once_with("evaluator")
        get_async_task_sdk.assert_called_once_with("evaluator")
        run_task.assert_called_once_with(AgentEvalJob, sdk=sdk, async_sdk=async_sdk)

    def test_main_returns_setup_exit_code_when_task_sdk_fails(self, mocker: MockerFixture) -> None:
        get_task_sdk = mocker.patch("nemo_evaluator.tasks.runner.get_task_sdk", side_effect=RuntimeError("boom"))
        run_task = mocker.patch("nemo_evaluator.tasks.runner.run_task")

        exit_code = agent_eval_task_main()

        assert exit_code == SDK_INITIALIZATION_EXIT_CODE
        get_task_sdk.assert_called_once_with("evaluator")
        run_task.assert_not_called()
