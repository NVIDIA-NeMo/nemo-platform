# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_experimentalist_plugin.config import (
    EvolutionaryOptimizerConfig,
    MetricTarget,
    has_metric_dimensions,
    pareto_objectives,
)
from nemo_experimentalist_plugin.experimentalist.components.loop import _with_insight_objective


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

    effective = _with_insight_objective(config, ("uses_required_tool", "cites_source"))

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
