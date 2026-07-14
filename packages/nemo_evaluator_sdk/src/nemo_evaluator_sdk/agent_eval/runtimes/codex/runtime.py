# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Codex-backed agent-eval runtimes."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval.runtimes.docker_sandbox import DockerSandboxAgentRuntime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.agent_eval.workspace_seeds import SEED_FILES_INPUT_KEY, seed_workspace
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

DEFAULT_CODEX_TIMEOUT_S = 600
DEFAULT_CODEX_DOCKER_MODEL = "gpt-5.4"
DEFAULT_CODEX_DOCKER_CLI_IMAGE = "node:22-alpine"
DEFAULT_CODEX_DOCKER_CLI_PACKAGE = "@openai/codex@0.137.0"
ProcessFactory = Callable[..., Awaitable[Any]]


class RuntimeChoice(StrEnum):
    """Which Codex execution mode the caller wants."""

    DOCKER = "docker"
    LOCAL = "local"


class EffectiveCodexRuntime(StrEnum):
    """The concrete runtime chosen for a :class:`RuntimeChoice` + environment."""

    DOCKER_SANDBOX = "docker_sandbox"
    DOCKER_CLI = "docker_cli"
    LOCAL_CLI = "local_cli"


#: Builds the prompt handed to Codex on stdin for a task. Swap it to change how a task is framed
#: (e.g. a benchmark-specific preamble); the default presents the task and invites workspace edits.
CodexPromptBuilder = Callable[[AgentEvalTask], str]


class CodexCliAgentRuntime:
    """AgentTaskRunner that uses the locally installed Codex CLI credentials."""

    def __init__(
        self,
        *,
        model: str | None = None,
        work_root: str | Path | None = None,
        codex_bin: str = "codex",
        timeout_s: int = DEFAULT_CODEX_TIMEOUT_S,
        prompt_builder: CodexPromptBuilder | None = None,
        process_factory: ProcessFactory | None = None,
        runtime_name: str = "codex_cli",
    ) -> None:
        self._model = model
        self._work_root = Path(work_root).expanduser() if work_root is not None else None
        self._codex_bin = codex_bin
        self._timeout_s = timeout_s
        self._prompt_builder = prompt_builder or AgentEvalTask.agent_prompt
        self._process_factory = process_factory or asyncio.create_subprocess_exec
        self._runtime_name = runtime_name

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalTrial]:
        if shutil.which(self._codex_bin) is None:
            raise RuntimeError(f"Codex CLI executable {self._codex_bin!r} was not found on PATH")

        resolved_config = config or AgentEvalRunConfig()
        semaphore = asyncio.Semaphore(resolved_config.parallelism)

        async def run_one(index: int, task: AgentEvalTask) -> AgentEvalTrial:
            async with semaphore:
                return await self._run_task(index, task, resolved_config)

        return await asyncio.gather(*(run_one(index, task) for index, task in enumerate(tasks)))

    async def _run_task(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> AgentEvalTrial:
        evidence_dir = self._evidence_dir(index, task, config)
        workspace_dir = evidence_dir / "workspace"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        prompt_path = evidence_dir / "prompt.txt"
        task_path = evidence_dir / "task.json"
        stdout_path = evidence_dir / "stdout.jsonl"
        stderr_path = evidence_dir / "stderr.txt"
        final_output_path = evidence_dir / "final_output.txt"

        # Persist the task for debugging, but never the grader-only fields: the docker variant mounts
        # this evidence dir into the sandbox (danger-full-access), so serializing `intent` (desired
        # behavior) or `reference` (held-out ground truth) here would let the agent read them back out
        # of `/evidence/task.json` — the same reward-hacking leak the intent-free prompt closes.
        task_path.write_text(task.model_dump_json(indent=2, exclude={"intent", "reference"}), encoding="utf-8")

        command = self._command(workspace_dir=workspace_dir, final_output_path=final_output_path)
        process: Any | None = None
        try:
            # Seed inside the guarded block so a bad seed (e.g. a path escaping the workspace) fails
            # just this task rather than aborting the whole run. Offload to a worker thread: seeding is
            # synchronous (a handler may do blocking I/O, e.g. the plugin's fileset download), and this
            # runs on the event loop shared by every concurrent task, so a blocking seed would stall them all.
            seeded_files = await asyncio.to_thread(seed_workspace, workspace_dir, task.inputs.get(SEED_FILES_INPUT_KEY))
            # Build the prompt after seeding and inside the guarded block: an instruction-less task
            # raises here, failing just this task instead of aborting the run (and seeding wins if both).
            prompt = self._prompt_builder(task)
            prompt_path.write_text(prompt, encoding="utf-8")
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
        except TimeoutError as exc:
            await _terminate_process(process)
            return _failed_codex_trial(task, evidence_dir, exc, runtime_name=self._runtime_name)
        except Exception as exc:
            return _failed_codex_trial(task, evidence_dir, exc, runtime_name=self._runtime_name)

        stdout_text = _decode_process_output(stdout)
        stderr_text = _decode_process_output(stderr)
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")

        if process.returncode != 0:
            return _failed_codex_trial(
                task,
                evidence_dir,
                RuntimeError(f"codex exec exited with status {process.returncode}: {stderr_text.strip()}"),
                runtime_name=self._runtime_name,
            )

        if final_output_path.exists():
            output_text = final_output_path.read_text(encoding="utf-8")
        else:
            output_text = stdout_text
            final_output_path.write_text(output_text, encoding="utf-8")
        return AgentEvalTrial(
            id=f"{task.id}:codex",
            task_id=task.id,
            status=AgentEvalTrialStatus.COMPLETED,
            output=AgentOutput(
                output_text=output_text,
                metadata={
                    "runtime": self._runtime_name,
                    "agent": "codex",
                    "agent_model": self._model,
                    "evidence_dir": str(evidence_dir),
                },
            ),
            evidence=CandidateEvidence(
                descriptors={
                    "workspace": EvidenceDescriptor(kind="filesystem", ref=str(workspace_dir)),
                    "prompt": EvidenceDescriptor(kind="text", format="txt", ref=str(prompt_path)),
                    "task": EvidenceDescriptor(kind="json", format="json", ref=str(task_path)),
                    "stdout": EvidenceDescriptor(kind="codex_stdout", format="jsonl", ref=str(stdout_path)),
                    "stderr": EvidenceDescriptor(kind="text", format="txt", ref=str(stderr_path)),
                    "final_output": EvidenceDescriptor(kind="text", format="txt", ref=str(final_output_path)),
                },
                metadata={"runtime": self._runtime_name, "agent": "codex"},
            ),
            metadata={
                "runtime": self._runtime_name,
                "agent": "codex",
                "agent_model": self._model,
                "agent_ok": True,
                "seeded_files": seeded_files,
                "generated": True,
            },
        )

    def _command(self, *, workspace_dir: Path, final_output_path: Path) -> list[str]:
        command = [
            self._codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(workspace_dir),
            "--output-last-message",
            str(final_output_path),
            "--json",
        ]
        if self._model is not None:
            command.extend(["--model", self._model])
        command.append("-")
        return command

    def _evidence_dir(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> Path:
        root = self._work_root
        if root is None:
            root = (config.output_dir or Path.cwd()) / "evidence" / "codex"
        safe_task_id = _safe_path_name(task.id)
        task_dir = f"{index:06d}-{safe_task_id}" if safe_task_id else f"task-{index:06d}"
        return Path(root) / task_dir


class CodexDockerCliAgentRuntime(CodexCliAgentRuntime):
    """AgentTaskRunner that runs Codex CLI inside a Docker container."""

    def __init__(
        self,
        *,
        model: str | None = None,
        work_root: str | Path | None = None,
        docker_bin: str = "docker",
        image: str = DEFAULT_CODEX_DOCKER_CLI_IMAGE,
        codex_package: str = DEFAULT_CODEX_DOCKER_CLI_PACKAGE,
        auth_path: str | Path | None = None,
        timeout_s: int = DEFAULT_CODEX_TIMEOUT_S,
        prompt_builder: CodexPromptBuilder | None = None,
        process_factory: ProcessFactory | None = None,
    ) -> None:
        super().__init__(
            model=model,
            work_root=work_root,
            timeout_s=timeout_s,
            prompt_builder=prompt_builder,
            process_factory=process_factory,
            runtime_name="codex_docker_cli",
        )
        self._docker_bin = docker_bin
        self._image = image
        self._codex_package = codex_package
        self._auth_path = (
            Path(auth_path).expanduser() if auth_path is not None else Path.home() / ".codex" / "auth.json"
        )

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalTrial]:
        if shutil.which(self._docker_bin) is None:
            raise RuntimeError(f"Docker executable {self._docker_bin!r} was not found on PATH")
        if not self._auth_path.exists():
            raise RuntimeError(
                f"Codex auth file was not found at {self._auth_path}. Run `codex login` or use OPENAI_API_KEY "
                "so --runtime docker can use DockerSandboxAgentRuntime."
            )

        resolved_config = config or AgentEvalRunConfig()
        semaphore = asyncio.Semaphore(resolved_config.parallelism)

        async def run_one(index: int, task: AgentEvalTask) -> AgentEvalTrial:
            async with semaphore:
                return await self._run_task(index, task, resolved_config)

        return await asyncio.gather(*(run_one(index, task) for index, task in enumerate(tasks)))

    def _command(self, *, workspace_dir: Path, final_output_path: Path) -> list[str]:
        evidence_dir = final_output_path.parent
        inner_command = [
            "npx",
            "-y",
            self._codex_package,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "danger-full-access",
            "--cd",
            "/workspace",
            "--output-last-message",
            "/evidence/final_output.txt",
            "--json",
        ]
        if self._model is not None:
            inner_command.extend(["--model", self._model])
        inner_command.append("-")
        return [
            self._docker_bin,
            "run",
            "--rm",
            "-i",
            "-v",
            f"{self._auth_path.resolve()}:/root/.codex/auth.json:ro",
            "-v",
            f"{workspace_dir.resolve()}:/workspace",
            "-v",
            f"{evidence_dir.resolve()}:/evidence",
            self._image,
            "sh",
            "-lc",
            shlex.join(inner_command),
        ]


def resolve_codex_runtime(
    *,
    runtime: RuntimeChoice,
    model: str | None,
    output_dir: Path,
    env: Mapping[str, str] = os.environ,
    prompt_builder: CodexPromptBuilder | None = None,
) -> tuple[CodexCliAgentRuntime | CodexDockerCliAgentRuntime | DockerSandboxAgentRuntime, EffectiveCodexRuntime]:
    """Pick and construct a Codex runtime for a run-mode + environment.

    ``local`` runs the on-PATH Codex CLI. ``docker`` prefers the OpenAI-Agents ``DockerSandbox`` when
    ``OPENAI_API_KEY`` is an OpenAI platform secret (``sk-...``) and otherwise falls back to the
    containerized Codex CLI (which mounts ``~/.codex/auth.json``). ``prompt_builder`` is threaded into
    the CLI runtimes; the sandbox runtime does its own prompting. Returns the runtime plus the
    :class:`EffectiveCodexRuntime` actually chosen so callers can label/report it.
    """
    effective_runtime = _resolve_codex_runtime(runtime, env)
    if effective_runtime == EffectiveCodexRuntime.LOCAL_CLI:
        return (
            CodexCliAgentRuntime(
                model=model,
                work_root=output_dir / "evidence" / "codex",
                prompt_builder=prompt_builder,
            ),
            effective_runtime,
        )
    if effective_runtime == EffectiveCodexRuntime.DOCKER_CLI:
        return (
            CodexDockerCliAgentRuntime(
                model=model,
                work_root=output_dir / "evidence" / "codex-docker",
                prompt_builder=prompt_builder,
            ),
            effective_runtime,
        )
    if effective_runtime == EffectiveCodexRuntime.DOCKER_SANDBOX:
        return DockerSandboxAgentRuntime(model=model or DEFAULT_CODEX_DOCKER_MODEL), effective_runtime
    raise ValueError(f"unsupported Codex runtime {runtime!r}")


def _resolve_codex_runtime(runtime: RuntimeChoice, env: Mapping[str, str] = os.environ) -> EffectiveCodexRuntime:
    if runtime == RuntimeChoice.LOCAL:
        return EffectiveCodexRuntime.LOCAL_CLI
    if runtime == RuntimeChoice.DOCKER:
        if _openai_sdk_secret_key_is_set(env):
            return EffectiveCodexRuntime.DOCKER_SANDBOX
        return EffectiveCodexRuntime.DOCKER_CLI
    raise ValueError(f"unsupported Codex runtime {runtime!r}")


def _openai_sdk_secret_key_is_set(env: Mapping[str, str] = os.environ) -> bool:
    return env.get("OPENAI_API_KEY", "").strip().startswith("sk-")


def list_codex_agent_models(*, codex_bin: str = "codex") -> list[dict[str, Any]]:
    """Return visible Codex model descriptors from the local Codex CLI."""
    if shutil.which(codex_bin) is None:
        raise RuntimeError(f"Codex CLI executable {codex_bin!r} was not found on PATH")
    result = subprocess.run(
        [codex_bin, "debug", "models"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    models = payload.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Codex model catalog did not contain a models list")
    visible = [model for model in models if isinstance(model, dict) and model.get("visibility") == "list"]
    return sorted(visible, key=lambda model: int(model.get("priority") or 0), reverse=True)


def print_codex_agent_models(*, codex_bin: str = "codex") -> None:
    """Print local Codex model slugs and display names."""
    for model in list_codex_agent_models(codex_bin=codex_bin):
        slug = model.get("slug")
        if not isinstance(slug, str):
            continue
        display_name = model.get("display_name")
        if isinstance(display_name, str) and display_name != slug:
            print(f"{slug}\t{display_name}")
        else:
            print(slug)


def _failed_codex_trial(
    task: AgentEvalTask,
    evidence_dir: Path,
    exc: Exception,
    *,
    runtime_name: str = "codex_cli",
) -> AgentEvalTrial:
    error_path = evidence_dir / "error.json"
    error_path.write_text(
        json.dumps({"error_type": exc.__class__.__name__, "error": str(exc)}) + "\n", encoding="utf-8"
    )
    return AgentEvalTrial(
        id=f"{task.id}:codex",
        task_id=task.id,
        status=AgentEvalTrialStatus.FAILED,
        output=None,
        evidence=CandidateEvidence(
            descriptors={"error": EvidenceDescriptor(kind="error", format="json", ref=str(error_path))},
            metadata={"runtime": runtime_name, "agent": "codex"},
        ),
        metadata={
            "runtime": runtime_name,
            "agent": "codex",
            "agent_ok": False,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        },
    )


async def _terminate_process(process: Any | None) -> None:
    if process is None or process.returncode is not None:
        return
    process.kill()
    with contextlib.suppress(Exception):
        await process.wait()


def _decode_process_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _safe_path_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip(".-")[:120]
