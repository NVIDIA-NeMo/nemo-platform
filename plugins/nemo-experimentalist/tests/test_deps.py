# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ExperimentalistDeps validation: insight and/or agent may be set (or combined)."""

from pathlib import Path

import pytest
from nemo_eval_author_plugin.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.deps import ExperimentalistDeps


def _datasets(tmp_path: Path) -> dict:
    # DatasetRef is a lazy URI handle resolved at evaluation time, so the paths
    # need not exist here.
    return {
        "train_dataset": DatasetRef(uri=str(tmp_path / "train")),
        "validation_dataset": DatasetRef(uri=str(tmp_path / "val")),
    }


def _task_template(tmp_path: Path) -> DatasetRef:
    return DatasetRef(uri=str(tmp_path / "template"))


def test_agent_only_ok(tmp_path: Path) -> None:
    ExperimentalistDeps(agent="ssh://git@h/g/r.git@main", **_datasets(tmp_path))


def test_insight_only_ok(tmp_path: Path) -> None:
    ExperimentalistDeps(insight="ins-1", task_template=_task_template(tmp_path), **_datasets(tmp_path))


def test_insight_and_agent_combined_ok(tmp_path: Path) -> None:
    # The Mode-1 PR workflow: an insight guides optimization while a git agent
    # supplies the code + PR target. Both set together is now valid.
    deps = ExperimentalistDeps(
        insight="ins-1",
        agent="ssh://git@h/g/r.git@main",
        task_template=_task_template(tmp_path),
        **_datasets(tmp_path),
    )
    assert deps.insight == "ins-1"
    assert deps.agent == "ssh://git@h/g/r.git@main"


def test_insight_without_task_template_raises(tmp_path: Path) -> None:
    # Mode 1 needs a task template to fill from production traces.
    with pytest.raises(ValueError, match="task_template"):
        ExperimentalistDeps(insight="ins-1", **_datasets(tmp_path))


def test_neither_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be set"):
        ExperimentalistDeps(**_datasets(tmp_path))
