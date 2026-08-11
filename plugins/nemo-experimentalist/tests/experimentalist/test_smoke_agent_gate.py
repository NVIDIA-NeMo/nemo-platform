# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Assert an Experimentalist run actually repaired the weakness it was given.

Reward alone is not enough. A candidate can raise the number without fixing the
code, and a run can look healthy while measuring nothing, so each assertion below
targets a distinct way the result could be hollow.

Every path and payload shape here is confirmed against a real run
(2026-08-05, G1 repair scenario, winner agent-1 at validation 1.000 from a
baseline of 0.333). Point SMOKE_EXPERIMENT_DIR at an experiment directory to run
these; they skip otherwise.

    SMOKE_EXPERIMENT_DIR=/tmp/smoke-g1-repair uv run pytest \\
      plugins/nemo-experimentalist/tests/experimentalist/test_smoke_agent_gate.py -v
"""

from __future__ import annotations

import functools
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_EXPERIMENT_DIR = Path(os.environ.get("SMOKE_EXPERIMENT_DIR", "/nonexistent"))
_EO = "eval-and-optimize"

# The repo's own copy of the fixture, used to replay held-out tasks against a
# candidate's code. The records file is the same one the run used: the task image
# is tagged by a content hash of it, so a drift would have failed an asset test.
_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "smoke-agent"
_RECORDS = _EXAMPLE_DIR / "dataset" / "_shared" / "records.json"
_G1_VALIDATION = _EXAMPLE_DIR / "dataset" / "groups" / "g1-aggregation" / "validation"

# Which question this run answers. The two classes have *opposite* pass
# conditions, so a run is only meaningful once you say which one you started.
#   repair          -- train covers the general case; the winner must beat baseline
#   generalization  -- train covers only a narrow case; the baseline must be kept
_SCENARIO = os.environ.get("SMOKE_SCENARIO", "repair")

# Assertion 2. A threshold, not equality: the agent under test is deterministic
# but the Experimentalist's own components are not. The observed delta was 0.667.
REWARD_DELTA_THRESHOLD = 0.3

# Assertion 4's matching rule. Two independent hits, so one incidental word does
# not satisfy it. The real analysis matched "total", "sum" and "aggregat".
ROOT_CAUSE_TERMS = ("total", "sum", "aggregat", "arithmetic")
MIN_ROOT_CAUSE_HITS = 2

# G1's validation split: two weakness tasks plus one control. Task names are the
# full `[task] name` from task.toml, not the directory name.
VALIDATION_WEAKNESS_TASKS = {"smoke/g1-total-hours-ops", "smoke/g1-total-hours-analysts"}
VALIDATION_CONTROL_TASKS = {"smoke/g1-lookup-grace"}

# G4's split, used by the generalization assertions below.
G4_VALIDATION_CONTROL_TASKS = {"smoke/g4-lookup-grace"}

pytestmark = pytest.mark.skipif(
    not (_EXPERIMENT_DIR / _EO / "run.json").is_file(),
    reason="no completed experiment at SMOKE_EXPERIMENT_DIR",
)

repair_only = pytest.mark.skipif(_SCENARIO != "repair", reason="set SMOKE_SCENARIO=repair")


def _winner_label() -> str:
    """Read the winning candidate's label from the run record."""
    run = json.loads((_EXPERIMENT_DIR / _EO / "run.json").read_text(encoding="utf-8"))
    winner = run.get("winner_agent")
    assert winner, f"run.json has no winner_agent: {sorted(run)}"
    return str(winner)


def _agent_source(label: str) -> str:
    return (_EXPERIMENT_DIR / _EO / "agents" / label / "agent.py").read_text(encoding="utf-8")


def _aggregate(label: str, dataset: str = "validation") -> dict[str, float]:
    """Aggregate metrics for one evaluation.

    There is no top-level ``aggregate_metrics``. Harbor nests it under
    ``stats.evals.<eval-key>.metrics[0]``, and the eval key is Harbor's own, so
    read the single entry rather than constructing the key.
    """
    result = _EXPERIMENT_DIR / _EO / "results" / f"{label}-{dataset}" / "result.json"
    evals = list(json.loads(result.read_text(encoding="utf-8"))["stats"]["evals"].values())
    assert len(evals) == 1, f"expected one eval in {result}, found {len(evals)}"
    return evals[0]["metrics"][0]


def _per_task_rewards(label: str, dataset: str = "validation") -> dict[str, float]:
    """Per-task reward, keyed by the full task name, from ``verifier_result.rewards``."""
    rewards: dict[str, float] = {}
    for trial in sorted((_EXPERIMENT_DIR / _EO / "results" / f"{label}-{dataset}").glob("*/result.json")):
        payload = json.loads(trial.read_text(encoding="utf-8"))
        rewards[payload["task_name"]] = float(payload["verifier_result"]["rewards"]["reward"])
    return rewards


@functools.cache
def _agent_class(label: str) -> Any:
    """Import a candidate's agent.py by path; it is not an installed package.

    `agent_source` points at the example's `agent/` directory and its *contents*
    are copied to the candidate root, so agent.py sits directly under
    `agents/<label>/`.
    """
    os.environ["RECORDS_PATH"] = str(_RECORDS)
    os.environ.setdefault("TRACE_DIR", tempfile.mkdtemp(prefix="smoke-gate-traces-"))
    path = _EXPERIMENT_DIR / _EO / "agents" / label / "agent.py"
    spec = importlib.util.spec_from_file_location(f"_smoke_gate_{label}", path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.ReportAgent


def _normalize(text: str) -> str:
    """Mirror tests/test.sh: strip CR at end-of-line only, then trailing newlines."""
    return re.sub(r"\r$", "", text, flags=re.MULTILINE).rstrip("\n")


def _replays_correctly(label: str, task_dir: Path) -> bool:
    """Run one held-out task against *label*'s own code and compare to its fixture."""
    instruction = (task_dir / "instruction.md").read_text(encoding="utf-8").strip()
    expected = (task_dir / "tests" / "expected.txt").read_text(encoding="utf-8")
    written = _agent_class(label)().solve(instruction) + "\n"
    return _normalize(written) == _normalize(expected)


@repair_only
def test_1_weakness_repaired() -> None:
    """Check that the winner answers the held-out aggregation tasks."""
    winner = _winner_label()
    if winner == "agent-0":
        pytest.fail("winner is the baseline; nothing was repaired")

    assert _agent_source(winner) != _agent_source("agent-0"), "winner source is identical to the baseline"

    tasks = [
        task
        for task in sorted(_G1_VALIDATION.iterdir())
        if (task / "task.toml").is_file() and task.name.startswith("total-hours-")
    ]
    assert tasks, f"no total-hours tasks under {_G1_VALIDATION}; the fixture moved"
    failed = [task.name for task in tasks if not _replays_correctly(winner, task)]
    assert not failed, (
        f"{winner} does not answer {failed} correctly when replayed against its own code; "
        "the reward rose for some other reason"
    )


@repair_only
def test_2_reward_improved() -> None:
    """Check that validation reward improves beyond the threshold."""
    baseline = _aggregate("agent-0")["reward"]
    winner = _aggregate(_winner_label())["reward"]
    assert winner - baseline >= REWARD_DELTA_THRESHOLD, (
        f"validation reward {baseline} -> {winner} is below the {REWARD_DELTA_THRESHOLD} threshold"
    )


@repair_only
def test_3_no_regression() -> None:
    """Check that the winner still passes baseline control tasks."""
    rewards = _per_task_rewards(_winner_label())
    broken = {task for task in VALIDATION_CONTROL_TASKS if rewards.get(task, 0.0) < 1.0}
    assert not broken, f"winner regressed control tasks: {sorted(broken)}"


@repair_only
def test_4_analysis_named_the_weakness() -> None:
    """Check that the Analyzer identifies the aggregation problem."""
    analyses = sorted((_EXPERIMENT_DIR / _EO / "analysis").glob("round-*.md"))
    assert analyses, f"no analyzer output under {_EXPERIMENT_DIR / _EO / 'analysis'}"
    text = " ".join(a.read_text(encoding="utf-8") for a in analyses).lower()
    hits = [term for term in ROOT_CAUSE_TERMS if term in text]
    assert len(hits) >= MIN_ROOT_CAUSE_HITS, f"analysis did not name the aggregation gap; matched only {hits}"


@repair_only
def test_5_generalizes_to_held_out_instances() -> None:
    """Check that the winner passes both held-out weakness tasks."""
    rewards = _per_task_rewards(_winner_label())
    failed = {task for task in VALIDATION_WEAKNESS_TASKS if rewards.get(task, 0.0) < 1.0}
    assert not failed, f"winner did not generalize; still failing: {sorted(failed)}"


# --------------------------------------------------------------------------
# Generalization scenario. Opposite pass condition: a fix that does not
# transfer must be *rejected*, so success is the baseline being retained.
# Verified against a real run (2026-08-05, G4): the candidate scored 1.000 on
# train and 0.333 on validation, and agent-0 won.
# --------------------------------------------------------------------------

generalization_only = pytest.mark.skipif(
    _SCENARIO != "generalization",
    reason="set SMOKE_SCENARIO=generalization",
)


def _train_aggregate(label: str) -> dict[str, float]:
    """Train aggregate for a candidate.

    Candidate train runs carry a subset size and hash in the directory name and
    there may be several, so glob rather than construct the path, and take the
    best -- that is the score the loop judged the candidate on.
    """
    dirs = sorted((_EXPERIMENT_DIR / _EO / "results").glob(f"{label}-train*"))
    assert dirs, f"no train results for {label}"
    best: dict[str, float] = {"reward": -1.0}
    for d in dirs:
        evals = list(json.loads((d / "result.json").read_text(encoding="utf-8"))["stats"]["evals"].values())
        metrics = evals[0]["metrics"][0]
        if metrics["reward"] > best["reward"]:
            best = metrics
    return best


@generalization_only
def test_g_1_baseline_was_retained() -> None:
    """Check that the generalization scenario retains the baseline."""
    winner = _winner_label()
    assert winner == "agent-0", (
        f"winner is {winner}, but a generalization scenario expects the baseline to be kept. "
        "Either the fix genuinely transferred -- in which case this group's train split covers "
        "the general case and it is a repair scenario -- or validation is not held out."
    )


@generalization_only
def test_g_2_a_candidate_actually_fixed_train() -> None:
    """Check that a candidate improved on the training tasks."""
    candidates = sorted(d.name for d in (_EXPERIMENT_DIR / _EO / "agents").iterdir() if d.name != "agent-0")
    assert candidates, "no candidates were produced; the round did nothing"
    baseline_train = _train_aggregate("agent-0")["reward"]
    best = max(_train_aggregate(c)["reward"] for c in candidates)
    assert best > baseline_train, (
        f"no candidate improved on train ({baseline_train} -> {best}); "
        "the baseline was kept because nothing worked, not because validation rejected a fix"
    )


@generalization_only
def test_g_2b_the_train_winner_failed_validation() -> None:
    """Check that held-out data rejects the candidate that won on training."""
    candidates = sorted(d.name for d in (_EXPERIMENT_DIR / _EO / "agents").iterdir() if d.name != "agent-0")
    best = max(candidates, key=lambda c: _train_aggregate(c)["reward"])
    baseline_validation = _aggregate("agent-0")["reward"]
    best_validation = _aggregate(best)["reward"]
    assert best_validation <= baseline_validation, (
        f"{best} improved on train and also scored {best_validation} on validation, beating the "
        f"baseline's {baseline_validation} -- so validation did not reject it, and the baseline "
        "was retained for some other reason. Either the split is not held out or selection is wrong."
    )


@generalization_only
def test_g_3_no_regression() -> None:
    """Check that the retained baseline still passes its controls."""
    rewards = _per_task_rewards("agent-0")
    broken = {task for task in G4_VALIDATION_CONTROL_TASKS if rewards.get(task, 0.0) < 1.0}
    assert not broken, f"baseline controls are failing: {sorted(broken)}"
