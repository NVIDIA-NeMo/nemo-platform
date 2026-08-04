# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nemo_eval_author_plugin.eval_author import materialization
from nemo_experimentalist_plugin.experimentalist.components.holdout_utils import (
    DEFAULT_BLOCKED_PATHS,
    HELD_OUT_SPLITS,
    HELD_OUT_STORAGE_DIR,
    INSIGHT_TRAIN_SPLIT,
    INSIGHT_VALIDATION_SPLIT,
    VALIDATION_SPLIT,
    ensure_heldout_hidden,
    restore_heldout_splits,
)


def _stage(workspace: Path, split: str) -> Path:
    task_dir = workspace / "dataset" / split / "000-task"
    task_dir.mkdir(parents=True)
    (task_dir / "solution.sh").write_text(f"{split} answer\n")
    return workspace / "dataset" / split


def test_insight_split_names_match_eval_author() -> None:
    """Eval Author names the materialized directories; holdout derives blocked tokens from them."""
    assert INSIGHT_TRAIN_SPLIT == materialization.INSIGHT_TRAIN_SPLIT
    assert INSIGHT_VALIDATION_SPLIT == materialization.INSIGHT_VALIDATION_SPLIT


def test_insight_validation_is_held_out_and_insight_train_is_not() -> None:
    assert INSIGHT_VALIDATION_SPLIT in HELD_OUT_SPLITS
    assert INSIGHT_TRAIN_SPLIT not in HELD_OUT_SPLITS
    assert f"dataset/{INSIGHT_VALIDATION_SPLIT}" in DEFAULT_BLOCKED_PATHS
    assert f"dataset/{INSIGHT_TRAIN_SPLIT}" not in DEFAULT_BLOCKED_PATHS
    assert HELD_OUT_STORAGE_DIR in DEFAULT_BLOCKED_PATHS


def test_hiding_relocates_insight_validation_and_leaves_insight_train_visible(tmp_path: Path) -> None:
    insight_validation = _stage(tmp_path, INSIGHT_VALIDATION_SPLIT)
    insight_train = _stage(tmp_path, INSIGHT_TRAIN_SPLIT)

    ensure_heldout_hidden(tmp_path)

    hidden = tmp_path / HELD_OUT_STORAGE_DIR / INSIGHT_VALIDATION_SPLIT
    assert not insight_validation.exists()
    assert (hidden / "000-task" / "solution.sh").read_text() == f"{INSIGHT_VALIDATION_SPLIT} answer\n"
    assert (insight_train / "000-task" / "solution.sh").exists()


@pytest.mark.parametrize("split", [VALIDATION_SPLIT, INSIGHT_VALIDATION_SPLIT])
def test_scoring_round_trip_restores_then_re_hides_each_held_out_split(tmp_path: Path, split: str) -> None:
    visible = _stage(tmp_path, split)
    splits = frozenset({split})

    ensure_heldout_hidden(tmp_path, splits=splits)
    assert not visible.exists()

    restore_heldout_splits(tmp_path, splits=splits)
    assert (visible / "000-task" / "solution.sh").read_text() == f"{split} answer\n"

    ensure_heldout_hidden(tmp_path, splits=splits)
    assert not visible.exists()
    assert (tmp_path / HELD_OUT_STORAGE_DIR / split / "000-task" / "solution.sh").exists()


def test_restoring_one_half_leaves_the_other_hidden(tmp_path: Path) -> None:
    _stage(tmp_path, VALIDATION_SPLIT)
    _stage(tmp_path, INSIGHT_VALIDATION_SPLIT)
    ensure_heldout_hidden(tmp_path)

    restore_heldout_splits(tmp_path, splits=frozenset({INSIGHT_VALIDATION_SPLIT}))

    assert (tmp_path / "dataset" / INSIGHT_VALIDATION_SPLIT).exists()
    assert not (tmp_path / "dataset" / VALIDATION_SPLIT).exists()
    assert (tmp_path / HELD_OUT_STORAGE_DIR / VALIDATION_SPLIT).exists()


def test_hiding_is_idempotent_so_it_can_run_before_every_phase(tmp_path: Path) -> None:
    visible = _stage(tmp_path, INSIGHT_VALIDATION_SPLIT)
    hidden = tmp_path / HELD_OUT_STORAGE_DIR / INSIGHT_VALIDATION_SPLIT

    for _ in range(3):
        ensure_heldout_hidden(tmp_path)
        assert not visible.exists()
        assert (hidden / "000-task" / "solution.sh").read_text() == f"{INSIGHT_VALIDATION_SPLIT} answer\n"


def test_restoring_replaces_a_path_a_candidate_re_created_while_it_was_hidden(tmp_path: Path) -> None:
    visible = _stage(tmp_path, INSIGHT_VALIDATION_SPLIT)
    ensure_heldout_hidden(tmp_path)
    (visible / "000-task").mkdir(parents=True)
    (visible / "000-task" / "solution.sh").write_text("forged\n")

    restore_heldout_splits(tmp_path, splits=frozenset({INSIGHT_VALIDATION_SPLIT}))

    assert (visible / "000-task" / "solution.sh").read_text() == f"{INSIGHT_VALIDATION_SPLIT} answer\n"
