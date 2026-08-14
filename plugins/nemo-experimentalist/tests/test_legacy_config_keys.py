# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Every key this refactor removed must be rejected, by name, with its replacement.

The config tolerates unknown keys, so a removed one is otherwise accepted and ignored
-- and the run then does something other than what the file says. That is the worst
kind of failure here: it is silent, and `config_snapshot` records the run as correct.

Two distinct migrations are covered, because they read differently to whoever hits
them. A `disable_*` flag became "choose no implementation of the role". A config block
moved under `<role>_config` so the bare role key could name the component -- which
means a *string* there is still valid and must keep working.
"""

from __future__ import annotations

import pytest
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig


@pytest.mark.parametrize(
    ("key", "replacement"),
    [("disable_convergence_check", "terminator: null"), ("disable_trajectory_scoring", "trajectory_scorer: null")],
)
def test_a_disable_flag_names_the_role_to_null(key: str, replacement: str) -> None:
    with pytest.raises(ValueError, match=replacement):
        EvolutionaryOptimizerConfig.model_validate({key: True})


@pytest.mark.parametrize(("key", "replacement"), [("analyzer", "analyzer_config"), ("proposer", "proposer_config")])
def test_a_config_block_under_a_role_key_names_the_config_key(key: str, replacement: str) -> None:
    with pytest.raises(ValueError, match=replacement):
        EvolutionaryOptimizerConfig.model_validate({key: {"some": "setting"}})


@pytest.mark.parametrize(("key", "value"), [("analyzer", "trace"), ("proposer", "code-change")])
def test_a_component_name_under_the_same_key_is_still_valid(key: str, value: str) -> None:
    """The whole point of the move: the bare key now selects the component."""
    config = EvolutionaryOptimizerConfig.model_validate({key: value})

    assert getattr(config, key) == value


@pytest.mark.parametrize(
    ("key", "role", "config_key"),
    [
        ("evaluator", "outcome_evaluator", "outcome_evaluator_config"),
        ("evaluation", "outcome_evaluator", "outcome_evaluator_config"),
        ("coder", "builder", "builder_config"),
        ("goal_config", "trajectory_scorer", "trajectory_scorer_config"),
    ],
)
def test_a_renamed_role_names_both_the_role_and_its_config(key: str, role: str, config_key: str) -> None:
    """These are not fields at all, so any value would otherwise be dropped in silence."""
    with pytest.raises(ValueError, match=f"{role}.*{config_key}"):
        EvolutionaryOptimizerConfig.model_validate({key: {"n_attempts": 1}})


@pytest.mark.parametrize("value", ["harbor", {"n_attempts": 1}, None, 3])
def test_a_renamed_role_is_rejected_whatever_the_value(value: object) -> None:
    """A string under `evaluator` reads as "use this component" and would be ignored."""
    with pytest.raises(ValueError, match="outcome_evaluator"):
        EvolutionaryOptimizerConfig.model_validate({"evaluator": value})


def test_models_points_at_nemo_setup() -> None:
    """Model selection left the run config entirely in #1159; say where it went."""
    with pytest.raises(ValueError, match="nemo setup"):
        EvolutionaryOptimizerConfig.model_validate({"models": {"smart": "gpt-5"}})


def test_curator_names_eval_author() -> None:
    with pytest.raises(ValueError, match="'curator' was renamed to 'eval_author'"):
        EvolutionaryOptimizerConfig.model_validate({"curator": {"max_traces": 1}})


def test_a_config_using_the_current_keys_is_accepted() -> None:
    """The rejections must not fire on the spelling they are steering people towards."""
    config = EvolutionaryOptimizerConfig.model_validate(
        {
            "terminator": None,
            "trajectory_scorer": None,
            "outcome_evaluator": "harbor",
            "outcome_evaluator_config": {"n_attempts": 1},
            "builder": "llm-code-edit",
            "analyzer_config": {},
            "proposer_config": {},
        }
    )

    assert config.terminator is None
    assert config.outcome_evaluator == "harbor"
    assert config.outcome_evaluator_config == {"n_attempts": 1}


def test_the_skill_documents_only_live_config_keys() -> None:
    """The skill's example config is what users copy, so a key rejected above is a
    defect that reaches every reader rather than only the person who wrote it.

    The rejections and the documentation drifted apart once already: the skill still
    taught `disable_convergence_check`, `coder` and `evaluator` after all three had
    become errors, so following it produced a run that died at config validation.
    """
    import re
    from pathlib import Path

    import yaml

    skill = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "nemo_experimentalist_plugin"
        / "skills"
        / "nemo-experimentalist"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    fields = set(EvolutionaryOptimizerConfig.model_fields)
    checked = 0
    for block in re.findall(r"```yaml\n(.*?)```", skill, re.DOTALL):
        data = yaml.safe_load(block)
        if not isinstance(data, dict) or "max_rounds" not in data:
            continue  # not a run config
        checked += 1
        unknown = sorted(set(data) - fields)
        assert not unknown, f"SKILL.md documents keys the schema does not have: {unknown}"
        EvolutionaryOptimizerConfig.model_validate(data)

    assert checked, "found no run-config example in SKILL.md; the block matcher is wrong"


def test_the_old_analyzer_component_value_is_rejected_by_name() -> None:
    """`agent-trace` named the evidence twice over and read as a noun pair rather than
    "analyzes traces". A config carrying it would otherwise fail deep in resolution,
    reporting an unknown component instead of the one-word fix."""
    with pytest.raises(ValueError, match="'agent-trace' was renamed to 'trace'"):
        EvolutionaryOptimizerConfig.model_validate({"analyzer": "agent-trace"})


def test_the_current_analyzer_value_is_accepted() -> None:
    """The rejection must not fire on the spelling it steers people towards."""
    assert EvolutionaryOptimizerConfig.model_validate({"analyzer": "trace"}).analyzer == "trace"


def test_the_default_analyzer_resolves() -> None:
    """A default that names a component nothing registers is a run that dies at round 0."""
    from nemo_experimentalist_plugin.experimentalist.registry import resolve

    default = EvolutionaryOptimizerConfig().analyzer
    assert default == "trace"
    assert resolve("root-cause-analyzer", default) is not None
