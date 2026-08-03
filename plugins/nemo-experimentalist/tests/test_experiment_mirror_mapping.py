# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any

from doubles import make_candidate
from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.experimentalist import experiment_mirror as m


def _cand(**kw: Any) -> Candidate:
    return make_candidate(run_id="run-1", label="agent-0", description="baseline", **kw)


def test_group_name_is_sanitized_and_bounded():
    assert m.group_name("Run_1/ABC") == "opt-run-1-abc"
    assert len(m.group_name("x" * 200)) <= 63


def test_experiment_name_deterministic():
    assert m.experiment_name("opt-run-1", "agent-0", "train") == "opt-run-1-agent-0-train"


def test_status_derivation():
    # Baseline is ``ancestor is None``, not a generation-0 sentinel: a strategy that
    # leaves generation at 0 must not have every candidate read as the baseline.
    assert m.experiment_status(_cand(generation=0)) == "baseline"
    assert m.experiment_status(_cand(generation=2, ancestor="agent-0", killed_generation=3)) == "killed"
    assert m.experiment_status(_cand(generation=2, ancestor="agent-0")) == "survived"
    assert m.experiment_status(_cand(generation=2)) == "baseline"


def test_group_metadata_carries_run_fields():
    run = ExperimentRun(
        workspace="default",
        agent="a",
        insight=None,
        config_snapshot={"k": 1},
        status="running",
        progress_completed=2,
        progress_total=5,
        progress_unit="round",
        winner_agent="agent-3",
    )
    md = m.group_metadata(run)
    # Platform metadata is dict[str, str]: config_snapshot is JSON-serialized and the
    # progress counter is stringified, so the create/update body passes server validation.
    assert md == {
        "agent": "a",
        "config_snapshot": '{"k": 1}',
        "status": "running",
        "progress_completed": "2",
        "progress_total": "5",
        "progress_unit": "round",
        "winner_candidate": "agent-3",
    }


def test_group_metadata_omits_winner_until_present():
    run = ExperimentRun(
        workspace="default",
        agent="a",
        insight=None,
        config_snapshot={"k": 1},
        status="running",
        progress_completed=0,
        winner_agent=None,
    )
    md = m.group_metadata(run)
    # None is not a valid metadata value; omit the key rather than send null (would 422).
    assert "winner_candidate" not in md
    assert all(isinstance(v, str) for v in md.values())


def test_experiment_metadata_is_identity_only():
    md = m.experiment_metadata(_cand(generation=1), "train")
    # generation stringified for dict[str, str] metadata; no reward/trials copied.
    # Both id and label: ancestor references are ids, Experiment names use labels.
    assert md == {
        "generation": "1",
        "candidate_id": "id-agent-0",
        "candidate_label": "agent-0",
        "split": "train",
    }


def test_pseudo_source_link_is_a_url():
    assert m.pseudo_source_link("opt-run-1", "agent-0") == "opt://opt-run-1/candidate/agent-0"
