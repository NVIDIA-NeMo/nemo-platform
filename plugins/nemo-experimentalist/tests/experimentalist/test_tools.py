# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from nemo_experimentalist_plugin.experimentalist.components.coder import Coder
from nemo_experimentalist_plugin.experimentalist.components.holdout_utils import (
    BLOCKED_MESSAGE,
    HELD_OUT_STORAGE_DIR,
)
from nemo_experimentalist_plugin.experimentalist.components.tools import GuardedShellTools
from nooa.agentdoc import pformat
from nooa.tools import ShellResult


async def test_guarded_shell_tools_runs_allowed_commands(tmp_path):
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        result = await shell.run("python -", stdin="print('allowed')")
    finally:
        await shell.close()

    assert result.stdout.strip() == "allowed"
    assert result.returncode == 0
    assert result.success


@pytest.mark.parametrize(
    "command",
    [
        "cat dataset/validation/secret",
        "cat dataset/insight-validation/000-task/solution.sh",
        f"ls {HELD_OUT_STORAGE_DIR}",
    ],
)
async def test_guarded_shell_tools_returns_failure_for_blocked_paths(tmp_path, command: str):
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        result = await shell.run(command)
    finally:
        await shell.close()

    assert isinstance(result, ShellResult)
    assert result.stdout == ""
    assert result.stderr == BLOCKED_MESSAGE
    assert result.returncode == 1
    assert not result.success


async def test_guarded_shell_tools_allows_the_visible_insight_train_half(tmp_path):
    task_dir = tmp_path / "dataset" / "insight-train" / "000-task"
    task_dir.mkdir(parents=True)
    (task_dir / "task.md").write_text("visible\n")
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        result = await shell.run("cat dataset/insight-train/000-task/task.md")
    finally:
        await shell.close()

    assert result.stdout.strip() == "visible"
    assert result.success


def test_coder_hides_skill_registry_that_can_replace_guarded_shell(tmp_path):
    nooa_skill = Path(__file__).resolve().parents[2] / "framework-skills" / "nooa"
    coder = Coder(workspace=tmp_path, framework_skills_dirs=[nooa_skill])

    rendered = pformat(coder)

    assert "skills=SkillRegistry" not in rendered
    assert "shell=ShellTools" in rendered
    assert "nooa=Nooa" in rendered
