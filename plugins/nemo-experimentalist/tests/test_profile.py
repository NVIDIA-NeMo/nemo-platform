# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from unittest.mock import Mock

import pytest
from nemo_experimentalist_plugin import profile as profile_module
from nemo_experimentalist_plugin.profile import AgentProfile, load_profile
from nemo_insights_plugin.contracts.profile import PROFILE_FILENAME, ProfileError

MINIMAL = """\
agent: flight-planner
task_template: ./evals/task_template
datasets:
  train: ./evals/train
  validation: ./evals/val
"""

SHARED_PROFILE_FIXTURE = """\
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


def write_profile(tmp_path: Path, text: str = MINIMAL) -> Path:
    p = tmp_path / PROFILE_FILENAME
    p.write_text(text, encoding="utf-8")
    return p


def test_load_profile_delegates_to_shared_model_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_profile(tmp_path)
    expected = AgentProfile(
        agent="delegated",
        task_template="template",
        datasets={"train": "train", "validation": "validation"},
        profile_dir=tmp_path,
    )
    loader = Mock(return_value=expected)
    monkeypatch.setattr(profile_module, "load_profile_model", loader)

    assert load_profile(path) is expected
    loader.assert_called_once_with(path, AgentProfile)


def test_load_minimal_profile_defaults(tmp_path: Path) -> None:
    profile = load_profile(write_profile(tmp_path))
    assert profile.agent == "flight-planner"
    assert profile.agent_source == "."
    assert profile.agent_spec is None
    assert profile.experiment_config is None
    assert profile.framework_skills == []
    assert profile.workspace == "default"
    assert profile.profile_dir == tmp_path.resolve()


def test_missing_required_field_names_it(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="task_template"):
        load_profile(write_profile(tmp_path, "agent: a\ndatasets:\n  train: t\n  validation: v\n"))


def test_unknown_key_raises_shared_profile_error(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="task_templte") as exc_info:
        load_profile(write_profile(tmp_path, MINIMAL + "task_templte: typo\n"))

    assert type(exc_info.value) is ProfileError


def test_profile_dir_is_reserved_for_loader_injection(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="'profile_dir' is reserved"):
        load_profile(write_profile(tmp_path, MINIMAL + "profile_dir: elsewhere\n"))


def test_experiment_config_inline_and_path(tmp_path: Path) -> None:
    inline = load_profile(
        write_profile(tmp_path, MINIMAL + "experiment_config:\n  storage:\n    publish_winner: true\n")
    )
    assert inline.experiment_config == {"storage": {"publish_winner": True}}
    as_path = load_profile(write_profile(tmp_path, MINIMAL + "experiment_config: ./experiment.yaml\n"))
    assert as_path.experiment_config == "./experiment.yaml"


def test_full_profile_matches_shared_contract_shape(tmp_path: Path) -> None:
    profile = load_profile(write_profile(tmp_path, SHARED_PROFILE_FIXTURE))

    assert profile.agent == "flight-planner"
    assert profile.workspace == "flight-workspace"
    assert profile.agent_spec == "./AGENT-SPEC.md"


def test_profile_directory_anchors_shared_insights_path(tmp_path: Path) -> None:
    path = tmp_path / "optimizer.yaml"
    path.write_text(MINIMAL, encoding="utf-8")
    profile = load_profile(path)

    assert profile.profile_dir / ".nemo-optimizer" / "insights.yaml" == (
        tmp_path.resolve() / ".nemo-optimizer" / "insights.yaml"
    )
