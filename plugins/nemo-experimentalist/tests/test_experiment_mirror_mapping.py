# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.experimentalist import experiment_mirror as m


def _cand(**kw):
    base = dict(run_id="run-1", label="agent-0", round=0, optimization="baseline")
    base.update(kw)
    return Candidate(**base)


def test_group_name_is_sanitized_and_bounded():
    assert m.group_name("Run_1/ABC") == "opt-run-1-abc"
    assert len(m.group_name("x" * 200)) <= 63


def test_experiment_name_deterministic():
    assert m.experiment_name("opt-run-1", "agent-0", "train") == "opt-run-1-agent-0-train"


def test_status_derivation():
    assert m.experiment_status(_cand(round=0)) == "baseline"
    assert m.experiment_status(_cand(round=2, killed_round=3)) == "killed"
    assert m.experiment_status(_cand(round=2)) == "survived"


def test_group_metadata_carries_run_fields():
    run = ExperimentRun(
        workspace="default",
        agent="a",
        insight=None,
        config_snapshot={"k": 1},
        status="running",
        rounds_completed=2,
        winner_agent="agent-3",
    )
    md = m.group_metadata(run)
    # Platform metadata is dict[str, str]: config_snapshot is JSON-serialized and the
    # round counter is stringified, so the create/update body passes server validation.
    assert md == {
        "agent": "a",
        "config_snapshot": '{"k": 1}',
        "status": "running",
        "rounds_completed": "2",
        "winner_candidate": "agent-3",
    }


def test_group_metadata_omits_winner_until_present():
    run = ExperimentRun(
        workspace="default",
        agent="a",
        insight=None,
        config_snapshot={"k": 1},
        status="running",
        rounds_completed=0,
        winner_agent=None,
    )
    md = m.group_metadata(run)
    # None is not a valid metadata value; omit the key rather than send null (would 422).
    assert "winner_candidate" not in md
    assert all(isinstance(v, str) for v in md.values())


def test_experiment_metadata_is_identity_only():
    md = m.experiment_metadata(_cand(round=1), "train")
    # round stringified for dict[str, str] metadata; no reward/trials copied
    assert md == {"round": "1", "candidate_id": "agent-0", "split": "train"}


def test_pseudo_source_link_is_a_url():
    assert m.pseudo_source_link("opt-run-1", "agent-0") == "opt://opt-run-1/candidate/agent-0"
