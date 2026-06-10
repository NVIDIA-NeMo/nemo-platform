# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Claude skill discovery helpers for the Studio coding-agent bridge."""

import logging
from collections.abc import Iterable
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from nemo_platform_ext.cli.commands.skills.base import Scope, Skill
from nemo_platform_ext.cli.commands.skills.registry import (
    DuplicateSkillError,
    _load_skills_from_root,
    get_installer,
    load_skills,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_PLATFORM_SKILL_SOURCE_DISTS = frozenset({"nemo-platform-ext", "nemo-platform-sdk"})
_AGGREGATE_SKILL_SOURCE_DIST = "nemo-platform"


class ClaudeSkillResponse(BaseModel):
    """A NeMo skill as it is exposed to Claude Code for this repository."""

    name: str
    claude_name: str
    description: str
    source: str
    source_path: str | None = None
    install_path: str
    installed: bool


def _skill_entry_point_dist_name(entry_point: Any) -> str | None:
    dist = getattr(entry_point, "dist", None)
    name = getattr(dist, "name", None)
    return name if isinstance(name, str) else None


def _skill_entry_point_preference(entry_point: Any) -> tuple[int, str]:
    """Pick editable plugin providers before the bundled aggregate distribution."""
    dist_name = _skill_entry_point_dist_name(entry_point)
    if entry_point.name == "platform":
        if dist_name == "nemo-platform-ext":
            return (0, dist_name)
        if dist_name == _AGGREGATE_SKILL_SOURCE_DIST:
            return (1, dist_name)
        if dist_name == "nemo-platform-sdk":
            return (2, dist_name)
    if dist_name == _AGGREGATE_SKILL_SOURCE_DIST:
        return (1, dist_name)
    return (0, dist_name or "")


def _allowed_skill_provider_names() -> set[str] | None:
    try:
        from nemo_platform_plugin.discovery import discover_entry_points
    except ImportError:
        logger.warning("nemo-platform-plugin is unavailable; using all nemo.skills entry points", exc_info=True)
        return None
    return set(discover_entry_points("nemo.skills").keys())


def _raw_skill_entry_points() -> Iterable[Any]:
    return entry_points(group="nemo.skills")


def _resolve_skills_entry_point_root(entry_point: Any) -> Path | None:
    try:
        skills_dir_factory = entry_point.load()
    except Exception:
        logger.warning(
            "Failed to load 'nemo.skills' entry point %r (%s) - skipping",
            entry_point.name,
            entry_point.value,
            exc_info=True,
        )
        return None

    try:
        skills_root = skills_dir_factory()
    except Exception:
        logger.warning("Failed to resolve skills directory for provider %r", entry_point.name, exc_info=True)
        return None

    if not isinstance(skills_root, Path):
        logger.warning(
            "Skipping provider %r skills: expected Path, got %s",
            entry_point.name,
            type(skills_root).__name__,
        )
        return None
    if not skills_root.is_dir():
        logger.warning("Skipping provider %r skills: path is not a directory: %s", entry_point.name, skills_root)
        return None
    return skills_root


def _load_skills_from_preferred_entry_points() -> dict[str, Skill]:
    """Load skills for Studio while preferring editable source providers over vendored mirrors."""
    allowed_names = _allowed_skill_provider_names()
    candidates_by_name: dict[str, list[tuple[Any, Path]]] = {}
    for entry_point in _raw_skill_entry_points():
        if allowed_names is not None and entry_point.name not in allowed_names:
            continue
        skills_root = _resolve_skills_entry_point_root(entry_point)
        if skills_root is None:
            continue
        candidates_by_name.setdefault(entry_point.name, []).append((entry_point, skills_root))

    all_skills: dict[str, Skill] = {}
    for provider_name in sorted(candidates_by_name):
        entry_point, skills_root = min(
            candidates_by_name[provider_name],
            key=lambda candidate: _skill_entry_point_preference(candidate[0]),
        )
        source_dist = _skill_entry_point_dist_name(entry_point)
        for skill in _load_skills_from_root(skills_root, source_plugin=provider_name, source_dist=source_dist).values():
            existing = all_skills.get(skill.name)
            if existing is not None:
                raise DuplicateSkillError(
                    f"Duplicate skill '{skill.name}' found in provider {provider_name}: "
                    f"{skill.source_dir}. Already defined in {existing.source_dir}."
                )
            all_skills[skill.name] = skill
    return dict(sorted(all_skills.items()))


def _load_claude_skills() -> dict[str, Skill]:
    try:
        return load_skills()
    except DuplicateSkillError as exc:
        logger.warning(
            "Skill registry has duplicate provider content; falling back to preferred editable providers: %s",
            exc,
        )
        return _load_skills_from_preferred_entry_points()


def _path_for_response(path: Path, server_cwd: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(server_cwd))
    except ValueError:
        return str(resolved)


def _skill_source_label(skill: Skill) -> str:
    if skill.source_dist is not None:
        if skill.source_dist in _PLATFORM_SKILL_SOURCE_DISTS:
            return "nemo-platform"
        return skill.source_dist
    if skill.source_plugin is not None:
        return skill.source_plugin
    return "-"


def _claude_skill_response(name: str, skill: Skill, server_cwd: Path) -> ClaudeSkillResponse:
    installer = get_installer("claude")
    install_path = installer.get_install_path(Scope.PROJECT, server_cwd, name)
    source_path = _path_for_response(skill.source_dir, server_cwd) if skill.source_dir is not None else None
    return ClaudeSkillResponse(
        name=name,
        claude_name=install_path.parent.name,
        description=skill.description,
        source=_skill_source_label(skill),
        source_path=source_path,
        install_path=_path_for_response(install_path, server_cwd),
        installed=install_path.is_file(),
    )


def list_claude_skill_responses(server_cwd: Path) -> list[ClaudeSkillResponse]:
    """List NeMo skills with Claude Code install metadata for a Studio working directory."""
    skills = _load_claude_skills()
    return [_claude_skill_response(name, skill, server_cwd) for name, skill in skills.items()]
