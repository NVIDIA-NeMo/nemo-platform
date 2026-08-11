# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the run-bundle loader (`read_trials`) — the inverse of `persist_run`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.persistence import persist_run, read_trials
from nemo_evaluator_sdk.agent_eval.results import AgentEvalAttemptValue, AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor


def _write_trial(run_dir: Path, trial: AgentEvalTrial) -> None:
    (run_dir / "trials.jsonl").write_text(json.dumps(trial.model_dump(mode="json")) + "\n", encoding="utf-8")


def _trial_with_workspace(ref: str) -> AgentEvalTrial:
    return AgentEvalTrial(
        id="taskA:fabric",
        task_id="taskA",
        status=AgentEvalTrialStatus.COMPLETED,
        output=AgentOutput(output_text="done"),
        evidence=CandidateEvidence(descriptors={"workspace": EvidenceDescriptor(kind="filesystem", ref=ref)}),
        metadata={"agent_ok": True},
    )


def test_read_trials_hydrates_trial_and_keeps_valid_evidence_ref(tmp_path: Path) -> None:
    # A stored bundle whose workspace evidence ref still resolves as-is (re-scoring reads the deliverables).
    workspace = tmp_path / "evidence" / "fabric" / "run" / "000000-taskA" / "workspace"
    (workspace / "output").mkdir(parents=True)
    (workspace / "output" / "memo.txt").write_text("deliverable", encoding="utf-8")
    _write_trial(tmp_path, _trial_with_workspace(str(workspace)))

    (trial,) = read_trials(tmp_path)
    assert trial.task_id == "taskA" and trial.status == AgentEvalTrialStatus.COMPLETED
    ws = trial.evidence.require("workspace")
    assert ws.kind == "filesystem" and Path(ws.ref).is_dir()  # type: ignore[arg-type]


def test_read_trials_rebuilds_evidence_ref_for_a_moved_bundle(tmp_path: Path) -> None:
    # The stored ref points at the (now gone) launch dir, but the evidence exists under the given run_dir —
    # read_trials rebuilds the ref under run_dir from the evidence/ tail so a moved/copied bundle still works.
    workspace = tmp_path / "evidence" / "fabric" / "run" / "000000-taskA" / "workspace"
    workspace.mkdir(parents=True)
    stale = "/some/old/launch/dir/evidence/fabric/run/000000-taskA/workspace"
    _write_trial(tmp_path, _trial_with_workspace(stale))

    (trial,) = read_trials(tmp_path)
    ws = trial.evidence.require("workspace")
    assert Path(ws.ref) == workspace and Path(ws.ref).is_dir()  # type: ignore[arg-type]


def test_persist_run_writes_bundle_relative_refs_that_survive_a_move(tmp_path: Path) -> None:
    # persist_run stores evidence refs RELATIVE to the bundle, so the bundle is self-contained: copy it
    # anywhere and read_trials still resolves the deliverables — no launch-CWD dependency.
    bundle = tmp_path / "run"
    workspace = bundle / "evidence" / "fabric" / "r" / "000000-taskA" / "workspace"
    (workspace / "output").mkdir(parents=True)
    (workspace / "output" / "memo.txt").write_text("deliverable", encoding="utf-8")

    result = AgentEvalResult(
        run_id="r",
        tasks=[],
        trials=[_trial_with_workspace(str(workspace))],  # absolute ref under the bundle
        scores=[],
        summary=AgentEvalSummary.from_scores([], tasks=[]),
    )
    persist_run(result, bundle)

    stored = json.loads((bundle / "trials.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert stored["evidence"]["descriptors"]["workspace"]["ref"] == "evidence/fabric/r/000000-taskA/workspace"

    moved = tmp_path / "moved-bundle"
    shutil.copytree(bundle, moved)
    (trial,) = read_trials(moved)
    resolved = Path(trial.evidence.require("workspace").ref)  # type: ignore[arg-type]
    assert resolved.is_dir() and resolved == moved / "evidence" / "fabric" / "r" / "000000-taskA" / "workspace"


def test_persist_run_writes_per_task_attempts_to_summary(tmp_path: Path) -> None:
    summary = AgentEvalSummary(
        task_metric_attempts={
            "task-a": {
                "harbor_reward.reward": [
                    AgentEvalAttemptValue(trial_id="task-a__aaa", value=1.0),
                    AgentEvalAttemptValue(trial_id="task-a__bbb", value=0.0),
                ]
            },
            "task-b": {
                "harbor_reward.reward": [
                    AgentEvalAttemptValue(trial_id="task-b__ccc", value=1.0),
                    AgentEvalAttemptValue(trial_id="task-b__ddd", value=None),
                ]
            },
        }
    )
    result = AgentEvalResult(run_id="run", tasks=[], trials=[], scores=[], summary=summary)

    persist_run(result, tmp_path)

    payload = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert payload["task_metric_attempts"] == {
        "task-a": {
            "harbor_reward.reward": [
                {"trial_id": "task-a__aaa", "value": 1.0},
                {"trial_id": "task-a__bbb", "value": 0.0},
            ]
        },
        "task-b": {
            "harbor_reward.reward": [
                {"trial_id": "task-b__ccc", "value": 1.0},
                {"trial_id": "task-b__ddd", "value": None},
            ]
        },
    }
    assert AgentEvalSummary.model_validate(payload).task_metric_attempts == summary.task_metric_attempts


def test_summary_json_round_trips_attempt_order_through_sort_keys(tmp_path: Path) -> None:
    # persist_run writes with sort_keys=True. Attempts are a list precisely so that trial order
    # survives that: keying them by trial id would come back sorted lexicographically instead.
    summary = AgentEvalSummary(
        task_metric_attempts={
            "task-a": {
                "harbor_reward.reward": [
                    AgentEvalAttemptValue(trial_id="z-trial", value=1.0),
                    AgentEvalAttemptValue(trial_id="a-trial", value=0.0),
                ]
            }
        }
    )
    result = AgentEvalResult(run_id="run", tasks=[], trials=[], scores=[], summary=summary)

    persist_run(result, tmp_path)
    payload = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    reloaded = AgentEvalSummary.model_validate(payload)

    assert [a.trial_id for a in reloaded.task_metric_attempts["task-a"]["harbor_reward.reward"]] == [
        "z-trial",
        "a-trial",
    ]


def test_read_trials_rejects_evidence_ref_that_escapes_the_bundle(tmp_path: Path) -> None:
    # A copied/untrusted bundle whose ref uses `..` to escape the bundle must NOT be resolved to the
    # outside path: the rebuilt ref is accepted only when it stays inside run_dir.
    (tmp_path / "outside_secret").mkdir()  # a real dir outside the bundle
    bundle = tmp_path / "run"
    bundle.mkdir()
    escaping = "evidence/../../outside_secret"  # bundle/evidence/../../outside_secret -> tmp_path/outside_secret
    _write_trial(bundle, _trial_with_workspace(escaping))

    (trial,) = read_trials(bundle)
    # left as the stored ref — never rewritten to the escaped (but existing) outside path
    assert trial.evidence.require("workspace").ref == escaping


def test_persist_and_read_keep_external_evidence_refs_absolute(tmp_path: Path) -> None:
    # Evidence that lives OUTSIDE the bundle (e.g. a re-scored bundle referencing the ORIGINAL run's
    # deliverables) must keep its absolute ref through persist + read — not relativized, not dropped.
    external = tmp_path / "original-run" / "evidence" / "fabric" / "r" / "000000-taskA" / "workspace"
    (external / "output").mkdir(parents=True)
    (external / "output" / "memo.txt").write_text("deliverable", encoding="utf-8")
    external_ref = str(external.resolve())

    bundle = tmp_path / "rescored"  # a DIFFERENT bundle that references the external deliverables
    result = AgentEvalResult(
        run_id="r",
        tasks=[],
        trials=[_trial_with_workspace(external_ref)],
        scores=[],
        summary=AgentEvalSummary.from_scores([], tasks=[]),
    )
    persist_run(result, bundle)

    stored = json.loads((bundle / "trials.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert stored["evidence"]["descriptors"]["workspace"]["ref"] == external_ref  # absolute, unchanged

    (trial,) = read_trials(bundle)
    assert trial.evidence.require("workspace").ref == external_ref  # retained as-is


def test_persist_defaults_to_the_work_dir_so_evidence_lands_inside_the_bundle(tmp_path: Path) -> None:
    # Defaulting to work_dir is what keeps a bundle self-contained: the evidence the trials point at
    # is already underneath it, so persist can rewrite the refs bundle-relative.
    workspace = tmp_path / "evidence" / "000000-taskA" / "workspace"
    workspace.mkdir(parents=True)
    result = AgentEvalResult(
        run_id="r",
        tasks=[],
        trials=[_trial_with_workspace(str(workspace))],
        scores=[],
        summary=AgentEvalSummary.from_scores([], tasks=[]),
        work_dir=tmp_path,
    )

    location = result.persist(write_dashboard=False)

    assert location.output_dir == tmp_path
    stored = json.loads((tmp_path / "trials.jsonl").read_text(encoding="utf-8"))["evidence"]["descriptors"]
    assert stored["workspace"]["ref"] == "evidence/000000-taskA/workspace"  # relative => self-contained


def test_persist_without_a_work_dir_or_an_explicit_target_is_an_error() -> None:
    # An in-memory run has nowhere to go; failing loudly beats inventing a directory.
    result = AgentEvalResult(
        run_id="r", tasks=[], trials=[], scores=[], summary=AgentEvalSummary.from_scores([], tasks=[])
    )

    with pytest.raises(ValueError, match="no work_dir"):
        result.persist()


def test_persist_accepts_an_explicit_target_for_an_in_memory_run(tmp_path: Path) -> None:
    # The counterpart to the error above: an in-memory run has no default, but naming one works.
    result = AgentEvalResult(
        run_id="r", tasks=[], trials=[], scores=[], summary=AgentEvalSummary.from_scores([], tasks=[])
    )

    location = result.persist(tmp_path, write_dashboard=False)

    assert location.output_dir == tmp_path
    assert json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))["run_id"] == "r"
