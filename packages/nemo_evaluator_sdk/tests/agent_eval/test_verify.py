# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the generic verifier mechanic."""

from __future__ import annotations

from pathlib import Path

from nemo_evaluator_sdk.agent_eval.runtimes.verify import (
    apply_verify_to_metadata,
    collect_verifier_outcome,
    skipped_outcome,
)


def test_collect_reads_reward_file_when_present(tmp_path: Path) -> None:
    (tmp_path / "reward.txt").write_text("1\n", encoding="utf-8")
    (tmp_path / "test-stdout.txt").write_text("PASSED", encoding="utf-8")
    outcome = collect_verifier_outcome(ok=False, exit_code=3, log_dir=tmp_path)
    # reward.txt is authoritative even when the process exit said not-ok.
    assert outcome.ran and outcome.reward == 1 and outcome.exit_code == 3
    assert outcome.stdout == "PASSED"


def test_collect_derives_and_writes_reward_when_missing(tmp_path: Path) -> None:
    outcome = collect_verifier_outcome(ok=True, exit_code=0, log_dir=tmp_path)
    assert outcome.reward == 1 and outcome.passed is True
    assert (tmp_path / "reward.txt").read_text(encoding="utf-8").strip() == "1"


def test_apply_to_metadata_stamps_and_skips(tmp_path: Path) -> None:
    meta: dict[str, object] = {}
    apply_verify_to_metadata(meta, skipped_outcome())
    assert meta == {"verify_status": "skipped"}

    meta2: dict[str, object] = {}
    apply_verify_to_metadata(meta2, collect_verifier_outcome(ok=True, exit_code=0, log_dir=tmp_path))
    assert meta2["verify_status"] == "ok" and meta2["reward"] == 1 and meta2["passed"] is True
