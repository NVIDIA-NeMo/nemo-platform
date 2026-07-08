# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for publish_to_intake — the explicit Evaluator -> Intake publish step."""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from nemo_evaluator.intake.publish import PublishError, publish_to_intake
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.metrics.protocol import MetricOutput
from nemo_intake_plugin.spans.api.evaluator_results_schemas import EvaluatorResultInput
from nemo_intake_plugin.spans.ingest.atif import AtifIngestRequest
from nemo_platform import AsyncNeMoPlatform

# --- fakes ------------------------------------------------------------------


class _FakePaginatedTraces:
    def __init__(self, *, root_span_id: str | None, session_id: str) -> None:
        self._root_span_id = root_span_id
        self._session_id = session_id

    async def items(self) -> AsyncIterator[object]:
        if self._root_span_id is not None:
            yield SimpleNamespace(
                session_id=self._session_id,
                root_span_id=f"{self._root_span_id}:{self._session_id}",
            )


class _FakeIntakeClient:
    def __init__(
        self,
        *,
        root_span_id: str | None,
        atif_fail: bool,
        fail_eval_session: str | None,
    ) -> None:
        self.root_span_id = root_span_id
        self.atif_fail = atif_fail
        self.fail_eval_session = fail_eval_session
        self.atif_calls: list[dict[str, Any]] = []
        self.eval_calls: list[dict[str, Any]] = []

    async def create_atif(self, *, workspace: str, body: AtifIngestRequest) -> None:
        if self.atif_fail:
            raise RuntimeError("atif ingest 400")
        self.atif_calls.append({"workspace": workspace, **body.model_dump(mode="json", exclude_none=True)})

    async def create_evaluator_result(self, *, workspace: str, body: EvaluatorResultInput) -> object:
        if self.fail_eval_session is not None and body.session_id == self.fail_eval_session:
            raise RuntimeError(f"evaluator-results 500 for {body.session_id}")
        self.eval_calls.append({"workspace": workspace, **body.model_dump(mode="json", exclude_none=True)})
        return SimpleNamespace(evaluator_result_id="eval-1")

    async def list_traces(self, *, workspace: str, query_params: dict[str, Any]) -> _FakePaginatedTraces:
        del workspace
        session_id = str(query_params["filter"]["session_id"])
        return _FakePaginatedTraces(root_span_id=self.root_span_id, session_id=session_id)


class _FakeClient:
    def __init__(
        self,
        *,
        workspace: str | None = "default",
        root_span_id: str | None = "span",
        atif_fail: bool = False,
        fail_eval_session: str | None = None,
    ) -> None:
        self.workspace = workspace
        self.intake_client = _FakeIntakeClient(
            root_span_id=root_span_id,
            atif_fail=atif_fail,
            fail_eval_session=fail_eval_session,
        )
        self.atif_calls = self.intake_client.atif_calls
        self.eval_calls = self.intake_client.eval_calls


def _client(**kwargs: Any) -> AsyncNeMoPlatform:
    return cast(AsyncNeMoPlatform, _FakeClient(**kwargs))


@pytest.fixture(autouse=True)
def _adapt_intake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nemo_evaluator.intake.publish.client_from_platform",
        lambda platform, _client_type: platform.intake_client,
    )


# --- fixtures ---------------------------------------------------------------


def _trial(trial_id: str, task_id: str = "task-1") -> AgentEvalTrial:
    return AgentEvalTrial(
        id=trial_id,
        task_id=task_id,
        status=AgentEvalTrialStatus.COMPLETED,
        output=AgentOutput(output_text="answer"),
    )


def _score(
    trial_id: str,
    metric_type: str,
    outputs: list[MetricOutput],
    status: AgentEvalScoreStatus = AgentEvalScoreStatus.COMPLETED,
) -> AgentEvalTaskScore:
    return AgentEvalTaskScore(
        id=f"score-{trial_id}-{metric_type}",
        run_id="run-1",
        task_id="task-1",
        trial_id=trial_id,
        metric_type=metric_type,
        status=status,
        outputs=outputs,
    )


def _result(trials: list[AgentEvalTrial], scores: list[AgentEvalTaskScore]) -> AgentEvalResult:
    return AgentEvalResult(
        run_id="run-1",
        tasks=[],
        trials=trials,
        scores=scores,
        summary=AgentEvalSummary(),
    )


# --- tests ------------------------------------------------------------------


async def test_publishes_trajectory_and_scores() -> None:
    result = _result(
        trials=[_trial("t-1")],
        scores=[
            _score("t-1", "accuracy", [MetricOutput(name="score", value=0.5), MetricOutput(name="passed", value=True)]),
            _score("t-1", "latency", [MetricOutput(name="p50", value=1.2)]),
        ],
    )
    client = _FakeClient()
    report = await publish_to_intake(result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1")

    assert len(client.atif_calls) == 1
    assert client.atif_calls[0]["session_id"] == "run-1:t-1"
    assert client.atif_calls[0]["experiment_context"] == {"experiment_id": "exp-1", "test_case_id": "task-1"}
    # 3 metric outputs across the two score records -> 3 evaluator-result rows.
    assert len(client.eval_calls) == 3
    assert {call["name"] for call in client.eval_calls} == {"accuracy.score", "accuracy.passed", "latency.p50"}
    # span_id resolved from the trace and threaded into every row.
    assert {call["span_id"] for call in client.eval_calls} == {"span:run-1:t-1"}

    assert report.trial_count == 1
    assert report.evaluator_result_count == 3
    published = report.published_trials[0]
    assert (published.trial_id, published.session_id, published.span_id, published.evaluator_result_count) == (
        "t-1",
        "run-1:t-1",
        "span:run-1:t-1",
        3,
    )


async def test_multiple_trials_each_get_their_own_session_and_span() -> None:
    result = _result(
        trials=[_trial("t-1"), _trial("t-2")],
        scores=[
            _score("t-1", "accuracy", [MetricOutput(name="score", value=1.0)]),
            _score("t-2", "accuracy", [MetricOutput(name="score", value=0.0)]),
        ],
    )
    client = _FakeClient()
    report = await publish_to_intake(result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1")

    assert len(client.atif_calls) == 2
    assert report.trial_count == 2
    by_session = {call["session_id"]: call["span_id"] for call in client.eval_calls}
    assert by_session == {"run-1:t-1": "span:run-1:t-1", "run-1:t-2": "span:run-1:t-2"}


async def test_trial_without_scores_still_ingests_trajectory() -> None:
    result = _result(trials=[_trial("t-1")], scores=[])
    client = _FakeClient()
    report = await publish_to_intake(result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1")

    assert len(client.atif_calls) == 1
    assert len(client.eval_calls) == 0
    assert report.published_trials[0].evaluator_result_count == 0


async def test_explicit_workspace_overrides_client_default() -> None:
    result = _result(trials=[_trial("t-1")], scores=[])
    client = _FakeClient(workspace="default")
    report = await publish_to_intake(
        result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1", workspace="ws-2"
    )
    assert report.workspace == "ws-2"
    assert client.atif_calls[0]["workspace"] == "ws-2"


async def test_missing_workspace_raises() -> None:
    result = _result(trials=[_trial("t-1")], scores=[])
    client = _FakeClient(workspace=None)
    with pytest.raises(ValueError, match="workspace"):
        await publish_to_intake(result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1")


async def test_unresolvable_span_raises_publish_error() -> None:
    result = _result(
        trials=[_trial("t-1")],
        scores=[_score("t-1", "accuracy", [MetricOutput(name="score", value=1.0)])],
    )
    client = _FakeClient(root_span_id=None)
    with pytest.raises(PublishError, match="No root span"):
        await publish_to_intake(result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1")


async def test_ingest_failure_propagates() -> None:
    result = _result(trials=[_trial("t-1")], scores=[])
    client = _FakeClient(atif_fail=True)
    with pytest.raises(RuntimeError, match="atif ingest 400"):
        await publish_to_intake(result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1")


async def test_failed_and_non_finite_scores_are_skipped_and_reported() -> None:
    # NaN can't be sent (not JSON-serializable) and a FAILED score is not a real measurement; both
    # are omitted but surfaced in the report so the omission is explicit, not silent (X6).
    result = _result(
        trials=[_trial("t-1")],
        scores=[
            _score(
                "t-1", "accuracy", [MetricOutput(name="score", value=1.0), MetricOutput(name="broken", value=math.nan)]
            ),
            _score("t-1", "judge", [MetricOutput(name="verdict", value=math.nan)], status=AgentEvalScoreStatus.FAILED),
        ],
    )
    client = _FakeClient()
    report = await publish_to_intake(result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1")

    # Only the finite, completed output is sent to Intake.
    assert {call["name"] for call in client.eval_calls} == {"accuracy.score"}
    # The omissions are reported, with reasons.
    assert {(skip.name, skip.reason) for skip in report.skipped} == {
        ("accuracy.broken", "non-finite value"),
        ("judge.verdict", "scoring failed"),
    }


async def test_one_trial_failure_does_not_block_others_and_is_reported() -> None:
    # Partial uploads are acceptable (intake has no rollback), so a single trial's failure must NOT
    # abort the others — every trial that can land should land, leaving less for an idempotent retry.
    result = _result(
        trials=[_trial("t-1"), _trial("t-2")],
        scores=[
            _score("t-1", "accuracy", [MetricOutput(name="score", value=1.0)]),
            _score("t-2", "accuracy", [MetricOutput(name="score", value=0.0)]),
        ],
    )
    client = _FakeClient(fail_eval_session="run-1:t-2")

    with pytest.raises(PublishError) as excinfo:
        await publish_to_intake(
            result, platform=cast(AsyncNeMoPlatform, client), experiment_id="exp-1", max_concurrency=1
        )

    # The healthy trial still published despite the other failing.
    assert any(call["session_id"] == "run-1:t-1" for call in client.eval_calls)
    assert all(call["session_id"] != "run-1:t-2" for call in client.eval_calls)

    # The failure surfaces the affected trial and points the user at recovery.
    message = str(excinfo.value).lower()
    assert "t-2" in message
    assert "re-run" in message or "cached" in message or "publish" in message
