# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from nooa import TextSkill
from nooa.skill_registry import SkillRegistry


def load_framework_skills(registry: SkillRegistry, dirs: list[Path]) -> None:
    """Register TextSkills from user-provided framework skill directories."""
    for skill_dir in dirs:
        if not skill_dir.is_dir():
            continue
        if (skill_dir / "SKILL.md").exists() or (skill_dir / "skill.md").exists():
            skill = TextSkill(path=skill_dir)
            registry.register(f"ext.{skill.id}", skill)
    registry.load(["cmd.*", "ext.*"])
    registry.activate(["cmd.*", "ext.*"])
