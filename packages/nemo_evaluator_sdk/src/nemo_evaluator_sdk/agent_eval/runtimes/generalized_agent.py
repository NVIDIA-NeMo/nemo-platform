# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plug-and-play seam for generalized-agent CLIs (codex/claude/cursor/...).

"Generalized agents" follows the *Agents Improving Agents* terminology: a single
CLI that takes a prompt and autonomously drives a task to completion. The split
that makes these plug-and-play:

* :class:`GeneralizedAgentDriver` is the **driver** — a generic
  ``AgentAttemptRuntime`` that runs a CLI which reads a prompt on stdin and writes
  its final answer to a file, then captures workspace/stdout/stderr/final-output
  as evidence. This is the stable, reusable part.
* :class:`GeneralizedAgentSpec` is the **per-agent adapter** — the bespoke part:
  how to build the CLI command and (optionally) how to parse that agent's
  trajectory into extra evidence. Implementing a new agent means subclassing this,
  not rewriting a runtime.

Reference specs (e.g. :class:`~nemo_evaluator_sdk.agent_eval.runtimes.claude_code.ClaudeCodeSpec`
and :class:`~nemo_evaluator_sdk.agent_eval.runtimes.cursor_agent.CursorAgentSpec`)
live in their own modules: the driver and evidence contract are stable, but each
CLI's exact flags and trajectory format are the integrator's responsibility and
may drift with upstream releases. Auth is the caller's concern (inject via env);
nothing here hardcodes credentials.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalTask,
    AgentOutput,
)
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

DEFAULT_GENERALIZED_AGENT_TIMEOUT_S = 600
ProcessFactory = Callable[..., Awaitable[object]]


@dataclass(frozen=True)
class RunArtifacts:
    """Resolved on-disk paths for one generalized-agent attempt."""

    evidence_dir: Path
    workspace_dir: Path
    prompt_path: Path
    task_path: Path
    stdout_path: Path
    stderr_path: Path
    final_output_path: Path


class GeneralizedAgentSpec:
    """Per-agent adapter: prompt, command, and trajectory→evidence parsing.

    Subclass and implement :meth:`build_command`. Override :meth:`build_prompt`,
    :meth:`extra_evidence`, or :meth:`final_output` for agent-specific behavior.
    """

    name: str = "generalized_agent"
    binary: str = ""
    model: str | None = None

    def build_prompt(self, task: AgentEvalTask) -> str:
        """Default instruction prompt (override per agent if needed)."""
        return f"Task id: {task.id}\nIntent: {task.intent}\nInputs: {task.inputs}\n"

    def build_command(self, artifacts: RunArtifacts) -> list[str]:
        """Return the argv to launch; the prompt is delivered on stdin."""
        raise NotImplementedError

    def extra_evidence(self, artifacts: RunArtifacts) -> dict[str, EvidenceDescriptor]:
        """Optional per-agent evidence (e.g. a parsed trajectory). Default: none."""
        return {}

    def final_output(self, artifacts: RunArtifacts, stdout_text: str) -> str:
        """Final answer text: prefer the written final-output file, else stdout."""
        if artifacts.final_output_path.exists():
            return artifacts.final_output_path.read_text(encoding="utf-8")
        return stdout_text


class GeneralizedAgentDriver:
    """Generic ``AgentAttemptRuntime`` for stdin-prompt generalized-agent CLIs."""

    def __init__(
        self,
        spec: GeneralizedAgentSpec,
        *,
        work_root: str | Path | None = None,
        timeout_s: int = DEFAULT_GENERALIZED_AGENT_TIMEOUT_S,
        process_factory: ProcessFactory | None = None,
    ) -> None:
        if not spec.binary:
            raise ValueError(f"{type(spec).__name__} must set a non-empty `binary`")
        self._spec = spec
        self._work_root = Path(work_root).expanduser() if work_root is not None else None
        self._timeout_s = timeout_s
        self._process_factory = process_factory or asyncio.create_subprocess_exec

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalAttempt]:
        if self._process_factory is asyncio.create_subprocess_exec and shutil.which(self._spec.binary) is None:
            raise RuntimeError(f"{self._spec.name} CLI executable {self._spec.binary!r} was not found on PATH")

        resolved = config or AgentEvalRunConfig()
        semaphore = asyncio.Semaphore(resolved.parallelism)

        async def run_one(index: int, task: AgentEvalTask) -> AgentEvalAttempt:
            async with semaphore:
                return await self._run_task(index, task, resolved)

        return await asyncio.gather(*(run_one(index, task) for index, task in enumerate(tasks)))

    async def _run_task(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> AgentEvalAttempt:
        artifacts = self._artifacts(index, task, config)
        artifacts.evidence_dir.mkdir(parents=True, exist_ok=True)
        artifacts.workspace_dir.mkdir(parents=True, exist_ok=True)

        prompt = self._spec.build_prompt(task)
        artifacts.prompt_path.write_text(prompt, encoding="utf-8")
        artifacts.task_path.write_text(task.model_dump_json(indent=2), encoding="utf-8")

        command = self._spec.build_command(artifacts)
        try:
            process = await self._process_factory(
                *command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")),
                timeout=self._timeout_s,
            )
        except Exception as exc:
            return self._failed_attempt(task, artifacts, exc)

        stdout_text = _decode(stdout)
        stderr_text = _decode(stderr)
        artifacts.stdout_path.write_text(stdout_text, encoding="utf-8")
        artifacts.stderr_path.write_text(stderr_text, encoding="utf-8")

        return_code = getattr(process, "returncode", 0)
        if return_code:
            return self._failed_attempt(
                task,
                artifacts,
                RuntimeError(f"{self._spec.name} exited with status {return_code}: {stderr_text.strip()}"),
            )

        descriptors: dict[str, EvidenceDescriptor] = {
            "workspace": EvidenceDescriptor(kind="filesystem", format="dir", ref=str(artifacts.workspace_dir)),
            "prompt": EvidenceDescriptor(kind="text", format="txt", ref=str(artifacts.prompt_path)),
            "task": EvidenceDescriptor(kind="json", format="json", ref=str(artifacts.task_path)),
            "stdout": EvidenceDescriptor(kind="logs", format="txt", ref=str(artifacts.stdout_path)),
            "stderr": EvidenceDescriptor(kind="logs", format="txt", ref=str(artifacts.stderr_path)),
        }
        descriptors.update(self._spec.extra_evidence(artifacts))

        return AgentEvalAttempt(
            id=f"{task.id}:{self._spec.name}",
            task_id=task.id,
            status="completed",
            output=AgentOutput(
                text=self._spec.final_output(artifacts, stdout_text),
                metadata={
                    "runtime": self._spec.name,
                    "agent_model": self._spec.model,
                    "evidence_dir": str(artifacts.evidence_dir),
                },
            ),
            evidence=CandidateEvidence(descriptors=descriptors, metadata={"runtime": self._spec.name}),
            metadata={
                "runtime": self._spec.name,
                "agent_model": self._spec.model,
                "generated": True,
            },
        )

    def _failed_attempt(self, task: AgentEvalTask, artifacts: RunArtifacts, exc: Exception) -> AgentEvalAttempt:
        error_path = artifacts.evidence_dir / "error.json"
        error_path.write_text(
            json.dumps({"error_type": exc.__class__.__name__, "error": str(exc)}) + "\n", encoding="utf-8"
        )
        return AgentEvalAttempt(
            id=f"{task.id}:{self._spec.name}",
            task_id=task.id,
            status="failed",
            output=None,
            evidence=CandidateEvidence(
                descriptors={"error": EvidenceDescriptor(kind="error", format="json", ref=str(error_path))},
                metadata={"runtime": self._spec.name},
            ),
            metadata={
                "runtime": self._spec.name,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            },
        )

    def _artifacts(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> RunArtifacts:
        root = self._work_root or ((config.output_dir or Path.cwd()) / "evidence" / self._spec.name)
        evidence_dir = Path(root) / (_safe_path_name(task.id) or f"task-{index}")
        return RunArtifacts(
            evidence_dir=evidence_dir,
            workspace_dir=evidence_dir / "workspace",
            prompt_path=evidence_dir / "prompt.txt",
            task_path=evidence_dir / "task.json",
            stdout_path=evidence_dir / "stdout.txt",
            stderr_path=evidence_dir / "stderr.txt",
            final_output_path=evidence_dir / "final_output.txt",
        )


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _safe_path_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip(".-")[:120]


__all__ = [
    "DEFAULT_GENERALIZED_AGENT_TIMEOUT_S",
    "GeneralizedAgentDriver",
    "GeneralizedAgentSpec",
    "RunArtifacts",
]
