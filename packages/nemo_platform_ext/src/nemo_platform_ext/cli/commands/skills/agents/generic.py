# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic agent installer for Agent Skills-compatible folders."""

from pathlib import Path

import yaml
from nemo_platform_ext.cli.commands.skills.base import Scope, Skill
from nemo_platform_ext.cli.commands.skills.installer import BaseAgentInstaller


class GenericInstaller(BaseAgentInstaller):
    name = "generic"
    display_name = "Generic (.agents/skills)"
    supported_scopes = [Scope.PROJECT, Scope.USER]

    def get_install_path(self, scope: Scope, project_root: Path, skill_name: str) -> Path:
        if scope == Scope.PROJECT:
            return project_root / ".agents" / "skills" / f"nemo-{skill_name}" / "SKILL.md"
        return Path.home() / ".agents" / "skills" / f"nemo-{skill_name}" / "SKILL.md"

    def format_content(self, skill: Skill) -> str:
        front_matter = yaml.safe_dump(
            {"name": f"nemo-{skill.name}", "description": skill.description},
            sort_keys=False,
            allow_unicode=True,
        )
        return f"---\n{front_matter}---\n\n{skill.content}"
