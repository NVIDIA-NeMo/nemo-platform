# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixture-based tests for the generalized-agent driver seam (no real CLIs)."""

from __future__ import annotations

from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.claude_code import ClaudeCodeSpec
from nemo_evaluator_sdk.agent_eval.runtimes.cursor_agent import CursorAgentSpec
from nemo_evaluator_sdk.agent_eval.runtimes.generalized_agent import (
    GeneralizedAgentDriver,
    GeneralizedAgentSpec,
    RunArtifacts,
)
from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunConfig, AgentEvalTask


class _EchoSpec(GeneralizedAgentSpec):
    name = "echo_agent"
    binary = "echo-agent"

    def build_command(self, artifacts: RunArtifacts) -> list[str]:
        return [self.binary, "--out", str(artifacts.final_output_path)]

    def extra_evidence(self, artifacts: RunArtifacts) -> dict:
        from nemo_evaluator_sdk.values.evidence import EvidenceDescriptor

        return {"trajectory": EvidenceDescriptor(kind="trace", format="jsonl", ref=str(artifacts.stdout_path))}


class _FakeProcess:
    def __init__(self, *, returncode: int, final_output_path: Path | None, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self._final_output_path = final_output_path
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self, stdin: bytes | None = None) -> tuple[bytes, bytes]:
        if self._final_output_path is not None:
            self._final_output_path.write_text("final answer", encoding="utf-8")
        return self._stdout, self._stderr


def _factory(*, returncode: int = 0, write_final: bool = True):
    captured: dict = {}

    async def factory(*command, **kwargs):
        captured["command"] = list(command)
        final_path = Path(command[command.index("--out") + 1]) if "--out" in command else None
        return _FakeProcess(
            returncode=returncode,
            final_output_path=final_path if write_final else None,
            stdout=b'{"event":"done"}\n',
        )

    return factory, captured


def _task() -> AgentEvalTask:
    return AgentEvalTask(id="demo/task", intent="do the thing", inputs={"k": "v"})


@pytest.mark.asyncio
async def test_driver_produces_completed_attempt_with_evidence(tmp_path: Path) -> None:
    factory, captured = _factory()
    driver = GeneralizedAgentDriver(_EchoSpec(), work_root=tmp_path, process_factory=factory)

    attempts = await driver.run_tasks([_task()], AgentEvalRunConfig())
    attempt = attempts[0]

    assert captured["command"][0] == "echo-agent"
    assert attempt.status == "completed"
    assert attempt.output is not None and attempt.output.text == "final answer"
    # Standard + spec-provided evidence keys are present and paths exist on disk.
    assert {"workspace", "prompt", "task", "stdout", "stderr", "trajectory"} <= set(attempt.evidence.descriptors)
    assert (tmp_path / "demo-task" / "prompt.txt").read_text(encoding="utf-8").startswith("Task id: demo/task")


@pytest.mark.asyncio
async def test_driver_marks_failed_on_nonzero_exit(tmp_path: Path) -> None:
    factory, _ = _factory(returncode=1, write_final=False)
    driver = GeneralizedAgentDriver(_EchoSpec(), work_root=tmp_path, process_factory=factory)

    attempt = (await driver.run_tasks([_task()]))[0]
    assert attempt.status == "failed"
    assert attempt.output is None
    assert "error" in attempt.evidence.descriptors
    assert (tmp_path / "demo-task" / "error.json").exists()


def test_reference_specs_build_expected_commands(tmp_path: Path) -> None:
    artifacts = RunArtifacts(
        evidence_dir=tmp_path,
        workspace_dir=tmp_path / "workspace",
        prompt_path=tmp_path / "p",
        task_path=tmp_path / "t",
        stdout_path=tmp_path / "o",
        stderr_path=tmp_path / "e",
        final_output_path=tmp_path / "f",
    )
    claude_cmd = ClaudeCodeSpec(model="claude-x").build_command(artifacts)
    assert claude_cmd[0] == "claude" and "--model" in claude_cmd and "claude-x" in claude_cmd

    cursor_cmd = CursorAgentSpec().build_command(artifacts)
    assert cursor_cmd[0] == "cursor-agent" and "--model" not in cursor_cmd


def test_driver_rejects_spec_without_binary(tmp_path: Path) -> None:
    class _NoBinary(GeneralizedAgentSpec):
        def build_command(self, artifacts: RunArtifacts) -> list[str]:
            return []

    with pytest.raises(ValueError, match="non-empty"):
        GeneralizedAgentDriver(_NoBinary(), work_root=tmp_path)
