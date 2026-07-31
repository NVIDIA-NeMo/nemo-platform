# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repo-shape probes, plus the traversal helpers the rest of discovery shares.

Three things matter to Eval Author but are not fields of a Harbor job config: the doctrine
document describing what the agent is for, any Harbor skill bundles the repo ships, and
whether the platform has traces for this agent to author evals from.

None of these probes ever returns a ``fail``. ``DiscoveryReport.runnable`` is false when
any finding failed, and that flag means precisely one thing: Harbor cannot run this
config. A repo with no traces yet, or no ``ETHOS.md``, runs its evals perfectly well. Only
the ladder in ``validate`` gets to fail a report.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from nemo_eval_author_plugin.discovery.models import Finding

_GROUP = "repo"

# Vendored and generated trees dwarf a repo's own content and never hold its eval setup.
#
# `eval-and-optimize` and `.nemo-optimizer` are Experimentalist's output, and pruning them is
# what keeps discover from reading the optimizer's own results as the repo's declared setup:
# they hold Harbor job dirs from the optimizer's runs and working copies of the agent, which
# every probe here would otherwise treat as candidates the repo maintains.
_PRUNE_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".eggs",
        ".cache",
        "site-packages",
        "dist",
        "build",
        "eval-and-optimize",
        ".nemo-optimizer",
    }
)
_MAX_WALK_DEPTH = 6

# ETHOS.md is the new name and AGENT-SPEC.md the old one, so both are honored while the
# rename is in flight. README.md is the fallback every repo has.
_DOCTRINE_FILENAMES = ("ETHOS.md", "AGENT-SPEC.md", "README.md")
_SKILL_FILENAME = "SKILL.md"
_MAX_LISTED_SKILLS = 10


def walk_dirs(root: Path, max_depth: int = _MAX_WALK_DEPTH) -> Iterator[Path]:
    """Yield directories under *root*, pruning vendored trees and bottoming out by depth."""
    root = root.resolve()
    root_depth = len(root.parts)
    for current, dir_names, _ in os.walk(root):
        current_path = Path(current)
        if len(current_path.parts) - root_depth >= max_depth:
            dir_names.clear()
        else:
            dir_names[:] = sorted(name for name in dir_names if name not in _PRUNE_DIR_NAMES)
        yield current_path


def display_path(path: Path, repo_root: Path) -> str:
    """Render *path* relative to the repo when it lives there, absolute when it does not.

    Not every discovered path is inside the repo: ``discover_profile`` walks upward, so an
    ``optimizer.yaml`` in a parent directory is a legitimate find rather than an error to
    crash on. A path that is already relative is left alone, which also covers the
    ``<job config>`` sentinel used for values declared inline rather than in a file.
    """
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def find_doctrine(repo_root: Path) -> Finding:
    """Locate the document describing what the agent is supposed to do.

    Recording which name matched makes the report double as a signal for the
    ``AGENT-SPEC.md`` to ``ETHOS.md`` rename: a repo still on the old name says so here.
    """
    for name in _DOCTRINE_FILENAMES:
        candidate = repo_root / name
        if candidate.is_file():
            return Finding(
                name="doctrine",
                group=_GROUP,
                status="pass",
                message=f"Agent doctrine at {name}",
                path=candidate,
                hint=(
                    "ETHOS.md is the current name; this repo predates the rename." if name == "AGENT-SPEC.md" else None
                ),
            )
    return Finding(
        name="doctrine",
        group=_GROUP,
        status="warn",
        message=f"No {' or '.join(_DOCTRINE_FILENAMES)} at the repo root",
        hint="Eval Author writes better cases when the repo states what the agent is for.",
    )


def find_skills(repo_root: Path) -> Finding:
    """Find Harbor skill bundles, the directories a ``SKILL.md`` marks.

    These are what ``harbor.skills`` resolves for ``AgentConfig.skills`` and mounts at
    ``[environment].skills_dir``. Not the same thing as ``framework_skills`` in
    ``optimizer.yaml``: a repo can ship both, and they are handed to different consumers.
    """
    skills = [directory for directory in walk_dirs(repo_root) if (directory / _SKILL_FILENAME).is_file()]
    if not skills:
        return Finding(
            name="skills",
            group=_GROUP,
            status="warn",
            message=f"No {_SKILL_FILENAME} bundles found",
            hint="Only relevant if the agent under test is meant to receive Harbor skills.",
        )

    listed = ", ".join(display_path(path, repo_root) for path in skills[:_MAX_LISTED_SKILLS])
    remainder = len(skills) - _MAX_LISTED_SKILLS
    return Finding(
        name="skills",
        group=_GROUP,
        status="pass",
        message=f"{len(skills)} Harbor skill bundle(s): {listed}"
        + (f", and {remainder} more" if remainder > 0 else ""),
        path=skills[0],
        hint="Pass these to a job via AgentConfig.skills; they mount at [environment].skills_dir.",
    )


async def probe_traces(client: Any, *, agent: str, workspace: str) -> Finding:
    """Count the agent's distinct sessions in Intake, which is Eval Author's raw material.

    A "trace" is one distinct ``session_id`` among the agent's spans, because only spans
    carry the agent identity. This is the rollup ``count_agent_sessions`` performs in the
    insights analyst backend; the SDK call is made directly here rather than importing
    that class, which would drag a backend and its persistence into a read-only probe.
    """
    try:
        page = await client.intake.spans.groups.list(
            workspace=workspace,
            by="session_id",
            page=1,
            page_size=1,
            filter={"agent_name": agent},
            sort="-span_count",
        )
    except Exception as exc:
        return Finding(
            name="traces",
            group=_GROUP,
            status="warn",
            message=f"Could not read traces for '{agent}': {type(exc).__name__}: {exc}",
            hint="Traces feed later Eval Author stages; Harbor runs fine without them.",
        )

    total = page.pagination.total_results if page.pagination is not None else len(page.data)
    if not total:
        return Finding(
            name="traces",
            group=_GROUP,
            status="warn",
            message=f"No traces recorded for agent '{agent}' in workspace '{workspace}'",
            hint="Run the agent with telemetry enabled to give Eval Author something to author from.",
        )
    return Finding(
        name="traces",
        group=_GROUP,
        status="pass",
        message=f"{total} trace session(s) available for '{agent}' in workspace '{workspace}'",
    )
