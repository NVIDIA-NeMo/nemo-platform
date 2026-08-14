# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""``run.json``'s ``winner_agent`` is the winner's label, and it must stay that way.

Every artifact a run writes is filed under the label -- ``agents/agent-3/``,
``results/agent-3-validation/`` -- so a consumer that reads ``winner_agent`` is
reading it to build one of those paths. Writing the candidate id there instead
produces a value that resolves to nothing: no error, just an empty lookup, which
downstream reads as "the winner has no results" rather than as a broken reference.

That is not hypothetical. The field held the id for one revision of this branch,
and the failure it produced was a smoke-agent gate reporting a *regression* on a
control task the baseline answers perfectly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from doubles import make_candidate
from nemo_experimentalist_plugin.experimentalist.components.models import Candidate
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import load_winner


def _write_run(root: Path, *, winner_agent: str | None, candidates: list[Candidate]) -> Path:
    """Lay out a finished run the way the runner does: records by id, run.json by label."""
    eo = root / "eval-and-optimize"
    (eo / "candidates").mkdir(parents=True)
    for candidate in candidates:
        payload = json.loads(candidate.model_dump_json())
        payload["id"] = candidate.id
        (eo / "candidates" / f"{candidate.id}.json").write_text(json.dumps(payload), encoding="utf-8")
    (eo / "run.json").write_text(json.dumps({"status": "completed", "winner_agent": winner_agent}), encoding="utf-8")
    return eo


def _candidate(label: str, generation: int) -> Candidate:
    """`make_candidate` gives id and label different strings, which is the whole point here."""
    return make_candidate(label=label, generation=generation)


def test_load_winner_resolves_the_label_to_its_record(tmp_path: Path) -> None:
    """The records are filed by id, so the label has to be resolved rather than joined."""
    winner = _candidate("agent-1", 1)
    eo = _write_run(tmp_path, winner_agent="agent-1", candidates=[_candidate("agent-0", 0), winner])

    assert load_winner(eo).label == "agent-1"


def test_load_winner_rejects_a_label_no_candidate_carries(tmp_path: Path) -> None:
    """A dangling reference must say so rather than resolving to nothing."""
    eo = _write_run(tmp_path, winner_agent="agent-9", candidates=[_candidate("agent-0", 0)])

    with pytest.raises(FileNotFoundError, match="agent-9"):
        load_winner(eo)


def test_load_winner_rejects_a_candidate_id(tmp_path: Path) -> None:
    """The regression this file exists for: an id in the field resolves to nothing.

    Writing the id is what a caller does when it reaches for the obvious attribute,
    so the failure must be loud rather than an empty result set.
    """
    winner = _candidate("agent-1", 1)
    eo = _write_run(tmp_path, winner_agent=winner.id, candidates=[winner])

    with pytest.raises(FileNotFoundError):
        load_winner(eo)


def test_a_run_with_no_winner_is_an_error_not_a_none(tmp_path: Path) -> None:
    eo = _write_run(tmp_path, winner_agent=None, candidates=[_candidate("agent-0", 0)])

    with pytest.raises(ValueError, match="without a selected winner"):
        load_winner(eo)


def test_the_label_is_usable_as_a_path_component(tmp_path: Path) -> None:
    """What the field is *for*: the smoke-agent gate and the loop e2e suites read it
    and index `agents/` and `results/` with the result."""
    winner = _candidate("agent-1", 1)
    eo = _write_run(tmp_path, winner_agent="agent-1", candidates=[winner])
    for name in ("agents/agent-1", "results/agent-1-validation"):
        (eo / name).mkdir(parents=True)

    label = json.loads((eo / "run.json").read_text())["winner_agent"]

    assert (eo / "agents" / label).is_dir()
    assert (eo / "results" / f"{label}-validation").is_dir()


def test_every_run_critical_write_is_atomic() -> None:
    """`run.json` and `candidates/<id>.json` decide whether a run can resume.

    A plain `write_text` truncates before writing, so a process killed mid-write leaves a
    half-written file: `run.json` stops parsing and `list_candidates` raises, which loses
    the whole run rather than one record. `_atomic_write` writes a sibling and renames.

    Checked over the source rather than by killing a process, because the failure needs a
    crash at one specific instant to reproduce.
    """
    import re

    backend = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "nemo_experimentalist_plugin"
        / "experimentalist"
        / "experimentalist_backend.py"
    ).read_text(encoding="utf-8")

    plain = [
        line.strip()
        for line in backend.splitlines()
        if re.search(r"\.write_text\(", line)
        and "temporary.write_text" not in line  # _atomic_write's own write
        and "report_path" not in line  # OPTIMIZATION.md: regenerated, never read back
    ]

    assert not plain, f"run-critical writes that truncate in place: {plain}"
