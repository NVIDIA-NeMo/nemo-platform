# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The run's metric contract must actually reach the components that enforce it.

``objective_function`` and ``regression_metrics`` are validated on the run config,
which made them look wired when they were not: every component fell back to its own
default of "maximize reward" and the configured contract was silently ignored. The
failure is invisible -- a run completes, reports, and picks a winner, just against the
wrong objective -- so each construction site is named here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.experimentalist.components.models import MetricTarget
from nemo_experimentalist_plugin.experimentalist.components.selector import ParetoDiversitySelector
from nemo_experimentalist_plugin.experimentalist.strategies import evolutionary
from nemo_experimentalist_plugin.experimentalist.strategies.evolutionary import EvolutionaryStrategy

OBJECTIVES = [MetricTarget(name="pass_rate", direction="maximize")]
REGRESSIONS = [MetricTarget(name="latency", direction="minimize")]


@pytest.fixture
def config() -> EvolutionaryOptimizerConfig:
    return EvolutionaryOptimizerConfig(objective_function=OBJECTIVES, regression_metrics=REGRESSIONS)


def test_the_selector_is_built_with_the_configured_targets(tmp_path: Path, config: EvolutionaryOptimizerConfig) -> None:
    """Without this the winner is chosen against 'reward', whatever the run configured."""
    selector = EvolutionaryStrategy(working_dir=tmp_path, config=config)._selector(config)

    assert isinstance(selector, ParetoDiversitySelector)
    assert selector._objective_metrics == OBJECTIVES
    assert selector._regression_metrics == REGRESSIONS


@pytest.mark.asyncio
async def test_the_proposer_is_built_with_the_configured_targets(
    tmp_path: Path, config: EvolutionaryOptimizerConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Proposer states the objective in its own prompt, so a wrong one misdirects the round."""
    captured: dict[str, Any] = {}

    def capture(role: str, name: str, **kwargs: Any) -> Any:
        captured.update(kwargs)
        raise _Stop

    monkeypatch.setattr(evolutionary, "get_component", capture)
    strategy = EvolutionaryStrategy(working_dir=tmp_path, config=config)
    with pytest.raises(_Stop):
        await strategy._propose_improvements(
            analysis="",
            evolution_tree=evolutionary.EvolutionTree(),
            round_num=1,
            phase="exploration",
            config=config,
        )

    assert captured["objective_metrics"] == OBJECTIVES
    assert captured["regression_metrics"] == REGRESSIONS


def test_defaults_are_used_when_the_run_configures_none(tmp_path: Path) -> None:
    """An unconfigured run still ranks on something, rather than ranking on nothing."""
    default = EvolutionaryOptimizerConfig()
    selector = EvolutionaryStrategy(working_dir=tmp_path, config=default)._selector(default)

    assert isinstance(selector, ParetoDiversitySelector)
    assert [target.name for target in selector._objective_metrics] == [
        target.name for target in default.objective_function
    ]


class _Stop(Exception):
    """Cut the call short once the constructor kwargs have been seen."""
