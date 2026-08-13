# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guard the smoke agent's deliberately weak baseline and its record set.

The fixture only measures anything because the agent ships with known
weaknesses. A well-meaning edit that closes one silently destroys what an
Experimentalist run is asserted against, so the expected baseline is pinned
here. These tests need no Docker and no network.

See plugins/nemo-experimentalist/docs/smoke-agent-weaknesses.md before changing
either the agent or this file.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "smoke-agent"
_RECORDS = _EXAMPLE_DIR / "dataset" / "_shared" / "records.json"


@functools.cache
def _renderer() -> Any:
    """Import the task renderer by path; scripts is not a package."""
    path = _EXAMPLE_DIR / "scripts" / "render_tasks.py"
    spec = importlib.util.spec_from_file_location("_smoke_render_tasks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


@pytest.fixture(scope="module")
def rendered_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Render the compact task manifest once for these deterministic checks."""
    dataset = tmp_path_factory.mktemp("smoke-agent-dataset") / "dataset"
    shutil.copytree(_EXAMPLE_DIR / "dataset", dataset)
    _renderer().render(dataset)
    return dataset


def _records() -> list[dict]:
    return json.loads(_RECORDS.read_text(encoding="utf-8"))


def test_department_totals_are_pinned() -> None:
    """Check that department totals match the task expectations."""
    totals: dict[str, int] = {}
    for record in _records():
        totals[record["dept"]] = totals.get(record["dept"], 0) + record["hours"]
    assert totals == {"research": 29, "ops": 13}
    assert sum(totals.values()) == 42


def test_role_scoped_hours_are_pinned() -> None:
    """Check that role totals match the task expectations."""
    by_role: dict[str, int] = {}
    for record in _records():
        by_role[record["role"]] = by_role.get(record["role"], 0) + record["hours"]
    assert by_role["engineer"] == 20  # train
    assert by_role["analyst"] == 9  # validation


def test_g2_names_carry_no_other_weakness() -> None:
    """Check that G2 names do not also trigger another group’s behavior.

    The predicate mirrors the character class the agent's lookup pattern accepts.
    `str.isalpha()` is deliberately not used: it is Unicode-aware, so "Zoë" passes
    it while the agent's ASCII-only class rejects the name.
    """
    tricky = [r for r in _records() if not re.fullmatch(r"[A-Za-z ]+", r["name"])]
    assert {r["name"] for r in tricky} == {"O'Brien", "Zoë Washington", "Ann-Marie Cruz"}
    for record in tricky:
        assert record["role"] != "", (
            f"{record['name']} now carries a second group's weakness — see "
            "docs/smoke-agent-weaknesses.md before changing this record"
        )
        assert isinstance(record["hours"], int), f"{record['name']} would break another group"


def test_g5_empty_field_does_not_touch_g1() -> None:
    """Check that G5's empty value does not affect G1 tasks."""
    empty = [r for r in _records() if r["role"] == ""]
    assert [r["name"] for r in empty] == ["Karl Jung"]
    assert all(isinstance(r["hours"], int) for r in _records()), (
        "an empty `hours` would force a G1 fix to absorb G5's robustness"
    )


_EXPECTED_BASELINE: dict[tuple[str, str, str], float] = {
    # Train shows two *kinds* of filter -- by department and by role -- so a
    # general filter mechanism is the obvious fix. Validation holds new instances
    # of those same two kinds, which a general fix reaches and a hardcoded one
    # does not. This is what makes G1 a repair scenario rather than a
    # generalization one; see docs/smoke-agent-weaknesses.md.
    ("g1-aggregation", "train", "total-hours-research"): 0.0,
    ("g1-aggregation", "train", "total-hours-engineers"): 0.0,
    ("g1-aggregation", "train", "lookup-ada"): 1.0,
    ("g1-aggregation", "validation", "total-hours-ops"): 0.0,
    ("g1-aggregation", "validation", "total-hours-analysts"): 0.0,
    ("g1-aggregation", "validation", "lookup-grace"): 1.0,
    ("g2-name-patterns", "train", "lookup-obrien"): 0.0,
    ("g2-name-patterns", "train", "lookup-zoe"): 0.0,
    ("g2-name-patterns", "train", "lookup-ada"): 1.0,
    ("g2-name-patterns", "validation", "lookup-ann-marie"): 0.0,
    ("g2-name-patterns", "validation", "lookup-role-obrien"): 0.0,
    ("g2-name-patterns", "validation", "lookup-grace"): 1.0,
    ("g3-long-inputs", "train", "preamble-dept"): 0.0,
    ("g3-long-inputs", "train", "preamble-role"): 0.0,
    ("g3-long-inputs", "train", "plain-dept"): 1.0,
    ("g3-long-inputs", "validation", "preamble-long-dept"): 0.0,
    ("g3-long-inputs", "validation", "preamble-hours"): 0.0,
    ("g3-long-inputs", "validation", "trailing-prose"): 1.0,
    ("g4-dispatch-order", "train", "count-research"): 0.0,
    ("g4-dispatch-order", "train", "count-ops"): 0.0,
    ("g4-dispatch-order", "train", "lookup-ada"): 1.0,
    ("g4-dispatch-order", "validation", "count-operators-ops"): 0.0,
    ("g4-dispatch-order", "validation", "count-engineers-research"): 0.0,
    ("g4-dispatch-order", "validation", "lookup-grace"): 1.0,
    ("g5-edge-cases", "train", "missing-person"): 0.0,
    ("g5-edge-cases", "train", "empty-role"): 0.0,
    ("g5-edge-cases", "train", "lookup-ada"): 1.0,
    ("g5-edge-cases", "validation", "missing-person-role"): 0.0,
    ("g5-edge-cases", "validation", "missing-person-hours"): 0.0,
    ("g5-edge-cases", "validation", "lookup-grace"): 1.0,
}

GROUPS = (
    "g1-aggregation",
    "g2-name-patterns",
    "g3-long-inputs",
    "g4-dispatch-order",
    "g5-edge-cases",
)


@functools.cache
def _agent_class() -> Any:
    """Import agent.py by path; it is not an installed package."""
    os.environ["RECORDS_PATH"] = str(_RECORDS)
    os.environ.setdefault("TRACE_DIR", tempfile.mkdtemp(prefix="smoke-baseline-traces-"))
    spec = importlib.util.spec_from_file_location("_smoke_baseline_agent", _EXAMPLE_DIR / "agent" / "agent.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.ReportAgent


def _normalize(text: str) -> str:
    """Mirror tests/test.sh: strip CR at end-of-line only, then trailing newlines.

    Deliberately not text.replace("\\r", "") -- that is `tr -d '\\r'`, which deletes
    every carriage return and would let total=2<CR>9 collapse into a passing
    total=29.
    """
    return re.sub(r"\r$", "", text, flags=re.MULTILINE).rstrip("\n")


def _reward_for(dataset: Path, group: str, split: str, task_id: str) -> float:
    """Replay the container verifier in-process for one task."""
    task = dataset / "groups" / group / split / task_id
    instruction = (task / "instruction.md").read_text(encoding="utf-8").strip()
    expected = (task / "tests" / "expected.txt").read_text(encoding="utf-8")
    written = _agent_class()().solve(instruction) + "\n"
    return 1.0 if _normalize(written) == _normalize(expected) else 0.0


@pytest.mark.parametrize(("key", "expected"), list(_EXPECTED_BASELINE.items()))
def test_baseline_rewards_are_pinned(rendered_dataset: Path, key: tuple[str, str, str], expected: float) -> None:
    """Check that every task has its expected baseline reward."""
    assert _reward_for(rendered_dataset, *key) == expected, (
        f"{key} no longer scores {expected} at baseline. The agent ships with deliberate "
        "weaknesses; see plugins/nemo-experimentalist/docs/smoke-agent-weaknesses.md before "
        "changing agent.py."
    )


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("split", ["train", "validation"])
def test_each_split_keeps_two_failures_and_one_control(rendered_dataset: Path, group: str, split: str) -> None:
    """Check that every split has two failures and one control."""
    expected_ids = {task_id for (g, s, task_id) in _EXPECTED_BASELINE if g == group and s == split}
    actual_ids = {
        path.name for path in (rendered_dataset / "groups" / group / split).iterdir() if (path / "task.toml").is_file()
    }
    assert actual_ids == expected_ids, (
        f"{group}/{split} drifted: missing={sorted(expected_ids - actual_ids)} "
        f"unexpected={sorted(actual_ids - expected_ids)}"
    )
    rewards = sorted(_reward_for(rendered_dataset, group, split, task_id) for task_id in expected_ids)
    assert rewards == [0.0, 0.0, 1.0], f"{group}/{split} lost its two-failure/one-control shape: {rewards}"


@pytest.mark.parametrize(
    ("answer", "expected_shape"),
    [
        ("dept=research", 1.0),
        ("count=3", 1.0),
        ("names=Ada Lovelace", 1.0),
        ("role=", 1.0),
        ("I do not know how to answer that.", 0.0),
    ],
)
def test_shape_metric_discriminates(answer: str, expected_shape: float) -> None:
    """Check that the shape metric distinguishes an answer from a fallback.

    Mirrors the grep in tests/test.sh. A "did the agent write a file" metric was
    rejected here: this agent always writes one, so it would be constant.
    """
    actual = 1.0 if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", answer.splitlines()[0]) else 0.0
    assert actual == expected_shape
