# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guard the hello-harbor-agent example's *deliberately failing* baseline.

The example only teaches anything because the baseline agent has a capability
gap: it greets, but it cannot do arithmetic. The Analyzer diagnoses that gap, the
Proposer describes it, and the Coder closes it — which is the whole documented
one-round debug run.

A well-meaning edit that adds a ``handle_sum`` to the baseline silently destroys
that: both train tasks pass, the Analyzer gets no failing trial, and the debug
config has nothing to do. It happened once. These tests are fast (no Docker, no
containers) precisely so the gap is guarded on every run, and they read the real
dataset from disk so they stay honest when tasks change.

The reward rule mirrors ``tests/test.sh``: the agent's whole output must equal
``tests/expected.txt`` once CRLF line endings and trailing newlines are
normalized. Keeping the two in lockstep is itself asserted below.
"""

from __future__ import annotations

import functools
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "hello-harbor-agent"
_DATASET_DIR = _EXAMPLE_DIR / "dataset"

# The documented baseline, from README.md "The deliberate capability gap".
# reward 1.0 == the agent produced exactly the expected line.
_EXPECTED_BASELINE = {
    ("train", "greet-world"): 1.0,
    ("train", "sum-two"): 0.0,
    ("validation", "greet-universe"): 1.0,
    ("validation", "sum-three"): 0.0,
}


@functools.cache
def _load_hello_agent() -> Any:
    """Import the example's ``agent.py`` by path; it is not an installed package.

    Cached: the module cannot change mid-session, and without this every
    parametrized case re-execs it.
    """
    spec = importlib.util.spec_from_file_location("_hello_example_agent", _EXAMPLE_DIR / "agent.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.HelloAgent


def _normalize(text: str) -> str:
    """Mirror ``tests/test.sh``: strip CR at end-of-line only, then trailing newlines.

    Deliberately not ``text.replace("\\r", "")`` — that is the shell's
    ``tr -d '\\r'``, which deletes *every* carriage return and would let
    ``sum=4<CR>2`` collapse into a passing ``sum=42``.
    """
    return re.sub(r"\r$", "", text, flags=re.MULTILINE).rstrip("\n")


@functools.cache
def _reward_for(split: str, task_id: str) -> float:
    """Replay the verifier's comparison in-process for one task.

    Mirrors ``tests/test.sh`` exactly, including its whole-file rule: both sides
    are CRLF-normalized and stripped of trailing newlines, then compared in full.
    Comparing only the first line here would let this test pass output the real
    verifier rejects.
    """
    task_dir = _DATASET_DIR / split / task_id
    instruction = (task_dir / "instruction.md").read_text(encoding="utf-8").strip()
    expected = _normalize((task_dir / "tests" / "expected.txt").read_text(encoding="utf-8"))

    # main.py writes `solve(prompt) + "\n"` to output.txt.
    written = _load_hello_agent()().solve(instruction) + "\n"
    return 1.0 if _normalize(written) == expected else 0.0


@pytest.mark.parametrize(("split", "task_id", "expected_reward"), [(*k, v) for k, v in _EXPECTED_BASELINE.items()])
def test_baseline_scores_match_the_documented_capability_gap(
    split: str,
    task_id: str,
    expected_reward: float,
) -> None:
    assert _reward_for(split, task_id) == expected_reward


@pytest.mark.parametrize("split", ["train", "validation"])
def test_every_split_keeps_one_passing_and_one_failing_task(split: str) -> None:
    """Both splits must average 0.5 — and for the same structural reason.

    An aggregate of 1.0 means the gap was closed in the baseline; 0.0 means the
    greeting handler broke. Either way the example stops demonstrating what its
    README says it demonstrates.
    """
    rewards = {task_id: _reward_for(split, task_id) for (s, task_id) in _EXPECTED_BASELINE if s == split}

    # For a two-task split this also pins the 0.5 aggregate both evaluators report.
    assert sorted(rewards.values()) == [0.0, 1.0], f"{split} split lost its one-pass/one-fail shape: {rewards}"


def test_baseline_agent_exposes_no_arithmetic_handler() -> None:
    """The gap must be a real missing capability, not a regex that happens to miss.

    ``handle_sum`` is the exact method name the Proposer's ``add_concrete_method``
    improvement introduces in round 1, so its presence on the baseline means a
    previous run's output leaked back into the example.
    """
    agent = _load_hello_agent()()

    assert not hasattr(agent, "handle_sum"), (
        "the baseline agent must not implement handle_sum — that is the round-1 "
        "improvement the Coder is supposed to write (see README.md)"
    )


def test_unhandled_tasks_fall_through_to_the_fallback() -> None:
    """A failing task must fail by falling through, which is what the Analyzer reads."""
    module_agent = _load_hello_agent()
    instruction = (_DATASET_DIR / "train" / "sum-two" / "instruction.md").read_text(encoding="utf-8").strip()

    answer = module_agent().solve(instruction)

    assert answer == "I do not know how to answer that."


@pytest.mark.parametrize(
    ("written", "expected_reward"),
    [
        ("sum=42\n", 1.0),
        ("sum=42\r\n", 1.0),  # CRLF line ending is legitimate
        ("sum=4\r2\n", 0.0),  # embedded CR must not collapse into a match
        ("sum=42\nextra\n", 0.0),  # trailing content must not be ignored
    ],
)
def test_normalization_matches_the_shell_verifier(written: str, expected_reward: float) -> None:
    """Keep `_normalize` in lockstep with `sed 's/\\r$//'` in tests/test.sh.

    Both rules are reward-hacking guards; if this helper ever drifts back to
    stripping every CR, the in-process tests would pass output the container
    verifier rejects.
    """
    assert (1.0 if _normalize(written) == _normalize("sum=42\n") else 0.0) == expected_reward
