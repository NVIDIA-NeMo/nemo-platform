# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import Any, cast

from nemo_experimentalist_plugin.experimentalist.components.coder import Coder
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DependencyCommandResult
from nemo_experimentalist_plugin.experimentalist.components.holdout_utils import BLOCKED_MESSAGE
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


async def test_guarded_shell_tools_returns_failure_for_blocked_paths(tmp_path):
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        result = await shell.run("cat dataset/validation/secret")
    finally:
        await shell.close()

    assert isinstance(result, ShellResult)
    assert result.stdout == ""
    assert result.stderr == BLOCKED_MESSAGE
    assert result.returncode == 1
    assert not result.success


async def test_guarded_shell_tools_routes_through_executable_dependency_runtime(tmp_path):
    class FakeRuntime:
        commands: list[tuple[str, str | None, float]] = []

        async def execute(
            self,
            command: str,
            *,
            stdin: str | None = None,
            timeout: float = 30.0,
        ) -> DependencyCommandResult:
            self.commands.append((command, stdin, timeout))
            return DependencyCommandResult(stdout="/app\n", returncode=0)

    runtime = FakeRuntime()
    shell = GuardedShellTools(cwd=tmp_path)
    try:
        with shell.use_dependency_runtime(cast(Any, runtime)):
            result = await shell.run("pwd", stdin="input", timeout=12.5)
    finally:
        await shell.close()

    assert result == ShellResult(stdout="/app\n", stderr="", returncode=0)
    assert runtime.commands == [("pwd", "input", 12.5)]


def test_coder_hides_skill_registry_that_can_replace_guarded_shell(tmp_path):
    nooa_skill = Path(__file__).resolve().parents[2] / "framework-skills" / "nooa"
    coder = Coder(workspace=tmp_path, framework_skills_dirs=[nooa_skill])

    rendered = pformat(coder)

    assert "skills=SkillRegistry" not in rendered
    assert "shell=ShellTools" in rendered
    assert "nooa=Nooa" in rendered
