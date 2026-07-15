# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nemo_insights_plugin.contracts.profile import ProfileError
from nemo_insights_plugin.profile import load_profile, pick_agent_spec

FULL_PROFILE = """\
agent: flight-planner
task_template: ./evals/task_template
datasets:
  train: ./evals/train
  validation: ./evals/validation
experiment_config:
  optimization:
    rounds: 2
framework_skills: [./skills]
workspace: flight-workspace
agent_spec: ./AGENT-SPEC.md
"""


def test_load_profile_reads_analysis_fields_and_ignores_experiment_fields(tmp_path: Path) -> None:
    path = tmp_path / "optimizer.yaml"
    path.write_text(FULL_PROFILE, encoding="utf-8")

    profile = load_profile(path)

    assert profile.agent == "flight-planner"
    assert profile.workspace == "flight-workspace"
    assert profile.agent_spec == "./AGENT-SPEC.md"
    assert profile.profile_dir == tmp_path.resolve()


def test_profile_requires_nonempty_agent(tmp_path: Path) -> None:
    path = tmp_path / "optimizer.yaml"
    path.write_text("agent: ''\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="agent"):
        load_profile(path)


def test_pick_agent_spec_is_profile_relative(tmp_path: Path) -> None:
    path = tmp_path / "optimizer.yaml"
    path.write_text("agent: a\nagent_spec: ./AGENT-SPEC.md\n", encoding="utf-8")
    expected = tmp_path / "AGENT-SPEC.md"
    expected.write_text("# Agent", encoding="utf-8")

    assert pick_agent_spec(load_profile(path)) == expected.resolve()
