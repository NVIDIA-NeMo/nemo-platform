# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Every run-config value must reach the component that reads it.

A value declared on the run config and read by nobody is the worst kind of defect here:
the run completes, reports and picks a winner, just against settings other than the ones
the file states -- while `config_snapshot` records it as correct. Review found four of
these at once, so each construction site is named rather than covered by one general
assertion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from doubles import FakeBackend, make_context
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig, with_insight_objective
from nemo_experimentalist_plugin.entities import MetricTarget
from nemo_experimentalist_plugin.experimentalist.components.selector import ParetoDiversitySelector
from nemo_experimentalist_plugin.experimentalist.strategies.evolutionary import EvolutionaryStrategy

OBJECTIVES = [MetricTarget(name="pass_rate", direction="maximize")]
REGRESSIONS = [MetricTarget(name="latency", direction="minimize")]


def _capturing_context(tmp_path: Path, captured: dict[str, Any]):
    """A context whose `component()` records the kwargs instead of building anything."""
    ctx = make_context(root=tmp_path, backend=FakeBackend())

    def _component(role: str, name: str, **kwargs: Any) -> Any:
        captured[role] = kwargs
        return object()

    ctx.component = _component  # type: ignore[method-assign]
    return ctx


def test_the_selector_is_built_with_the_configured_targets(tmp_path: Path) -> None:
    """Without this the winner is chosen against 'reward', whatever the run configured."""
    config = EvolutionaryOptimizerConfig(objective_function=OBJECTIVES, regression_metrics=REGRESSIONS)
    selector = EvolutionaryStrategy(working_dir=tmp_path, config=config)._selector(config)

    assert isinstance(selector, ParetoDiversitySelector)
    assert selector._objective_metrics == OBJECTIVES
    assert selector._regression_metrics == REGRESSIONS


def test_the_terminator_is_built_with_the_runs_convergence_window(tmp_path: Path) -> None:
    """`min_rounds_before_stopping` sits on the run config beside `max_rounds`.

    It had a second home on `TerminatorConfig` with an independent default of 3, and the
    component read *that* one — so a run asking to stop after 2 rounds was accepted,
    recorded in `config_snapshot`, and ignored.
    """
    config = EvolutionaryOptimizerConfig(min_rounds_before_stopping=2)
    captured: dict[str, Any] = {}

    EvolutionaryStrategy(working_dir=tmp_path, config=config)._terminator(
        _capturing_context(tmp_path, captured), config
    )

    assert captured["terminator"]["min_rounds_before_stopping"] == 2


def test_the_trajectory_scorer_is_built_with_the_runs_task_cap(tmp_path: Path) -> None:
    """Same shape: the cap defaulted to None inside the component, so every complete
    trace group was scored however small a cap the run asked for."""
    config = EvolutionaryOptimizerConfig(max_trajectory_tasks=6)
    captured: dict[str, Any] = {}

    EvolutionaryStrategy(working_dir=tmp_path, config=config)._trajectory_scorer(
        _capturing_context(tmp_path, captured), config
    )

    assert captured["trajectory-scorer"]["max_trajectory_tasks"] == 6


def test_the_context_carries_the_runs_metric_contract(tmp_path: Path) -> None:
    """The strategy is built before the host settles the objective, so it reads the
    contract off the context. That is also what progress lines and `run_finished`
    report — without it they fall back to `reward` and omit the winner's real scores."""
    ctx = make_context(
        root=tmp_path, backend=FakeBackend(), objective_metrics=OBJECTIVES, regression_metrics=REGRESSIONS
    )

    assert ctx.objective_metrics == OBJECTIVES
    assert ctx.regression_metrics == REGRESSIONS


def test_authored_metric_keys_become_the_objective_and_demote_the_rest() -> None:
    """What the host computes: authored keys are the objective, configured targets
    survive as guardrails rather than being dropped."""
    config = EvolutionaryOptimizerConfig(objective_function=OBJECTIVES, regression_metrics=REGRESSIONS)

    effective = with_insight_objective(config, ("cites_source",))

    assert [t.name for t in effective.objective_function] == ["cites_source"]
    assert {t.name for t in effective.regression_metrics} == {"pass_rate", "latency"}


@pytest.mark.parametrize("field", ["min_rounds_before_stopping", "max_trajectory_tasks"])
def test_the_value_has_exactly_one_home(field: str) -> None:
    """Two homes for one value is what made these silently ignorable."""
    from nemo_experimentalist_plugin.experimentalist.components.goal_tree import GoalTreeConfig
    from nemo_experimentalist_plugin.experimentalist.components.terminator import TerminatorConfig

    assert field in EvolutionaryOptimizerConfig.model_fields
    assert field not in TerminatorConfig.model_fields
    assert field not in GoalTreeConfig.model_fields
