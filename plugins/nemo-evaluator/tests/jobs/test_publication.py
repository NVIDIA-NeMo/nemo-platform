# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the agent-eval job's Intake publication step."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.jobs.agent_evaluate import AgentEvalJob
from nemo_evaluator.jobs.agent_spec import (
    AgentEvalInputSpec,
    AgentEvalSpec,
    AgentEvalTaskInput,
    AgentEvalTaskSpec,
    AgentTarget,
    CodexRunnerTarget,
    FabricRunnerTarget,
    HarborRunnerTarget,
    ModelTarget,
    Target,
    target_agent_identity,
)
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec, EvaluateJob, EvaluateSpec
from nemo_evaluator.jobs.publication import PublicationFailedError, publish_agent_eval_result
from nemo_evaluator.jobs.publication_spec import (
    IntakePublicationSpec,
    PublicationSpec,
    RowIntakePublicationSpec,
    RowPublicationSpec,
)
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary, RunMetadata
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.protocol import MetricOutput
from nemo_evaluator_sdk.values import Model, RunConfigOnline, RunConfigOnlineModel
from nemo_evaluator_sdk.values.agents import NemoAgentToolkitAgent
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult  # noqa: F401
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, EvaluationResult, RowScore
from nemo_platform import AsyncNeMoPlatform
from nemo_platform._exceptions import APIConnectionError, NotFoundError
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from pydantic import ValidationError
from pytest_mock import MockerFixture

STARTED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

_INLINE_METRIC = MetricInline.model_validate(
    bundle_metric(
        ExactMatchMetric(reference="{{item.question}}", candidate="{{item.question}}"),
        CloudpickleMetricBundlePackager(),
    ).model_dump(mode="json")
)

#: Aliased because `_FakeTraces` defines a `list` method, which shadows the builtin in class scope.
_SessionIds = list[str]


def _response(status: int) -> httpx.Response:
    """A real httpx response — the SDK errors read ``response.request`` in their constructor."""
    return httpx.Response(status, request=httpx.Request("GET", "http://platform/evaluations"))


# --- fakes ------------------------------------------------------------------


class _FakeTraces:
    def __init__(self, calls: _SessionIds) -> None:
        self._calls = calls

    def list(self, *, workspace: str, filter: dict[str, Any]) -> AsyncIterator[object]:  # noqa: A002
        session_id = filter["session_id"]
        self._calls.append(session_id)

        async def _gen() -> AsyncIterator[object]:
            yield SimpleNamespace(session_id=session_id, root_span_id=f"span:{session_id}")

        return _gen()


class _FakeEvaluations:
    def __init__(self, *, missing: bool = False, error: Exception | None = None) -> None:
        self.missing = missing
        self.error = error
        self.retrieved: _SessionIds = []

    async def retrieve(self, name: str, *, workspace: str | None = None) -> object:
        self.retrieved.append(name)
        if self.error is not None:
            raise self.error
        if self.missing:
            raise NotFoundError("not found", response=_response(404), body=None)
        return SimpleNamespace(name=name)


class _FakeIngest:
    def __init__(self, calls: list[dict[str, Any]], *, error: Exception | None = None) -> None:
        self._calls = calls
        self._error = error
        self.loop: asyncio.AbstractEventLoop | None = None

    async def create(self, **kwargs: Any) -> None:
        self.loop = asyncio.get_running_loop()
        if self._error is not None:
            raise self._error
        self._calls.append(kwargs)


class _FakeClient:
    """Minimal stand-in for the bits of ``AsyncNeMoPlatform`` publication touches."""

    def __init__(
        self,
        *,
        missing_evaluation: bool = False,
        ingest_error: Exception | None = None,
        preflight_error: Exception | None = None,
    ) -> None:
        self.workspace = "default"
        self.atif_calls: list[dict[str, Any]] = []
        self.eval_result_calls: list[dict[str, Any]] = []
        self.trace_calls: _SessionIds = []
        self.copy_calls = 0
        self.evaluations = _FakeEvaluations(missing=missing_evaluation, error=preflight_error)
        self.intake = SimpleNamespace(
            ingest=SimpleNamespace(atif=_FakeIngest(self.atif_calls, error=ingest_error)),
            evaluator_results=_FakeIngest(self.eval_result_calls),
            traces=_FakeTraces(self.trace_calls),
        )

    def copy(self, **kwargs: Any) -> _FakeClient:
        del kwargs
        self.copy_calls += 1
        return self


def _client(**kwargs: Any) -> AsyncNeMoPlatform:
    return cast(AsyncNeMoPlatform, _FakeClient(**kwargs))


def _result() -> AgentEvalResult:
    return AgentEvalResult(
        run_id="run-1",
        tasks=[],
        trials=[
            AgentEvalTrial(
                id="trial-1",
                task_id="task-1",
                status=AgentEvalTrialStatus.COMPLETED,
                output=AgentOutput(output_text="answer"),
            )
        ],
        scores=[
            AgentEvalTaskScore(
                id="score-1",
                run_id="run-1",
                task_id="task-1",
                trial_id="trial-1",
                metric_type="accuracy",
                status=AgentEvalScoreStatus.COMPLETED,
                outputs=[MetricOutput(name="score", value=1.0)],
            )
        ],
        summary=AgentEvalSummary(),
        metadata=RunMetadata(started_at=STARTED_AT),
    )


def _publish(client: AsyncNeMoPlatform | None, *, required: bool = True, agent_name: str | None = "a") -> Any:
    return publish_agent_eval_result(
        _result(),
        spec=IntakePublicationSpec(evaluation_id="eval-1", agent_name=agent_name, required=required),
        target=None,
        workspace="default",
        async_sdk=client,
    )


# --- identity resolution ----------------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (AgentTarget(agent=NemoAgentToolkitAgent(name="my-agent", url="http://agent")), ("my-agent", None)),
        (ModelTarget(model=Model(name="gpt-4o", url="http://model")), (None, "gpt-4o")),
        (HarborRunnerTarget(agent_name="oracle", agent_model_name="m"), ("oracle", "m")),
        (HarborRunnerTarget(agent_name="oracle", agent_import_path="pkg:Agent"), ("pkg:Agent", None)),
        (CodexRunnerTarget(model="gpt-5.5"), (None, "gpt-5.5")),
        (FabricRunnerTarget(config={}, model="p/m"), (None, "p/m")),
        (None, (None, None)),
    ],
)
def test_target_agent_identity(target: Target | None, expected: tuple[str | None, str | None]) -> None:
    assert target_agent_identity(target) == expected


# --- submit-time validation -------------------------------------------------


def _input_spec(target: Target | None, publication: PublicationSpec | None, **kwargs: Any) -> AgentEvalInputSpec:
    trials = None if target is not None else [_result().trials[0]]
    return AgentEvalInputSpec(
        tasks=[AgentEvalTaskInput(id="task-1", intent="do it")],
        target=target,
        trials=trials,
        publication=publication,
        **kwargs,
    )


def test_publication_is_optional() -> None:
    spec = _input_spec(ModelTarget(model=Model(name="m", url="http://m")), None)
    assert spec.publication is None


def test_publication_defaults_to_required() -> None:
    spec = _input_spec(
        AgentTarget(agent=NemoAgentToolkitAgent(name="a", url="http://a")),
        PublicationSpec(intake=IntakePublicationSpec(evaluation_id="eval-1")),
    )
    assert spec.publication is not None
    assert spec.publication.intake is not None
    assert spec.publication.intake.required is True


def test_agent_name_derived_from_agent_target_needs_no_override() -> None:
    spec = _input_spec(
        AgentTarget(agent=NemoAgentToolkitAgent(name="derived", url="http://a")),
        PublicationSpec(intake=IntakePublicationSpec(evaluation_id="eval-1")),
    )
    assert spec.publication is not None
    assert spec.publication.intake is not None
    assert spec.publication.intake.agent_name is None
    assert target_agent_identity(spec.target)[0] == "derived"


@pytest.mark.parametrize(
    "target",
    [
        ModelTarget(model=Model(name="gpt-4o", url="http://model")),
        CodexRunnerTarget(model="gpt-5.5"),
        FabricRunnerTarget(config={}),
        None,
    ],
)
def test_undeducible_agent_name_is_rejected_at_submit(target: Target | None) -> None:
    with pytest.raises(ValidationError, match="agent_name` is required"):
        _input_spec(target, PublicationSpec(intake=IntakePublicationSpec(evaluation_id="eval-1")))


def test_blank_identity_fields_are_rejected() -> None:
    # An empty `agent_name` satisfies `is not None` in the identity validator, so it would skip the
    # derivation that validator exists to require and resolve back to "" at publish time.
    with pytest.raises(ValidationError):
        IntakePublicationSpec(evaluation_id="eval-1", agent_name="")
    with pytest.raises(ValidationError):
        IntakePublicationSpec(evaluation_id="eval-1", agent_version="")


@pytest.mark.parametrize(
    "target",
    [ModelTarget(model=Model(name="gpt-4o", url="http://model")), CodexRunnerTarget(model="gpt-5.5"), None],
)
def test_explicit_agent_name_satisfies_undeducible_targets(target: Target | None) -> None:
    spec = _input_spec(
        target, PublicationSpec(intake=IntakePublicationSpec(evaluation_id="eval-1", agent_name="explicit"))
    )
    assert spec.publication is not None


# --- publishing -------------------------------------------------------------


def test_publishes_and_reports_what_landed() -> None:
    client = _FakeClient()
    outcome = _publish(cast(AsyncNeMoPlatform, client))

    assert client.copy_calls == 1
    assert outcome.status == PlatformJobStatus.COMPLETED
    assert outcome.evaluation_id == "eval-1"
    assert outcome.trial_count == 1
    assert outcome.evaluator_result_count == 1
    assert outcome.error is None
    assert client.evaluations.retrieved == ["eval-1"]


def test_outcome_does_not_leak_experiment_id() -> None:
    outcome = _publish(_client())
    assert "experiment_id" not in outcome.model_dump()


def test_stamps_the_run_start_time_so_republish_is_idempotent() -> None:
    client = _FakeClient()
    _publish(cast(AsyncNeMoPlatform, client))
    assert client.atif_calls[0]["steps"][0]["timestamp"] == STARTED_AT


def test_missing_evaluation_fails_before_any_ingest() -> None:
    client = _FakeClient(missing_evaluation=True)
    with pytest.raises(PublicationFailedError) as excinfo:
        _publish(cast(AsyncNeMoPlatform, client))

    assert client.atif_calls == []
    outcome = excinfo.value.outcome
    assert outcome.status == PlatformJobStatus.ERROR
    assert "does not exist" in (outcome.error or "")


def test_required_failure_raises_with_partial_outcome() -> None:
    client = _FakeClient(ingest_error=APIConnectionError(request=httpx.Request("POST", "http://platform/intake")))
    with pytest.raises(PublicationFailedError) as excinfo:
        _publish(cast(AsyncNeMoPlatform, client))

    outcome = excinfo.value.outcome
    assert outcome.status == PlatformJobStatus.ERROR
    assert outcome.trial_count == 0


def test_optional_failure_returns_outcome_instead_of_raising() -> None:
    client = _FakeClient(ingest_error=APIConnectionError(request=httpx.Request("POST", "http://platform/intake")))
    outcome = _publish(cast(AsyncNeMoPlatform, client), required=False)

    assert outcome.status == PlatformJobStatus.ERROR
    assert outcome.error


def test_unexpected_failure_still_honours_required_false() -> None:
    # `required=False` promises the evaluation survives a failed publish. An error outside the known
    # taxonomy — a bug, a transport quirk, anything unforeseen — must not be the one case that
    # escapes and fails the job anyway.
    client = _FakeClient(preflight_error=ValueError("something nobody planned for"))
    outcome = _publish(cast(AsyncNeMoPlatform, client), required=False)

    assert outcome.status == PlatformJobStatus.ERROR
    assert "ValueError" in (outcome.error or "")
    assert "something nobody planned for" in (outcome.error or "")


def test_unexpected_failure_fails_the_job_when_required() -> None:
    client = _FakeClient(preflight_error=ValueError("something nobody planned for"))
    with pytest.raises(PublicationFailedError) as excinfo:
        _publish(cast(AsyncNeMoPlatform, client))

    assert excinfo.value.outcome.status == PlatformJobStatus.ERROR


def test_platformless_run_is_a_failure_not_a_crash() -> None:
    outcome = _publish(None, required=False)
    assert outcome.status == PlatformJobStatus.ERROR
    assert "platformless" in (outcome.error or "")


def test_platformless_run_fails_the_job_when_required() -> None:
    with pytest.raises(PublicationFailedError):
        _publish(None)


# --- job wiring -------------------------------------------------------------


class _FakeEvaluator:
    """Stand-in for AgentEvaluator returning one completed trial per task."""

    def __init__(self, *, started_at: datetime | None = STARTED_AT) -> None:
        self._started_at = started_at
        self.loop: asyncio.AbstractEventLoop | None = None

    def run_sync(self, *, tasks: Sequence[AgentEvalTask], **kwargs: Any) -> AgentEvalResult:
        # Drives a real loop to completion the way `AgentEvaluator.run_sync` does, so publication
        # afterwards runs against an already-closed loop.
        return run_sync(lambda: self._run(tasks))

    async def _run(self, tasks: Sequence[AgentEvalTask]) -> AgentEvalResult:
        self.loop = asyncio.get_running_loop()
        return AgentEvalResult(
            run_id="run-1",
            tasks=list(tasks),
            trials=[
                AgentEvalTrial(
                    id=f"{task.id}:trial",
                    task_id=task.id,
                    status=AgentEvalTrialStatus.COMPLETED,
                    output=AgentOutput(output_text="4"),
                )
                for task in tasks
            ],
            scores=[],
            summary=AgentEvalSummary(),
            metadata=RunMetadata(started_at=self._started_at),
        )


def _job_context(tmp_path: Path, *, job_id: str | None = None) -> JobContext:
    storage = StoragePaths(ephemeral=tmp_path / "ephemeral", persistent=tmp_path / "persistent")
    storage.ephemeral.mkdir()
    storage.persistent.mkdir()
    return JobContext(
        workspace="default",
        storage=storage,
        results=LocalJobResults(root=storage.persistent / "results"),
        job_id=job_id,
    )


def _job_spec(*, required: bool = True) -> AgentEvalSpec:
    return AgentEvalSpec(
        tasks=[AgentEvalTaskSpec(id="task-1", intent="Answer.")],
        target=CodexRunnerTarget(model="gpt-5.5"),
        publication=PublicationSpec(
            intake=IntakePublicationSpec(evaluation_id="eval-1", agent_name="a", required=required)
        ),
    )


def test_job_does_not_publish_without_a_publication_spec(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=_FakeEvaluator())
    client = _FakeClient()

    spec = AgentEvalSpec(tasks=[AgentEvalTaskSpec(id="task-1", intent="Answer.")], target=CodexRunnerTarget())
    result = AgentEvalJob().run(
        spec.model_dump(), ctx=_job_context(tmp_path), async_sdk=cast(AsyncNeMoPlatform, client)
    )

    assert "publication" not in result
    assert client.atif_calls == []


def test_job_publishes_through_the_real_sync_bridge(tmp_path: Path, mocker: MockerFixture) -> None:
    evaluator = _FakeEvaluator()
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=evaluator)
    client = _FakeClient()
    ctx = _job_context(tmp_path)

    result = AgentEvalJob().run(_job_spec().model_dump(), ctx=ctx, async_sdk=cast(AsyncNeMoPlatform, client))

    # The evaluator drove a loop to completion first; publication then ran on a different one,
    # reusing the same injected SDK. That crossing is what raises "Event loop is closed" when the
    # client is bound to a dead loop (cf. nmp-1hr.2). It does not distinguish `run_sync` from a bare
    # `asyncio.run` — no loop is running at this point, so both behave the same here.
    ingest_loop = client.intake.ingest.atif.loop
    assert evaluator.loop is not None
    assert evaluator.loop.is_closed()
    assert ingest_loop is not None
    assert ingest_loop is not evaluator.loop

    assert result["status"] == PlatformJobStatus.COMPLETED
    assert result["publication"] == {
        "status": PlatformJobStatus.COMPLETED,
        "evaluation_id": "eval-1",
        "trial_count": 1,
        "evaluator_result_count": 0,
        "skipped": [],
    }
    assert len(client.atif_calls) == 1


def test_job_keeps_the_bundle_when_required_publication_fails(tmp_path: Path, mocker: MockerFixture) -> None:
    # Publication is the only step that can fail the job, so it runs last: the bundle and summary
    # artifacts must survive for a later re-publish.
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=_FakeEvaluator())
    client = _FakeClient(missing_evaluation=True)
    ctx = _job_context(tmp_path)

    with pytest.raises(PublicationFailedError):
        AgentEvalJob().run(_job_spec().model_dump(), ctx=ctx, async_sdk=cast(AsyncNeMoPlatform, client))

    assert (ctx.storage.persistent / "agent-eval" / "trials.jsonl").exists()
    assert (ctx.storage.persistent / "results" / "agent-eval-results").exists()


def test_job_completes_when_optional_publication_fails(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=_FakeEvaluator())
    client = _FakeClient(missing_evaluation=True)

    result = AgentEvalJob().run(
        _job_spec(required=False).model_dump(),
        ctx=_job_context(tmp_path),
        async_sdk=cast(AsyncNeMoPlatform, client),
    )

    assert result["status"] == PlatformJobStatus.COMPLETED
    assert result["publication"]["status"] == PlatformJobStatus.ERROR
    assert "does not exist" in result["publication"]["error"]


def test_job_publication_requires_a_run_start_time(tmp_path: Path, mocker: MockerFixture) -> None:
    # Without `started_at` the trajectory would fall back to Intake's per-request ingest clock, and
    # re-publishing would duplicate spans instead of replacing them. Refuse rather than write rows
    # that can never be collapsed.
    mocker.patch.object(AgentEvalJob, "_build_evaluator", return_value=_FakeEvaluator(started_at=None))

    result = AgentEvalJob().run(
        _job_spec(required=False).model_dump(),
        ctx=_job_context(tmp_path),
        async_sdk=cast(AsyncNeMoPlatform, _FakeClient()),
    )

    assert result["publication"]["status"] == PlatformJobStatus.ERROR
    assert "started_at" in result["publication"]["error"]


# --- dataset-driven (row) eval wiring ---------------------------------------


class _FakeRowEvaluator:
    """Stand-in for the row Evaluator, returning one scored row."""

    def run_sync(self, **kwargs: Any) -> EvaluationResult:
        return EvaluationResult(
            row_scores=[
                RowScore(
                    row_index=0,
                    item={"question": "2+2?", "qid": "q-1"},
                    sample={"output_text": "4", "response": {}},
                    metrics={"exact_match": [MetricOutput(name="score", value=1.0)]},
                    requests=[],
                )
            ],
            aggregate_scores=AggregatedMetricResult(scores=[]),
        )


def _evaluate_spec(*, required: bool = True, **intake: Any) -> EvaluateSpec:
    return EvaluateSpec(
        metrics=[_INLINE_METRIC],
        dataset=[{"question": "2+2?", "qid": "q-1"}],
        target=Model(name="gpt-4o", url="http://model"),
        params=RunConfigOnlineModel(),
        publication=RowPublicationSpec(
            intake=RowIntakePublicationSpec(evaluation_id="eval-1", agent_name="a", required=required, **intake)
        ),
    )


def test_evaluate_job_does_not_publish_without_a_publication_spec(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=_FakeRowEvaluator())
    client = _FakeClient()

    spec = EvaluateSpec(metrics=[_INLINE_METRIC], dataset=[{"question": "2+2?"}])
    result = EvaluateJob().run(
        spec.model_dump(), ctx=_job_context(tmp_path, job_id="job-1"), async_sdk=cast(AsyncNeMoPlatform, client)
    )

    assert "publication" not in result
    assert client.atif_calls == []


def test_evaluate_job_publishes_rows_through_the_real_sync_bridge(tmp_path: Path, mocker: MockerFixture) -> None:
    # `run` has already driven one event loop via `evaluator.run_sync`; publication drives another
    # through `run_sync` on the same injected SDK. Nothing patched out, so a loop-binding regression
    # surfaces as "Event loop is closed".
    mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=_FakeRowEvaluator())
    client = _FakeClient()

    result = EvaluateJob().run(
        _evaluate_spec().model_dump(),
        ctx=_job_context(tmp_path, job_id="job-1"),
        async_sdk=cast(AsyncNeMoPlatform, client),
    )

    assert result["publication"]["status"] == PlatformJobStatus.COMPLETED
    assert result["publication"]["trial_count"] == 1
    assert len(client.atif_calls) == 1
    # The run identity is the job id, so re-publishing the same job replaces rather than duplicates.
    assert client.atif_calls[0]["session_id"] == "job-1:row-0"


def test_evaluate_job_uses_the_configured_test_case_id_column(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=_FakeRowEvaluator())
    client = _FakeClient()

    EvaluateJob().run(
        _evaluate_spec(test_case_id_field="qid").model_dump(),
        ctx=_job_context(tmp_path, job_id="job-1"),
        async_sdk=cast(AsyncNeMoPlatform, client),
    )

    assert client.atif_calls[0]["session_id"] == "job-1:q-1"
    assert client.atif_calls[0]["evaluation_context"]["test_case_id"] == "q-1"


def test_evaluate_job_without_a_job_id_cannot_publish(tmp_path: Path, mocker: MockerFixture) -> None:
    # A row result carries no run id of its own, so a platformless local run has nothing stable to
    # key sessions on.
    mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=_FakeRowEvaluator())
    client = _FakeClient()

    result = EvaluateJob().run(
        _evaluate_spec(required=False).model_dump(),
        ctx=_job_context(tmp_path, job_id=None),
        async_sdk=cast(AsyncNeMoPlatform, client),
    )

    assert result["publication"]["status"] == PlatformJobStatus.ERROR
    assert "job id" in result["publication"]["error"]
    assert client.atif_calls == []


def test_evaluate_job_reports_a_bad_test_case_id_column(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch("nemo_evaluator.jobs.evaluate.Evaluator", return_value=_FakeRowEvaluator())
    client = _FakeClient()

    result = EvaluateJob().run(
        _evaluate_spec(required=False, test_case_id_field="missing").model_dump(),
        ctx=_job_context(tmp_path, job_id="job-1"),
        async_sdk=cast(AsyncNeMoPlatform, client),
    )

    assert result["publication"]["status"] == PlatformJobStatus.ERROR
    assert "missing" in result["publication"]["error"]
    assert client.atif_calls == []


def test_row_target_without_a_derivable_agent_name_is_rejected_at_submit() -> None:
    # A Model target names a model, not an agent. Without this the run would publish every
    # trajectory under an empty agent name.
    with pytest.raises(ValidationError, match="agent_name` is required"):
        EvaluateInputSpec(
            metrics=[_INLINE_METRIC],
            dataset=[{"question": "2+2?"}],
            target=Model(name="gpt-4o", url="http://model"),
            params=RunConfigOnlineModel(),
            publication=RowPublicationSpec(intake=RowIntakePublicationSpec(evaluation_id="eval-1")),
        )


def test_row_agent_target_derives_its_name() -> None:
    spec = EvaluateInputSpec(
        metrics=[_INLINE_METRIC],
        dataset=[{"question": "2+2?"}],
        target=NemoAgentToolkitAgent(name="my-agent", url="http://agent"),
        params=RunConfigOnline(),
        prompt_template="{{item.question}}",
        publication=RowPublicationSpec(intake=RowIntakePublicationSpec(evaluation_id="eval-1")),
    )
    assert spec.publication is not None
