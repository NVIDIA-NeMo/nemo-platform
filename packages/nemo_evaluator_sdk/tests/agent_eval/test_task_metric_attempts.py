# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.results import (
    AgentEvalAttemptValue,
    AgentEvalSummary,
    _task_metric_attempts,
    attempt_values,
)
from nemo_evaluator_sdk.agent_eval.scores import (
    TRIAL_STATUS_DETAIL,
    AgentEvalDiagnostic,
    AgentEvalDiagnosticSeverity,
    AgentEvalScoreStatus,
    AgentEvalTaskScore,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricResult
from nemo_evaluator_sdk.values.protocol import MetricOutputSpec
from pydantic import RootModel


class _TokenCount(RootModel[int]):
    """A free-model output: numeric, but a measurement rather than a per-attempt score."""


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
    attempts: dict[str, dict[str, list[AgentEvalAttemptValue]]],
) -> dict[str, dict[str, list[tuple[str, float | None]]]]:
    """Flatten attempt records to ``(trial_id, value)`` so assertions stay readable."""
    return {
        task_id: {key: [(a.trial_id, a.value) for a in records] for key, records in by_key.items()}
        for task_id, by_key in attempts.items()
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


def test_summary_exposes_ordered_numeric_attempt_values_per_task() -> None:
    reward = _Metric("reward", MetricOutputSpec.continuous_score("score"))
    retries = _Metric("retries", MetricOutputSpec.discrete_score("count"))
    verdict = _Metric("verdict", MetricOutputSpec.label("label"))
    complete = _Metric("complete", MetricOutputSpec.boolean("passed"))
    tasks = [_task("task-a", reward, retries, verdict, complete), _task("task-b", reward)]
    scores = [
        _score("task-a", "attempt-0", "reward", "score", 1.0),
        _score("task-a", "attempt-0", "retries", "count", 2),
        _score("task-a", "attempt-0", "verdict", "label", "good"),
        _score("task-a", "attempt-0", "complete", "passed", True),
        _score(
            "task-a",
            "attempt-1",
            "reward",
            "score",
            0.25,
            status=AgentEvalScoreStatus.PARTIAL,
        ),
        _score("task-a", "attempt-1", "retries", "count", 3),
        _score("task-a", "attempt-1", "complete", "passed", False),
        _score("task-b", "attempt-0", "reward", "score", 0.0),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)

    assert _pairs(summary.task_metric_attempts) == {
        "task-a": {
            "complete.passed": [("attempt-0", 1.0), ("attempt-1", 0.0)],
            "retries.count": [("attempt-0", 2.0), ("attempt-1", 3.0)],
            "reward.score": [("attempt-0", 1.0), ("attempt-1", 0.25)],
        },
        "task-b": {"reward.score": [("attempt-0", 0.0)]},
    }


def test_task_metric_attempts_scans_scores_once() -> None:
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = _SinglePassScores(
        [
            _score("task-a", "attempt-0", "reward", "score", 1.0),
            _score("task-a", "attempt-1", "reward", "score", 0.0),
        ]
    )

    assert _pairs(_task_metric_attempts(scores, tasks)) == {
        "task-a": {"reward.score": [("attempt-0", 1.0), ("attempt-1", 0.0)]}
    }


def test_failed_trials_are_attempts_but_metric_failures_are_unmeasured() -> None:
    tasks = [
        _task("flaky", _Metric("reward", MetricOutputSpec.continuous_score("score"))),
        _task("unmeasured", _Metric("reward", MetricOutputSpec.continuous_score("score"))),
    ]
    scores = [
        _score("flaky", "attempt-0", "reward", "score", 1.0),
        _failed_score("flaky", "attempt-1", trial_failed=True),
        _failed_score("unmeasured", "attempt-0", trial_failed=False),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)

    assert _pairs(summary.task_metric_attempts) == {
        # The dead trial keeps its identity, paired with its None; the unmeasured one has no entry at
        # all, so it is nameable from neither -- that asymmetry is what pass@k depends on.
        "flaky": {"reward.score": [("attempt-0", 1.0), ("attempt-1", None)]},
        "unmeasured": {"reward.score": []},
    }


def test_a_task_that_produced_no_trial_is_unmeasured_and_counted_in_pass_at_k_nan() -> None:
    # A runner may return no trial at all for a requested task (Harbor warns and carries on). The task
    # still declares the metric, so it holds an empty attempt list and counts as missing coverage --
    # excluding it would report pass@k over a denominator smaller than the task set that was asked for.
    reward = _Metric("reward", MetricOutputSpec.continuous_score("score"))
    tasks = [_task("scored", reward), _task("never-ran", reward)]
    scores = [_score("scored", "attempt-0", "reward", "score", 1.0)]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)
    by_name = {score.name: score for score in summary.scores.scores}

    assert _pairs(summary.task_metric_attempts) == {
        "scored": {"reward.score": [("attempt-0", 1.0)]},
        "never-ran": {"reward.score": []},
    }
    assert by_name["reward.score.pass@1"].mean == 1.0  # the one measured task passed
    assert by_name["reward.score.pass@1"].count == 1
    assert by_name["reward.score.pass@1"].nan_count == 1  # ...and the unrun one is not hidden


def test_outputs_declared_under_an_unretained_schema_stay_out_even_when_numeric() -> None:
    # Token measurements and other free models are excluded by their declared schema. Emitting a
    # numeric value must not add them back: the value is a measurement, not a per-attempt score.
    tasks = [
        _task(
            "task-a",
            _Metric("reward", MetricOutputSpec.continuous_score("score")),
            _Metric("usage", MetricOutputSpec.model("prompt_tokens", _TokenCount)),
        )
    ]
    scores = [
        _score("task-a", "attempt-0", "reward", "score", 1.0),
        _score("task-a", "attempt-0", "usage", "prompt_tokens", 1234),
    ]

    assert _pairs(AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_attempts) == {
        "task-a": {"reward.score": [("attempt-0", 1.0)]}
    }


def test_without_tasks_there_is_no_spec_to_filter_on() -> None:
    # No tasks means no declared schemas to consult, so every numeric output observed is retained.
    scores = [_score("task-a", "attempt-0", "usage", "prompt_tokens", 1234)]

    assert _pairs(AgentEvalSummary.from_scores(scores).task_metric_attempts) == {
        "task-a": {"usage.prompt_tokens": [("attempt-0", 1234.0)]}
    }


def test_attempts_align_across_keys_by_trial_id_not_position() -> None:
    # A metric that raised drops its attempt entirely while a dead trial holds its slot as None, so a
    # metric failure shortens its own key's list without shortening its neighbour's. Index i of two
    # keys is then two different trials -- which is exactly why every attempt names its trial.
    tasks = [
        _task(
            "task-a",
            _Metric("reward", MetricOutputSpec.continuous_score("score")),
            _Metric("steps", MetricOutputSpec.discrete_score("count")),
        )
    ]
    scores = [
        _score("task-a", "attempt-0", "reward", "score", 1.0),
        _score("task-a", "attempt-0", "steps", "count", 5),
        _failed_score("task-a", "attempt-1", trial_failed=False),  # the reward judge timed out
        _score("task-a", "attempt-1", "steps", "count", 9),
        _score("task-a", "attempt-2", "reward", "score", 0.0),
        _score("task-a", "attempt-2", "steps", "count", 7),
    ]

    attempts = AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_attempts["task-a"]

    # Position lies: index 1 is attempt-2 under reward.score but attempt-1 under steps.count.
    assert attempts["reward.score"][1].trial_id == "attempt-2"
    assert attempts["steps.count"][1].trial_id == "attempt-1"
    # trial_id tells the truth, so a join across the two keys is now possible and correct.
    steps_by_trial = {a.trial_id: a.value for a in attempts["steps.count"]}
    assert [(a.trial_id, a.value, steps_by_trial[a.trial_id]) for a in attempts["reward.score"]] == [
        ("attempt-0", 1.0, 5.0),
        ("attempt-2", 0.0, 7.0),
    ]


def test_dead_trials_are_nameable_from_the_summary_alone() -> None:
    # AALGO-428 needs to say *which* trial died to roll up exception types. Before attempts carried a
    # trial id the summary could count dead attempts but not name one; now it is a join key out to
    # trials.jsonl, where the error lives.
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = [
        _score("task-a", "attempt-0", "reward", "score", 1.0),
        _failed_score("task-a", "attempt-1", trial_failed=True),
        _failed_score("task-a", "attempt-2", trial_failed=False),  # metric raised: unmeasured, not dead
    ]

    attempts = AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_attempts["task-a"]["reward.score"]

    assert {a.trial_id for a in attempts if a.value is None} == {"attempt-1"}


def test_duplicate_trial_ids_are_two_attempts_not_one() -> None:
    # Nothing enforces trial-id uniqueness, so the attempt list must never be re-keyed by trial id:
    # collapsing two attempts into one would silently drop pass@k's n. A list cannot lose cardinality.
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = [
        _score("task-a", "dup", "reward", "score", 1.0),
        _score("task-a", "dup", "reward", "score", 0.0),
    ]

    summary = AgentEvalSummary.from_scores(scores, tasks=tasks)
    by_name = {score.name: score for score in summary.scores.scores}

    assert _pairs(summary.task_metric_attempts) == {"task-a": {"reward.score": [("dup", 1.0), ("dup", 0.0)]}}
    assert by_name["reward.score.pass@1"].mean == pytest.approx(0.5)  # n=2, not n=1
    assert by_name["reward.score.pass@2"].mean == pytest.approx(1.0)


def test_attempt_values_projects_to_a_bare_value_list() -> None:
    # The projection pass@k reads: order, cardinality and None-vs-absent preserved exactly.
    attempts = [
        AgentEvalAttemptValue(trial_id="t0", value=1.0),
        AgentEvalAttemptValue(trial_id="t1", value=None),
        AgentEvalAttemptValue(trial_id="t2", value=0.0),
    ]

    assert attempt_values(attempts) == [1.0, None, 0.0]
    assert attempt_values([]) == []


def test_pass_at_k_aggregates_are_unchanged_by_carrying_trial_ids() -> None:
    """Golden table captured from the pre-change implementation, before attempts carried trial ids.

    Every branch pass@k distinguishes is present: a task that always passes, one whose attempts
    include a dead trial (None counts toward ``n``), one whose metric raised on an attempt (dropped
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


def test_summary_without_task_metric_attempts_loads_as_empty() -> None:
    assert AgentEvalSummary.model_validate({}).task_metric_attempts == {}


def test_vendored_summary_accepts_task_metric_attempts() -> None:
    from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalSummary as VendoredAgentEvalSummary

    payload = {
        "task_metric_attempts": {
            "task-a": {"reward.score": [{"trial_id": "t0", "value": 1.0}, {"trial_id": "t1", "value": None}]}
        }
    }

    attempts = VendoredAgentEvalSummary.model_validate(payload).task_metric_attempts
    assert [(a.trial_id, a.value) for a in attempts["task-a"]["reward.score"]] == [("t0", 1.0), ("t1", None)]


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


def test_gym_example_reads_task_outcomes_from_summary() -> None:
    from packages.nemo_evaluator_sdk.examples.gym.inspect_results import per_task_attempts, per_task_outcomes

    summary = AgentEvalSummary(
        task_metric_attempts={
            "task-a": {
                "gym_reward.reward": [
                    AgentEvalAttemptValue(trial_id="task-a__aaa", value=1.0),
                    AgentEvalAttemptValue(trial_id="task-a__bbb", value=0.0),
                ]
            },
            "task-b": {"gym_reward.reward": []},
        }
    )

    # The example's headline accessor keeps its bare-value shape...
    assert per_task_outcomes(summary, metric_type="gym_reward", output_name="reward") == {
        "task-a": [1.0, 0.0],
        "task-b": [],
    }
    # ...and its sibling exposes the identity that makes an attempt traceable back to a rollout.
    attempts = per_task_attempts(summary, metric_type="gym_reward", output_name="reward")
    assert [(a.trial_id, a.value) for a in attempts["task-a"]] == [("task-a__aaa", 1.0), ("task-a__bbb", 0.0)]
