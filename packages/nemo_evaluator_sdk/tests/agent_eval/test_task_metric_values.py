# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.results import (
    AgentEvalSummary,
    TrialMetricValue,
    TrialMetricValueType,
    _task_metric_values,
    metric_values,
    numeric_metric_values,
)
from nemo_evaluator_sdk.agent_eval.scores import (
    TRIAL_STATUS_DETAIL,
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask, SemanticReducer, SemanticView, ViewSignal
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricResult
from nemo_evaluator_sdk.values.protocol import MetricOutputSpec
from pydantic import RootModel, ValidationError


class _TokenCount(RootModel[int]):
    """A free-model output: numeric, but a measurement rather than a per-trial score."""


class _Metric:
    def __init__(self, metric_type: str, output: MetricOutputSpec) -> None:
        self._type = metric_type
        self._output = output

    @property
    def type(self) -> str:
        return self._type

    def output_spec(self) -> list[MetricOutputSpec]:
        return [self._output]

    async def compute_scores(self, input: MetricInput) -> MetricResult:  # pragma: no cover
        raise NotImplementedError


class _SinglePassScores(list[AgentEvalTaskScore]):
    def __init__(self, scores: list[AgentEvalTaskScore]) -> None:
        super().__init__(scores)
        self.iterations = 0

    def __iter__(self) -> Iterator[AgentEvalTaskScore]:
        self.iterations += 1
        assert self.iterations == 1, "scores were rescanned"
        return super().__iter__()


def _task(task_id: str, *metrics: _Metric) -> AgentEvalTask:
    return AgentEvalTask(id=task_id, intent="test", inputs={}, metrics=list(metrics))


def _pairs(
    records: dict[str, dict[str, list[TrialMetricValue]]],
) -> dict[str, dict[str, list[tuple[str, float | int | bool | str | None]]]]:
    """Flatten trial-metric records to ``(trial_id, value)`` so assertions stay readable."""
    return {
        task_id: {key: [(a.trial_id, a.value) for a in values] for key, values in by_key.items()}
        for task_id, by_key in records.items()
    }


def _score(
    task_id: str,
    trial_id: str,
    metric_type: str,
    output_name: str,
    value: object,
    *,
    status: AgentEvalScoreStatus = AgentEvalScoreStatus.COMPLETED,
) -> AgentEvalTaskScore:
    return AgentEvalTaskScore(
        id=f"run:{task_id}:{trial_id}:{metric_type}",
        run_id="run",
        task_id=task_id,
        trial_id=trial_id,
        metric_type=metric_type,
        status=status,
        outputs=[MetricOutput(name=output_name, value=value)],
    )


def _failed_score(
    task_id: str, trial_id: str, *, trial_failed: bool, metric_type: str = "reward"
) -> AgentEvalTaskScore:
    details = {TRIAL_STATUS_DETAIL: "failed"} if trial_failed else {"exception_type": "TimeoutError"}
    return AgentEvalTaskScore(
        id=f"run:{task_id}:{trial_id}:{metric_type}",
        run_id="run",
        task_id=task_id,
        trial_id=trial_id,
        metric_type=metric_type,
        status=AgentEvalScoreStatus.FAILED,
        diagnostics=[
            AgentEvalDiagnostic(
                severity=AgentEvalDiagnosticSeverity.ERROR,
                message="failed",
                details=details,
            )
        ],
    )


def test_summary_exposes_ordered_native_metric_values_per_task() -> None:
    reward = _Metric("reward", MetricOutputSpec.continuous_score("score"))
    retries = _Metric("retries", MetricOutputSpec.discrete_score("count"))
    verdict = _Metric("verdict", MetricOutputSpec.label("label"))
    complete = _Metric("complete", MetricOutputSpec.boolean("passed"))
    tasks = [_task("task-a", reward, retries, verdict, complete), _task("task-b", reward)]
    scores = [
        _score("task-a", "trial-0", "reward", "score", 1.0),
        _score("task-a", "trial-0", "retries", "count", 2),
        _score("task-a", "trial-0", "verdict", "label", "good"),
        _score("task-a", "trial-0", "complete", "passed", True),
        _score(
            "task-a",
            "trial-1",
            "reward",
            "score",
            0.25,
            status=AgentEvalScoreStatus.PARTIAL,
        ),
        _score("task-a", "trial-1", "retries", "count", 3),
        _score("task-a", "trial-1", "complete", "passed", False),
        _score("task-b", "trial-0", "reward", "score", 0.0),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)

    assert _pairs(summary.task_metric_values) == {
        "task-a": {
            "complete.passed": [("trial-0", True), ("trial-1", False)],
            "retries.count": [("trial-0", 2), ("trial-1", 3)],
            "reward.score": [("trial-0", 1.0), ("trial-1", 0.25)],
            "verdict.label": [("trial-0", "good")],
        },
        "task-b": {"reward.score": [("trial-0", 0.0)]},
    }

    # `==` cannot see the type change (2 == 2.0, True == 1.0), so assert it directly -- preserving
    # the metric's own type is the whole point.
    records = summary.task_metric_values["task-a"]
    count = records["retries.count"][0].value
    assert isinstance(count, int) and not isinstance(count, bool)
    assert records["complete.passed"][0].value is True
    assert isinstance(records["reward.score"][0].value, float)
    assert records["verdict.label"][0].value_type is TrialMetricValueType.LABEL


def test_task_metric_values_scans_scores_once() -> None:
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = _SinglePassScores(
        [
            _score("task-a", "trial-0", "reward", "score", 1.0),
            _score("task-a", "trial-1", "reward", "score", 0.0),
        ]
    )

    assert _pairs(_task_metric_values(scores, tasks)) == {
        "task-a": {"reward.score": [("trial-0", 1.0), ("trial-1", 0.0)]}
    }


def test_failed_trials_are_recorded_but_metric_failures_are_unmeasured() -> None:
    tasks = [
        _task("flaky", _Metric("reward", MetricOutputSpec.continuous_score("score"))),
        _task("unmeasured", _Metric("reward", MetricOutputSpec.continuous_score("score"))),
    ]
    scores = [
        _score("flaky", "trial-0", "reward", "score", 1.0),
        _failed_score("flaky", "trial-1", trial_failed=True),
        _failed_score("unmeasured", "trial-0", trial_failed=False),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)

    assert _pairs(summary.task_metric_values) == {
        # The dead trial keeps its identity, paired with its None; the unmeasured one has no entry at
        # all, so it is nameable from neither -- that asymmetry is what pass@k depends on.
        "flaky": {"reward.score": [("trial-0", 1.0), ("trial-1", None)]},
        "unmeasured": {"reward.score": []},
    }


def test_a_task_that_produced_no_trial_is_unmeasured_and_counted_in_pass_at_k_nan() -> None:
    # from_scores can be handed a task list wider than the scores -- a caller re-aggregating a subset.
    # The task still declares the metric, so it holds an empty value list and counts as missing
    # coverage: excluding it would report pass@k over a denominator smaller than the task set asked
    # for. A full run cannot reach this state; AgentEvaluator._score_trials refuses to score when a
    # task produced no trial, which test_evaluator.py::test_run_rejects_tasks_without_trials pins.
    reward = _Metric("reward", MetricOutputSpec.continuous_score("score"))
    tasks = [_task("scored", reward), _task("never-ran", reward)]
    scores = [_score("scored", "trial-0", "reward", "score", 1.0)]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)
    by_name = {score.name: score for score in summary.scores.scores}

    assert _pairs(summary.task_metric_values) == {
        "scored": {"reward.score": [("trial-0", 1.0)]},
        "never-ran": {"reward.score": []},
    }
    assert by_name["reward.score.pass@1"].mean == 1.0  # the one measured task passed
    assert by_name["reward.score.pass@1"].count == 1
    assert by_name["reward.score.pass@1"].nan_count == 1  # ...and the unrun one is not hidden


def test_outputs_declared_under_an_unretained_schema_stay_out_even_when_numeric() -> None:
    # Token measurements and other free models are excluded by their declared schema. Emitting a
    # numeric value must not add them back: the value is a measurement, not a per-trial score.
    tasks = [
        _task(
            "task-a",
            _Metric("reward", MetricOutputSpec.continuous_score("score")),
            _Metric("usage", MetricOutputSpec.model("prompt_tokens", _TokenCount)),
        )
    ]
    scores = [
        _score("task-a", "trial-0", "reward", "score", 1.0),
        _score("task-a", "trial-0", "usage", "prompt_tokens", 1234),
    ]

    assert _pairs(AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_values) == {
        "task-a": {"reward.score": [("trial-0", 1.0)]}
    }


def test_one_tasks_schema_exclusion_does_not_suppress_another_tasks_output() -> None:
    # The spec filter is per task: tasks in one run need not declare the same output under the same
    # schema. Task-a declaring usage.prompt_tokens as a free model must not strip it from task-b,
    # which never declared it and whose only evidence is the numeric value it actually emitted.
    tasks = [
        _task("task-a", _Metric("usage", MetricOutputSpec.model("prompt_tokens", _TokenCount))),
        _task("task-b", _Metric("reward", MetricOutputSpec.continuous_score("score"))),
    ]
    scores = [
        _score("task-a", "trial-0", "usage", "prompt_tokens", 100),
        _score("task-b", "trial-0", "reward", "score", 1.0),
        _score("task-b", "trial-0", "usage", "prompt_tokens", 250),  # undeclared on task-b
    ]

    records = AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_values

    # task-a declared it under an unretained schema, so it is not a key there at all -- not even an
    # empty one -- and the numeric value it emitted cannot add it back.
    assert records["task-a"] == {}
    # task-b never declared it, so its emitted numeric value is the only evidence and it is kept.
    assert sorted(records["task-b"]) == ["reward.score", "usage.prompt_tokens"]
    assert _pairs(records)["task-b"]["usage.prompt_tokens"] == [("trial-0", 250)]
    assert isinstance(records["task-b"]["usage.prompt_tokens"][0].value, int)  # not widened to float


def test_nan_metric_values_survive_json_as_a_string() -> None:
    # A metric may legitimately score NaN. json.dumps would write a bare NaN token, which is not
    # valid JSON, so summary.json must carry the string form -- and read it back as a float.
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    summary = AgentEvalSummary.from_scores([_score("task-a", "trial-0", "reward", "score", float("nan"))], tasks=tasks)

    payload = summary.model_dump(mode="json")
    record = payload["task_metric_values"]["task-a"]["reward.score"][0]
    assert record["value"] == "NaN"
    assert record["value_type"] == "number"  # what tells it apart from a label reading "NaN"

    # Strict JSON: no bare NaN/Infinity tokens anywhere in the serialized bundle.
    def _reject(constant: str) -> float:
        raise AssertionError(f"summary.json contains a bare {constant} token")

    reloaded = json.loads(json.dumps(payload), parse_constant=_reject)
    value = AgentEvalSummary.model_validate(reloaded).task_metric_values["task-a"]["reward.score"][0].value
    assert isinstance(value, float) and math.isnan(value)


def test_a_label_and_a_real_nan_are_distinguishable_on_the_wire() -> None:
    # The reason value_type is required on the wire: strict JSON has no NaN literal, so a real NaN
    # travels as the string "NaN" -- the same three bytes as a judge label that happens to read "NaN".
    real_nan = TrialMetricValue(trial_id="t0", value=float("nan"))
    label = TrialMetricValue(trial_id="t1", value_type=TrialMetricValueType.LABEL, value="NaN")

    dumped = [a.model_dump(mode="json") for a in (real_nan, label)]
    assert [d["value"] for d in dumped] == ["NaN", "NaN"]  # identical payloads...
    assert [d["value_type"] for d in dumped] == ["number", "label"]  # ...told apart by the type

    back = [TrialMetricValue.model_validate(d) for d in json.loads(json.dumps(dumped))]
    assert isinstance(back[0].value, float) and math.isnan(back[0].value)
    assert back[1].value == "NaN" and isinstance(back[1].value, str)


def test_a_payload_without_value_type_still_loads() -> None:
    # Bundles written before value_type existed, and hand-built records. The old encoding gave a
    # string exactly one meaning -- the NaN escape -- so that is how a bare string is read.
    legacy_nan = TrialMetricValue.model_validate({"trial_id": "t0", "value": "NaN"})
    assert legacy_nan.value_type is TrialMetricValueType.NUMBER
    assert isinstance(legacy_nan.value, float) and math.isnan(legacy_nan.value)

    assert TrialMetricValue.model_validate({"trial_id": "t1", "value": 5}).value_type is TrialMetricValueType.NUMBER
    assert TrialMetricValue.model_validate({"trial_id": "t2", "value": None}).value_type is TrialMetricValueType.MISSING
    assert TrialMetricValue.model_validate({"trial_id": "t3", "value": "ok"}).value_type is TrialMetricValueType.LABEL


def test_a_record_cannot_claim_one_kind_and_carry_another() -> None:
    for payload in (
        {"trial_id": "t", "value_type": "number", "value": "good"},
        {"trial_id": "t", "value_type": "label", "value": 1.0},
        {"trial_id": "t", "value_type": "label", "value": None},
        {"trial_id": "t", "value_type": "missing", "value": 1.0},
    ):
        with pytest.raises(ValidationError):
            TrialMetricValue.model_validate(payload)


def test_value_type_is_always_present_in_serialized_output() -> None:
    # Optional for the caller (derived from the value), but never absent from what a reader sees --
    # they must not have to guess whether a string is an escaped float or a label.
    for record in (
        TrialMetricValue(trial_id="t", value=1.0),
        TrialMetricValue(trial_id="t", value="good"),
        TrialMetricValue(trial_id="t", value=None),
        TrialMetricValue(trial_id="t", value=float("nan")),
    ):
        assert "value_type" in record.model_dump(mode="json")


def test_without_tasks_there_is_no_spec_to_filter_on() -> None:
    # No tasks means no declared schemas to consult, so every numeric output observed is retained.
    scores = [_score("task-a", "trial-0", "usage", "prompt_tokens", 1234)]

    summary = AgentEvalSummary.from_scores(scores)

    assert _pairs(summary.task_metric_values) == {"task-a": {"usage.prompt_tokens": [("trial-0", 1234)]}}
    assert isinstance(summary.task_metric_values["task-a"]["usage.prompt_tokens"][0].value, int)


def test_values_align_across_keys_by_trial_id_not_position() -> None:
    # A metric that raised drops its record entirely while a dead trial holds its slot as None, so a
    # metric failure shortens its own key's list without shortening its neighbour's. Index i of two
    # keys is then two different trials -- which is exactly why every record names its trial.
    tasks = [
        _task(
            "task-a",
            _Metric("reward", MetricOutputSpec.continuous_score("score")),
            _Metric("steps", MetricOutputSpec.discrete_score("count")),
        )
    ]
    scores = [
        _score("task-a", "trial-0", "reward", "score", 1.0),
        _score("task-a", "trial-0", "steps", "count", 5),
        _failed_score("task-a", "trial-1", trial_failed=False),  # the reward judge timed out
        _score("task-a", "trial-1", "steps", "count", 9),
        _score("task-a", "trial-2", "reward", "score", 0.0),
        _score("task-a", "trial-2", "steps", "count", 7),
    ]

    records = AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_values["task-a"]

    # Position lies: index 1 is trial-2 under reward.score but trial-1 under steps.count.
    assert records["reward.score"][1].trial_id == "trial-2"
    assert records["steps.count"][1].trial_id == "trial-1"
    # trial_id tells the truth, so a join across the two keys is now possible and correct.
    steps_by_trial = {a.trial_id: a.value for a in records["steps.count"]}
    assert [(a.trial_id, a.value, steps_by_trial[a.trial_id]) for a in records["reward.score"]] == [
        ("trial-0", 1.0, 5),
        ("trial-2", 0.0, 7),
    ]


def test_an_undeclared_label_is_discovered_from_the_value_alone() -> None:
    # Load-bearing: the declared branch prepopulates keys from task specs *before* the discovery
    # loop, so a test using a *declared* label would still pass if that loop's gate were left as
    # _semantic_value (which drops strings). Only an undeclared label exercises it.
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = [
        _score("task-a", "trial-0", "reward", "score", 1.0),
        _score("task-a", "trial-0", "verdict", "grade", "excellent"),  # no task declares this
    ]

    assert _pairs(AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_values) == {
        "task-a": {"reward.score": [("trial-0", 1.0)], "verdict.grade": [("trial-0", "excellent")]}
    }

    # Same again with no specs at all, where the filter cannot apply.
    assert _pairs(AgentEvalSummary.from_scores(scores).task_metric_values) == {
        "task-a": {"reward.score": [("trial-0", 1.0)], "verdict.grade": [("trial-0", "excellent")]}
    }


def test_a_label_under_a_scorelike_key_does_not_break_pass_at_k() -> None:
    # _scorelike_outputs unions across all tasks while the spec filter is per task, and
    # validate_metric_result coerces-and-discards -- so a label can reach a key pass@k reads. It must
    # land in nan_count as an unmeasured task, not raise on `"good" >= 1.0`.
    reward = _Metric("reward", MetricOutputSpec.continuous_score("score"))
    tasks = [_task("scored", reward), _task("labelled")]  # 'labelled' declares no metric at all
    scores = [
        _score("scored", "trial-0", "reward", "score", 1.0),
        _score("labelled", "trial-0", "reward", "score", "good"),  # a label under a scorelike key
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)
    by_name = {score.name: score for score in summary.scores.scores}

    assert _pairs(summary.task_metric_values)["labelled"] == {"reward.score": [("trial-0", "good")]}
    assert by_name["reward.score.pass@1"].mean == 1.0  # the one measurable task passed
    assert by_name["reward.score.pass@1"].count == 1
    assert by_name["reward.score.pass@1"].nan_count == 1  # the labelled task is unmeasured, not failed


def test_a_view_over_a_label_output_reduces_to_nothing_rather_than_raising() -> None:
    # Views read MetricOutput through _semantic_value, which still projects to float and drops
    # strings -- so widening the value record cannot leak a label into view arithmetic. This pins
    # that separation; it fails loudly if views are ever rewired onto task_metric_values.
    verdict = _Metric("verdict", MetricOutputSpec.label("grade"))
    task = AgentEvalTask(
        id="task-a",
        intent="test",
        inputs={},
        metrics=[verdict],
        views={
            "quality": SemanticView(
                reducer=SemanticReducer.SINGLE, signals=[ViewSignal(metric="verdict", output="grade")]
            )
        },
    )
    scores = [_score("task-a", "trial-0", "verdict", "grade", "excellent")]

    summary = AgentEvalSummary.from_scores(scores, tasks=[task])
    view = summary.score("view.quality")

    assert view.count == 0 and view.nan_count == 1  # reduced to nothing, no exception
    assert _pairs(summary.task_metric_values) == {"task-a": {"verdict.grade": [("trial-0", "excellent")]}}


def test_dead_trials_are_nameable_from_the_summary_alone() -> None:
    # AALGO-428 needs to say *which* trial died to roll up exception types. Before records carried a
    # trial id the summary could count dead trials but not name one; now it is a lookup key out to
    # trials.jsonl, where the error lives.
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = [
        _score("task-a", "trial-0", "reward", "score", 1.0),
        _failed_score("task-a", "trial-1", trial_failed=True),
        _failed_score("task-a", "trial-2", trial_failed=False),  # metric raised: unmeasured, not dead
    ]

    records = AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_values["task-a"]["reward.score"]

    assert {a.trial_id for a in records if a.value is None} == {"trial-1"}


def test_duplicate_trial_ids_are_two_records_not_one() -> None:
    # Nothing enforces trial-id uniqueness, so the value list must never be re-keyed by trial id:
    # collapsing two records into one would silently drop pass@k's n. A list cannot lose cardinality.
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = [
        _score("task-a", "dup", "reward", "score", 1.0),
        _score("task-a", "dup", "reward", "score", 0.0),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)
    by_name = {score.name: score for score in summary.scores.scores}

    assert _pairs(summary.task_metric_values) == {"task-a": {"reward.score": [("dup", 1.0), ("dup", 0.0)]}}
    assert by_name["reward.score.pass@1"].mean == pytest.approx(0.5)  # n=2, not n=1
    assert by_name["reward.score.pass@2"].mean == pytest.approx(1.0)


def test_metric_values_projects_to_a_bare_value_list() -> None:
    # The projection pass@k reads: order, cardinality and None-vs-absent preserved exactly.
    records = [
        TrialMetricValue(trial_id="t0", value=1.0),
        TrialMetricValue(trial_id="t1", value=None),
        TrialMetricValue(trial_id="t2", value=0.0),
    ]

    assert metric_values(records) == [1.0, None, 0.0]

    # A label is preserved faithfully by metric_values and dropped by the arithmetic projection:
    # a categorical verdict is an unmeasured trial, not a failed one.
    with_label = [*records, TrialMetricValue(trial_id="t3", value="excellent")]
    assert metric_values(with_label) == [1.0, None, 0.0, "excellent"]
    assert numeric_metric_values(with_label) == [1.0, None, 0.0]
    assert numeric_metric_values([]) == []
    assert metric_values([]) == []


def test_pass_at_k_aggregates_are_unchanged_by_carrying_trial_ids() -> None:
    """Golden table captured from the pre-change implementation, before records carried trial ids.

    Every branch pass@k distinguishes is present: a task that always passes, one whose trials
    include a dead one (None counts toward ``n``), one whose metric raised on a trial (dropped
    from ``n``, so it falls out of ``k=2``), and two that yielded nothing at all (``nan_count``).
    """
    reward = _Metric("reward", MetricOutputSpec.continuous_score("score"))
    passed = _Metric("complete", MetricOutputSpec.boolean("passed"))
    tasks = [_task(t, reward, passed) for t in ("solved", "flaky", "judged-out", "unmeasured", "never-ran")]
    scores = [
        _score("solved", "s0", "reward", "score", 1.0),
        _score("solved", "s0", "complete", "passed", True),
        _score("solved", "s1", "reward", "score", 1.0),
        _score("solved", "s1", "complete", "passed", True),
        _score("solved", "s2", "reward", "score", 1.0),
        _score("solved", "s2", "complete", "passed", True),
        _score("flaky", "f0", "reward", "score", 1.0),
        _score("flaky", "f0", "complete", "passed", True),
        _failed_score("flaky", "f1", trial_failed=True),
        _failed_score("flaky", "f1", trial_failed=True, metric_type="complete"),
        _score("flaky", "f2", "reward", "score", 0.0),
        _score("flaky", "f2", "complete", "passed", False),
        _score("judged-out", "j0", "reward", "score", 1.0),
        _score("judged-out", "j0", "complete", "passed", True),
        _failed_score("judged-out", "j1", trial_failed=False),
        _failed_score("judged-out", "j1", trial_failed=False, metric_type="complete"),
        _failed_score("unmeasured", "u0", trial_failed=False),
        _failed_score("unmeasured", "u0", trial_failed=False, metric_type="complete"),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)
    actual = {s.name: (s.mean, s.count, s.nan_count) for s in summary.scores.scores if ".pass@" in s.name}

    assert actual == {
        "complete.passed.pass@1": (pytest.approx(0.7777777777777777), 3, 2),
        "complete.passed.pass@2": (pytest.approx(0.8333333333333333), 2, 2),
        "complete.passed.pass@3": (pytest.approx(1.0), 2, 2),
        "reward.score.pass@1": (pytest.approx(0.7777777777777777), 3, 2),
        "reward.score.pass@2": (pytest.approx(0.8333333333333333), 2, 2),
        "reward.score.pass@3": (pytest.approx(1.0), 2, 2),
    }


def test_summary_without_task_metric_values_loads_as_empty() -> None:
    assert AgentEvalSummary.model_validate({}).task_metric_values == {}


def test_vendored_summary_accepts_task_metric_values() -> None:
    from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalSummary as VendoredAgentEvalSummary

    payload = {
        "task_metric_values": {
            "task-a": {"reward.score": [{"trial_id": "t0", "value": 1.0}, {"trial_id": "t1", "value": None}]}
        }
    }

    # The payload deliberately omits value_type, so this doubles as the legacy-derivation regression.
    records = VendoredAgentEvalSummary.model_validate(payload).task_metric_values
    assert [(a.trial_id, a.value) for a in records["task-a"]["reward.score"]] == [("t0", 1.0), ("t1", None)]


def test_vendored_module_exposes_the_public_value_api() -> None:
    # The byte-copy test below proves file parity, not that the names are usable through the shipped
    # package. These are the surface a consumer of nemo-platform actually imports.
    from nemo_platform.beta.evaluator.agent_eval.results import (
        AgentEvalSummary as VendoredSummary,
    )
    from nemo_platform.beta.evaluator.agent_eval.results import (
        TrialMetricValue as VendoredValue,
    )
    from nemo_platform.beta.evaluator.agent_eval.results import (
        TrialMetricValueType as VendoredType,
    )
    from nemo_platform.beta.evaluator.agent_eval.results import (
        numeric_metric_values as vendored_numeric,
    )

    records = [VendoredValue(trial_id="t0", value=1.0), VendoredValue(trial_id="t1", value="good")]
    assert vendored_numeric(records) == [1.0]  # the label is dropped, as in the source module
    assert records[1].value_type is VendoredType.LABEL

    summary = VendoredSummary(task_metric_values={"task-a": {"reward.score": records}})
    [outcomes] = summary.task_outcomes()
    assert outcomes.task_id == "task-a" and outcomes.outcomes[0].metric_name == "reward.score"


def test_vendored_results_module_is_a_verbatim_copy_of_this_one() -> None:
    # `make vendor` mirrors this module into the SDK, rewriting only the package root. Validating the
    # field shape (above) would still pass against a stale copy carrying older filtering or docs, so
    # pin the whole file: any edit here that is not mirrored is drift between two live code paths.
    import nemo_evaluator_sdk.agent_eval.results as source
    import nemo_platform.beta.evaluator.agent_eval.results as vendored

    expected = (
        Path(source.__file__)
        .read_text(encoding="utf-8")
        .replace("from nemo_evaluator_sdk.", "from nemo_platform.beta.evaluator.")
    )

    assert Path(vendored.__file__).read_text(encoding="utf-8") == expected, (
        "sdk/python/.../beta/evaluator/agent_eval/results.py is out of sync; re-run `make vendor`"
    )


def test_gym_example_rejects_a_bundle_written_before_task_metric_values(tmp_path: Path) -> None:
    # The field defaults to empty, so an older bundle would load cleanly and simply show no per-task
    # section -- a reader would take that as "no per-task outcomes" rather than "this script cannot
    # see them". Fail with a version message instead.
    from packages.nemo_evaluator_sdk.examples.gym.inspect_results import BundleFormatError, load_bundle

    (tmp_path / "summary.json").write_text(json.dumps({"task_count": 2}), encoding="utf-8")

    with pytest.raises(BundleFormatError, match="predates summary.task_metric_values"):
        load_bundle(tmp_path)


def test_summary_task_outcomes_name_their_own_keys() -> None:
    # task_outcomes() lifts the nested dicts into models whose fields are named, for callers that
    # want a typed object to pass around. It is a read-time view: the summary keeps the dict shape.
    summary = AgentEvalSummary(
        task_metric_values={
            "task-b": {"gym_reward.reward": [TrialMetricValue(trial_id="task-b__bbb", value=0.0)]},
            "task-a": {
                "steps.count": [TrialMetricValue(trial_id="task-a__aaa", value=5)],
                "gym_reward.reward": [TrialMetricValue(trial_id="task-a__aaa", value=1.0)],
            },
        }
    )

    outcomes = summary.task_outcomes()

    assert [o.task_id for o in outcomes] == ["task-a", "task-b"]  # sorted by task
    assert [o.metric_name for o in outcomes[0].outcomes] == ["gym_reward.reward", "steps.count"]  # then metric
    assert [(t.trial_id, t.value) for t in outcomes[0].outcomes[0].trials] == [("task-a__aaa", 1.0)]


def _mixed_metric_summary() -> AgentEvalSummary:
    """One task measured by the metric, one that declared it but yielded nothing, one scored by another."""
    return AgentEvalSummary(
        task_metric_values={
            "task-a": {
                "gym_reward.reward": [
                    TrialMetricValue(trial_id="task-a__aaa", value=1.0),
                    TrialMetricValue(trial_id="task-a__bbb", value=0.0),
                ],
                "steps.count": [TrialMetricValue(trial_id="task-a__aaa", value=7)],
            },
            "task-b": {"gym_reward.reward": []},
            "task-c": {"judge.rating": [TrialMetricValue(trial_id="task-c__ccc", value=0.5)]},
        }
    )


def test_task_outcomes_narrows_to_one_metric() -> None:
    # The filter is what makes the typed view usable for a single-metric report; without it a caller
    # has to re-filter the nested lists by hand, which is what the dict shape already made them do.
    outcomes = _mixed_metric_summary().task_outcomes("gym_reward.reward")

    assert [o.task_id for o in outcomes] == ["task-a", "task-b"]
    assert [[oc.metric_name for oc in o.outcomes] for o in outcomes] == [["gym_reward.reward"], ["gym_reward.reward"]]
    assert [(t.trial_id, t.value) for t in outcomes[0].outcomes[0].trials] == [
        ("task-a__aaa", 1.0),
        ("task-a__bbb", 0.0),
    ]


def test_task_outcomes_drops_a_task_the_metric_never_measured_but_keeps_an_empty_one() -> None:
    # The two states are not the same and must not be flattened together. task-b declared the metric
    # and yielded no usable value -- that is missing coverage, so it stays with an empty trials list
    # and reports as unmeasured. task-c was scored by a different metric entirely; reporting it would
    # invent coverage the run never asked for.
    outcomes = _mixed_metric_summary().task_outcomes("gym_reward.reward")

    by_task = {o.task_id: o for o in outcomes}
    assert "task-c" not in by_task
    assert by_task["task-b"].outcomes[0].trials == []

    # Unfiltered, every task is present including the one scored by another metric.
    assert [o.task_id for o in _mixed_metric_summary().task_outcomes()] == ["task-a", "task-b", "task-c"]


def test_gym_example_reads_task_outcomes_from_summary() -> None:
    # The example reads the SDK's typed view rather than re-deriving one: each row names its own
    # task and metric, and each trial the rollout that produced it.
    from packages.nemo_evaluator_sdk.examples.gym.inspect_results import show_per_task

    outcomes = _mixed_metric_summary().task_outcomes("gym_reward.reward")

    assert [(o.task_id, o.outcomes[0].metric_name) for o in outcomes] == [
        ("task-a", "gym_reward.reward"),
        ("task-b", "gym_reward.reward"),
    ]
    # The display path is what the projection to floats exists for; it must not raise on an empty
    # outcome, which is the task that reports as unmeasured.
    show_per_task(outcomes)
