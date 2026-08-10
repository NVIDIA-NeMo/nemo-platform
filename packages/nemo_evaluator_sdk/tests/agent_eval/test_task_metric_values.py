# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.results import AgentEvalSummary, _task_metric_values
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


def _failed_score(task_id: str, trial_id: str, *, trial_failed: bool) -> AgentEvalTaskScore:
    details = {TRIAL_STATUS_DETAIL: "failed"} if trial_failed else {"exception_type": "TimeoutError"}
    return AgentEvalTaskScore(
        id=f"run:{task_id}:{trial_id}:reward",
        run_id="run",
        task_id=task_id,
        trial_id=trial_id,
        metric_type="reward",
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

    assert summary.task_metric_values == {
        "task-a": {
            "complete.passed": [1.0, 0.0],
            "retries.count": [2.0, 3.0],
            "reward.score": [1.0, 0.25],
        },
        "task-b": {"reward.score": [0.0]},
    }


def test_task_metric_values_scans_scores_once() -> None:
    tasks = [_task("task-a", _Metric("reward", MetricOutputSpec.continuous_score("score")))]
    scores = _SinglePassScores(
        [
            _score("task-a", "attempt-0", "reward", "score", 1.0),
            _score("task-a", "attempt-1", "reward", "score", 0.0),
        ]
    )

    assert _task_metric_values(scores, tasks) == {"task-a": {"reward.score": [1.0, 0.0]}}


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

    assert summary.task_metric_values == {
        "flaky": {"reward.score": [1.0, None]},
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

    assert summary.task_metric_values == {
        "scored": {"reward.score": [1.0]},
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

    assert AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_values == {"task-a": {"reward.score": [1.0]}}


def test_without_tasks_there_is_no_spec_to_filter_on() -> None:
    # No tasks means no declared schemas to consult, so every numeric output observed is retained.
    scores = [_score("task-a", "attempt-0", "usage", "prompt_tokens", 1234)]

    assert AgentEvalSummary.from_scores(scores).task_metric_values == {"task-a": {"usage.prompt_tokens": [1234.0]}}


def test_attempt_positions_are_comparable_only_within_one_key() -> None:
    # A metric that raised drops its attempt entirely while a dead trial holds its slot as None, so a
    # metric failure shortens its own key's list without shortening its neighbour's. Index i of two
    # keys is then two different trials -- there is no trial id to join on, and callers must not try.
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

    values = AgentEvalSummary.from_scores(scores, tasks=tasks).task_metric_values["task-a"]

    # Index 1 of reward.score is attempt-2; index 1 of steps.count is attempt-1.
    assert values == {"reward.score": [1.0, 0.0], "steps.count": [5.0, 9.0, 7.0]}


def test_summary_without_task_metric_values_loads_as_empty() -> None:
    assert AgentEvalSummary.model_validate({}).task_metric_values == {}


def test_vendored_summary_accepts_task_metric_values() -> None:
    from nemo_platform.beta.evaluator.agent_eval.results import AgentEvalSummary as VendoredAgentEvalSummary

    payload = {"task_metric_values": {"task-a": {"reward.score": [1.0, None]}}}

    assert VendoredAgentEvalSummary.model_validate(payload).task_metric_values == payload["task_metric_values"]


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
    from packages.nemo_evaluator_sdk.examples.gym.inspect_results import per_task_outcomes

    summary = AgentEvalSummary(
        task_metric_values={
            "task-a": {"gym_reward.reward": [1.0, 0.0]},
            "task-b": {"gym_reward.reward": []},
        }
    )

    assert per_task_outcomes(summary, metric_type="gym_reward", output_name="reward") == {
        "task-a": [1.0, 0.0],
        "task-b": [],
    }
