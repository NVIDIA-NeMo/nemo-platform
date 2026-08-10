# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Refuse to score an Insight suite whose tasks were never filled in.

Insight-driven mode has Eval Author write tasks from production traces by filling
the placeholders in `dataset/task-template/`. Nothing upstream requires it to
succeed: `fill_task_template` is instructed to leave unfillable placeholders
as-is, and `InsightSuite.validate` only checks that `instruction.md` is *non-empty*
-- which a file still containing `<QUESTION>` is.

An unfilled task asks a question no agent can parse and expects an answer nothing
produces, so it scores 0 whether or not the weakness was repaired. A run made of
those reads as "the Experimentalist failed to fix it" while measuring nothing at
all -- a confident wrong answer, which is the one output a fixture must never give.

These assertions turn that into a named failure. They do not make Mode 1 work; they
make it honest about which component fell over.

Point SMOKE_EXPERIMENT_DIR at an experiment directory to run them; they skip
otherwise.

    SMOKE_EXPERIMENT_DIR=/tmp/smoke-insight-g1 uv run pytest \\
        plugins/nemo-experimentalist/tests/experimentalist/test_smoke_agent_insight_suite.py -v
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

_EXPERIMENT_DIR = Path(os.environ.get("SMOKE_EXPERIMENT_DIR", "/nonexistent"))
_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "examples" / "smoke-agent" / "dataset" / "task-template"

# `<QUESTION>`, `<FIELD>`, `<EXPECTED>`. Read from the template rather than listed
# here, so adding a placeholder extends this guard instead of silently escaping it.
_PLACEHOLDER = re.compile(r"<[A-Z][A-Z0-9_]*>")

# Files a placeholder can hide in. tests/test.sh is excluded on purpose: it is synced
# from dataset/_shared and carries no placeholders, and its `<key>=<value>` prose
# would false-positive.
_FILLABLE = ("instruction.md", "task.toml", "tests/expected.txt")


def _require_experiment_dir() -> Path:
    if not _EXPERIMENT_DIR.is_dir():
        pytest.skip(f"set SMOKE_EXPERIMENT_DIR to an experiment directory (got {_EXPERIMENT_DIR})")
    return _EXPERIMENT_DIR


def _template_placeholders() -> set[str]:
    """Every placeholder token the committed template declares."""
    found: set[str] = set()
    for name in _FILLABLE:
        path = _TEMPLATE_DIR / name
        if path.is_file():
            found.update(_PLACEHOLDER.findall(path.read_text(encoding="utf-8")))
    return found


def _suite_dirs(experiment_dir: Path) -> list[Path]:
    """Materialized Insight suites, located by their manifest rather than by guessing.

    The path is `eval-and-optimize/eval_author/<insight-slug>/insight-suite/`, but the
    slug is derived from the insight id, so searching for the manifest is both simpler
    and robust to that scheme changing.
    """
    root = experiment_dir / "eval-and-optimize" / "eval_author"
    if not root.is_dir():
        return []
    return sorted(manifest.parent for manifest in root.rglob("insight-suite/manifest.json"))


def _materialized_tasks(suite_dir: Path) -> list[Path]:
    """Task directories the manifest claims, so a stray directory is not mistaken for one."""
    manifest = json.loads((suite_dir / "manifest.json").read_text(encoding="utf-8"))
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [suite_dir / entry["path"] for entry in tasks if isinstance(entry, dict) and entry.get("path")]


def test_the_template_still_declares_placeholders() -> None:
    """Guards the guard: with no placeholders to find, everything below passes vacuously."""
    declared = _template_placeholders()
    assert declared, (
        f"{_TEMPLATE_DIR} declares no <PLACEHOLDER> tokens, so the checks in this module "
        "cannot fail. Either the template changed shape or this pattern is wrong."
    )


def test_a_suite_was_materialized() -> None:
    """Mode 1 with trace_refs must produce a suite; an empty one is not a passing run."""
    experiment_dir = _require_experiment_dir()
    suites = _suite_dirs(experiment_dir)
    assert suites, (
        f"no Insight suite under {experiment_dir}/eval-and-optimize/eval_author/. Either this "
        "was a Mode 2 run, or Eval Author produced nothing -- check that the Insight's "
        "trace_refs resolve in the target workspace."
    )
    for suite in suites:
        assert _materialized_tasks(suite), f"{suite}/manifest.json lists no tasks"


def test_no_materialized_task_still_contains_a_placeholder() -> None:
    """The failure this module exists for."""
    experiment_dir = _require_experiment_dir()
    declared = _template_placeholders()
    unfilled: list[str] = []

    for suite in _suite_dirs(experiment_dir):
        for task_dir in _materialized_tasks(suite):
            for name in _FILLABLE:
                path = task_dir / name
                if not path.is_file():
                    continue
                remaining = sorted(set(_PLACEHOLDER.findall(path.read_text(encoding="utf-8"))) & declared)
                if remaining:
                    unfilled.append(f"{task_dir.name}/{name}: {', '.join(remaining)}")

    assert not unfilled, (
        "Eval Author did not fill the task template:\n  "
        + "\n  ".join(unfilled)
        + "\n\nEvery task in this suite scores 0 regardless of the agent, so this run cannot "
        "measure whether the weakness was fixed. Read the result as a broken test, not as a "
        "failed repair."
    )


def test_expected_answers_are_not_empty() -> None:
    """A blank expectation compares equal to a blank answer, which would score 1.0.

    Distinct from the placeholder check: a template can be filled with nothing at all,
    and the verifier's fail-closed guard only covers an *unreadable* fixture, not an
    empty one.
    """
    experiment_dir = _require_experiment_dir()
    empty = [
        f"{task_dir.name}/tests/expected.txt"
        for suite in _suite_dirs(experiment_dir)
        for task_dir in _materialized_tasks(suite)
        if (task_dir / "tests" / "expected.txt").is_file()
        and not (task_dir / "tests" / "expected.txt").read_text(encoding="utf-8").strip()
    ]
    assert not empty, "materialized tasks have an empty expected answer: " + ", ".join(empty)


def test_every_suite_task_was_actually_scored() -> None:
    """A task that never ran is worse than one that scored 0: it leaves no trace at all.

    In the first Mode 1 run the generated tasks referenced a stale image tag, so their
    containers never started -- `pull access denied for smoke-agent-env`. No
    `reward.json` was written, the tasks were dropped from the aggregate, and the run
    reported a perfectly ordinary baseline over the three *real* tasks. The Insight
    suite contributed nothing and nothing said so.

    A missing metric and a legitimate zero are treated very differently by the loop;
    this is the check that tells them apart.
    """
    experiment_dir = _require_experiment_dir()
    results = experiment_dir / "eval-and-optimize" / "results"
    if not results.is_dir():
        pytest.skip("no results/ directory; the run did not reach evaluation")

    expected_slugs = {task.name for suite in _suite_dirs(experiment_dir) for task in _materialized_tasks(suite)}
    if not expected_slugs:
        pytest.skip("no materialized suite tasks to check")

    # Harbor names a trial `<task-name-truncated>__<suffix>`, and the truncation length
    # is its business, not ours. Strip the suffix and ask whether what remains prefixes
    # a slug, rather than guessing how much survived -- an earlier version assumed 40
    # characters, matched nothing against the real 32, and passed while the tasks it
    # was meant to catch had never run.
    trials_by_slug: dict[str, list[Path]] = {slug: [] for slug in expected_slugs}
    for trial in results.rglob("*"):
        if not trial.is_dir():
            continue
        base = re.sub(r"__[A-Za-z0-9]+$", "", trial.name)
        if len(base) < 12:
            continue
        for slug in expected_slugs:
            if slug.startswith(base):
                trials_by_slug[slug].append(trial)

    unscored = sorted(
        slug
        for slug, trials in trials_by_slug.items()
        if trials and not any((trial / "verifier" / "reward.json").is_file() for trial in trials)
    )

    assert not unscored, (
        "materialized tasks produced no reward.json, so they never ran:\n  "
        + "\n  ".join(unscored)
        + "\n\nCheck the trial log for a container failure -- a stale [environment].docker_image "
        "is the usual cause. These tasks were silently dropped from the aggregate, so the run's "
        "scores describe only the tasks that did run."
    )


_GRAMMAR = (
    re.compile(r"what is the \w+ of ", re.IGNORECASE),
    re.compile(r"how many .* in the \w+ department", re.IGNORECASE),
    re.compile(r"what is the total \w+ in the \w+ (?:department|role)", re.IGNORECASE),
)


def test_the_grammar_matches_the_committed_tasks() -> None:
    """Keep the patterns tied to the tasks, not to prose about them.

    This runs without an experiment directory, because it is the check that would have
    caught the mistake it exists for: the first version of the list came from the
    template README, which still described the pre-rewording `total ... for the`
    phrasing. It then flagged correctly-generated questions as off-grammar -- a guard
    accusing the component it was written to exonerate.
    """
    groups = _TEMPLATE_DIR.parent / "groups"
    if not groups.is_dir():
        pytest.skip("no committed groups to check against")
    unmatched = [
        f"{path.parent.parent.parent.name}/{path.parent.name}: {path.read_text(encoding='utf-8').splitlines()[0]}"
        for path in sorted(groups.rglob("instruction.md"))
        if not any(pattern.search(path.read_text(encoding="utf-8")) for pattern in _GRAMMAR)
    ]
    assert not unmatched, (
        "committed tasks fall outside the grammar this module enforces, so it would "
        "reject correctly-generated questions:\n  " + "\n  ".join(unmatched)
    )


def test_generated_questions_stay_inside_the_agent_grammar() -> None:
    """A question outside the three parsed forms fails for the wrong reason.

    It looks exactly like the weakness under test -- the agent returns its fallback --
    but the cause is phrasing the agent was never able to parse, so the run measures the
    template rather than the Experimentalist. Warned about in the template README; this
    is that warning enforced.
    """
    experiment_dir = _require_experiment_dir()
    off_grammar: list[str] = []

    for suite in _suite_dirs(experiment_dir):
        for task_dir in _materialized_tasks(suite):
            instruction = task_dir / "instruction.md"
            if not instruction.is_file():
                continue
            text = instruction.read_text(encoding="utf-8")
            if not any(pattern.search(text) for pattern in _GRAMMAR):
                off_grammar.append(f"{task_dir.name}: {text.strip().splitlines()[0][:80]!r}")

    assert not off_grammar, (
        "generated questions fall outside the grammar the agent parses:\n  "
        + "\n  ".join(off_grammar)
        + "\n\nThese fail on the baseline for the wrong reason, which is indistinguishable "
        "from the weakness under test. See dataset/task-template/README.md."
    )
