# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_experimentalist_plugin.config import (
    EvolutionaryOptimizerConfig,
    has_metric_dimensions,
    pareto_objectives,
    with_insight_objective,
)
from nemo_experimentalist_plugin.entities import MetricTarget, TrialResult, TrialStatus
from nemo_experimentalist_plugin.experimentalist.components.models import missing_objective_reason


def test_metric_contract_supports_multiple_objective_metrics() -> None:
    config = EvolutionaryOptimizerConfig.model_validate(
        {
            "objective_function": [
                {"name": "tokens", "direction": "minimize"},
                {"name": "cost", "direction": "minimize"},
            ],
            "regression_metrics": [{"name": "success_rate", "direction": "maximize"}],
        }
    )

    assert config.optimization_policy() == (
        "Optimize these objective metric(s): tokens (minimize), cost (minimize). "
        "Do not regress these metric(s): success_rate (maximize). "
        "Metric values, including aggregates, are produced by the evaluator; do not invent formulas or weights."
    )


def test_metric_contract_treats_an_evaluator_aggregate_as_a_metric() -> None:
    config = EvolutionaryOptimizerConfig.model_validate(
        {"objective_function": [{"name": "quality", "direction": "maximize"}]}
    )

    assert [target.name for target in config.objective_function] == ["quality"]


def test_pareto_ranking_uses_only_objectives_and_normalizes_minimization() -> None:
    config = EvolutionaryOptimizerConfig.model_validate(
        {
            "objective_function": [
                {"name": "tokens", "direction": "minimize"},
                {"name": "cost", "direction": "minimize"},
            ],
            "regression_metrics": [{"name": "success", "direction": "maximize"}],
        }
    )

    assert pareto_objectives({"tokens": 10.0, "cost": 2.0, "success": 0.9}, config.objective_function) == {
        "tokens": -10.0,
        "cost": -2.0,
    }


def test_metric_dimensions_require_only_the_objectives_used_for_pareto_ranking() -> None:
    objectives = [MetricTarget(name="quality", direction="maximize")]
    regressions = [MetricTarget(name="cost", direction="minimize")]

    assert has_metric_dimensions({"quality": 0.9}, objectives)
    assert not has_metric_dimensions({"cost": 8.0}, objectives)
    assert has_metric_dimensions({"quality": 0.9, "cost": 11.0}, objectives)
    assert not has_metric_dimensions({"quality": 0.9}, [*objectives, *regressions])


def _trial(status: TrialStatus, *, error_type: str | None = None) -> TrialResult:
    return TrialResult(
        id=f"task__{status}",
        task_id="task",
        status=status,
        error=None if error_type is None else {"type": error_type},
    )


@pytest.mark.parametrize(
    ("trials", "metrics", "expected"),
    [
        # Measured: nothing to explain.
        ([_trial("completed")], {"reward": 0.0}, None),
        # No trials at all: the evaluator itself produced nothing.
        ([], {}, "the evaluator produced no trials, so 'reward' was never measured"),
        # Every trial failed. Harbor's own diagnosis is on the trials; name it.
        (
            [_trial("failed", error_type="RewardFileNotFoundError")],
            {},
            "0/1 trials completed (RewardFileNotFoundError), so 'reward' was never measured",
        ),
        # Mixed failures are counted, most frequent first.
        (
            [
                _trial("failed", error_type="AgentTimeoutError"),
                _trial("failed", error_type="AgentTimeoutError"),
                _trial("failed"),
            ],
            {},
            "0/3 trials completed (AgentTimeoutError ×2, unknown), so 'reward' was never measured",
        ),
        # The silent shape: the verifier ran, exited cleanly, and emitted no metric.
        ([_trial("completed"), _trial("completed")], {}, "2/2 trials completed, but none reported 'reward'"),
        # A trial can carry other metrics and still miss the objective.
        ([_trial("completed")], {"latency": 3.0}, "1/1 trials completed, but none reported 'reward'"),
    ],
)
def test_missing_objective_reason_names_the_evidence_behind_an_absent_metric(
    trials: list[TrialResult],
    metrics: dict[str, float],
    expected: str | None,
) -> None:
    objectives = [MetricTarget(name="reward", direction="maximize")]

    assert missing_objective_reason(trials, metrics, objectives) == expected


@pytest.mark.parametrize(
    "config",
    [
        {"objective_function": []},
        {
            "objective_function": [
                {"name": "reward", "direction": "maximize"},
                {"name": "reward", "direction": "minimize"},
            ]
        },
        {
            "objective_function": [{"name": "reward", "direction": "maximize"}],
            "regression_metrics": [{"name": "reward", "direction": "maximize"}],
        },
    ],
)
def test_metric_contract_rejects_ambiguous_or_overlapping_targets(config: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EvolutionaryOptimizerConfig.model_validate(config)


def test_insight_metrics_become_objectives_and_existing_targets_become_guardrails() -> None:
    config = EvolutionaryOptimizerConfig.model_validate(
        {
            "objective_function": [{"name": "cost", "direction": "minimize"}],
            "regression_metrics": [{"name": "safety", "direction": "maximize"}],
        }
    )

    effective = with_insight_objective(config, ("uses_required_tool", "cites_source"))

    assert [target.name for target in effective.objective_function] == ["uses_required_tool", "cites_source"]
    assert all(target.direction == "maximize" for target in effective.objective_function)
    # Demoted targets are carried across whole, `target` included. The authored insight
    # objectives get none: an LLM-invented metric has no known satisfied value, so a
    # Mode 1 run cannot stop early on one and falls back to its round budget.
    assert [target.model_dump() for target in effective.regression_metrics] == [
        {"name": "cost", "direction": "minimize", "target": None},
        {"name": "safety", "direction": "maximize", "target": None},
    ]
    assert all(target.target is None for target in effective.objective_function)
