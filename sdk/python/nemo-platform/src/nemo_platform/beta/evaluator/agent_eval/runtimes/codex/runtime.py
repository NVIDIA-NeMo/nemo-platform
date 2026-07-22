# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Codex-backed agent-eval runtimes."""

# ruff: noqa: I001, T201 - the vendored SDK mirror uses different import-order and print settings.

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.runtimes.docker_sandbox import DockerSandboxAgentRuntime
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_platform.beta.evaluator.agent_eval.workspace_seeds import SEED_FILES_INPUT_KEY, seed_workspace
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence, EvidenceDescriptor

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

        try:
            # The task directory is mounted into Docker, but its private parent is not. Keeping that
            # parent host-owned and 0700 preserves the local confidentiality boundary even when a
            # container is interrupted before its recursive cleanup completes.
            _ensure_private_directory(evidence_dir.parent)
            _ensure_private_directory(evidence_dir)
            _ensure_private_directory(workspace_dir)
        except Exception as exc:
            # The path that failed setup is not safe to use for artifact persistence. In particular,
            # writing through a rejected evidence-directory symlink would escape the private tree.
            return _failed_codex_trial(task, None, exc, runtime_name=self._runtime_name)

        prompt_path = evidence_dir / "prompt.txt"
        task_path = evidence_dir / "task.json"
        stdout_path = evidence_dir / "stdout.jsonl"
        stderr_path = evidence_dir / "stderr.txt"
        final_output_path = evidence_dir / "final_output.txt"

        # Persist the task for debugging, but never the grader-only fields: the docker variant mounts
        # this evidence dir into the sandbox (danger-full-access), so serializing `intent` (desired
        # behavior) or `reference` (held-out ground truth) here would let the agent read them back out
        # of `/evidence/task.json` — the same reward-hacking leak the intent-free prompt closes.
        try:
            _write_private_text(task_path, task.model_dump_json(indent=2, exclude={"intent", "reference"}))
        except Exception as exc:
            return _failed_codex_trial(task, evidence_dir, exc, runtime_name=self._runtime_name)

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
            _write_private_text(prompt_path, prompt)
            process = await self._process_factory(
                *command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if process is None:
                raise RuntimeError("process factory failed to create a process")
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
        artifact_persistence_error: str | None = None
        try:
            _write_private_text(stdout_path, stdout_text)
            _write_private_text(stderr_path, stderr_text)
        except Exception as exc:
            artifact_persistence_error = f"{exc.__class__.__name__}: {exc}"

        permission_cleanup_error: str | None = None
        try:
            self._validate_artifact_permissions(evidence_dir)
        except Exception as exc:
            permission_cleanup_error = f"{exc.__class__.__name__}: {exc}"

        if process.returncode != 0:
            return _failed_codex_trial(
                task,
                evidence_dir,
                RuntimeError(f"codex exec exited with status {process.returncode}: {stderr_text.strip()}"),
                runtime_name=self._runtime_name,
                permission_cleanup_error=permission_cleanup_error,
                artifact_persistence_error=artifact_persistence_error,
            )

        if artifact_persistence_error is not None:
            return _failed_codex_trial(
                task,
                evidence_dir,
                RuntimeError(f"failed to persist Codex evidence: {artifact_persistence_error}"),
                runtime_name=self._runtime_name,
                permission_cleanup_error=permission_cleanup_error,
                artifact_persistence_error=artifact_persistence_error,
            )
        if permission_cleanup_error is not None:
            return _failed_codex_trial(
                task,
                evidence_dir,
                PermissionError(f"Codex evidence permission normalization failed: {permission_cleanup_error}"),
                runtime_name=self._runtime_name,
                permission_cleanup_error=permission_cleanup_error,
            )

        try:
            output_text = _read_private_final_output(final_output_path, fallback=stdout_text)
        except Exception as exc:
            return _failed_codex_trial(task, evidence_dir, exc, runtime_name=self._runtime_name)
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

    def _validate_artifact_permissions(self, evidence_dir: Path) -> None:
        """Validate runtime-specific artifact postconditions after the process exits."""

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
        # Codex intentionally runs as root: the container mounts its auth under /root and coding tasks
        # may need to install tools. Repair the bind-mounted trees before Docker returns so the host can
        # score and persist every artifact the agent created without widening access to other host users.
        # Capture the bind mount's owner as seen inside this container before Codex runs: raw host UID/GID
        # values are not portable across Docker Desktop and rootless user-namespace mappings. Keep Codex
        # failures authoritative; only surface the required chmod status when Codex itself succeeded.
        shell_command = (
            "host_owner=\"$(stat -c '%u:%g' /evidence 2>/dev/null)\" || true; "
            f"{shlex.join(inner_command)}; "
            "codex_status=$?; "
            'if [ -n "$host_owner" ]; then '
            'chown -R "$host_owner" /workspace /evidence 2>/dev/null || true; '
            "fi; "
            "chmod -R u+rwX,go-rwx /workspace /evidence; "
            "permissions_status=$?; "
            'if [ "$codex_status" -ne 0 ]; then exit "$codex_status"; fi; '
            'exit "$permissions_status"'
        )
        return [
            self._docker_bin,
            "run",
            "--rm",
            "-i",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-v",
            f"{self._auth_path.resolve()}:/root/.codex/auth.json:ro",
            "-v",
            f"{workspace_dir.resolve()}:/workspace",
            "-v",
            f"{evidence_dir.resolve()}:/evidence",
            self._image,
            "sh",
            "-lc",
            shell_command,
        ]

    def _validate_artifact_permissions(self, evidence_dir: Path) -> None:
        _validate_private_tree(evidence_dir)


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
    evidence_dir: Path | None,
    exc: Exception,
    *,
    runtime_name: str = "codex_cli",
    permission_cleanup_error: str | None = None,
    artifact_persistence_error: str | None = None,
) -> AgentEvalTrial:
    evidence: CandidateEvidence | None = None
    error_artifact_error: str | None = None
    if evidence_dir is not None:
        error_path = evidence_dir / "error.json"
        try:
            _write_private_text(
                error_path, json.dumps({"error_type": exc.__class__.__name__, "error": str(exc)}) + "\n"
            )
        except Exception as artifact_exc:
            error_artifact_error = f"{artifact_exc.__class__.__name__}: {artifact_exc}"
        else:
            evidence = CandidateEvidence(
                descriptors={"error": EvidenceDescriptor(kind="error", format="json", ref=str(error_path))},
                metadata={"runtime": runtime_name, "agent": "codex"},
            )

    metadata: dict[str, Any] = {
        "runtime": runtime_name,
        "agent": "codex",
        "agent_ok": False,
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }
    if permission_cleanup_error is not None:
        metadata["permission_cleanup_error"] = permission_cleanup_error
    if artifact_persistence_error is not None:
        metadata["artifact_persistence_error"] = artifact_persistence_error
    if error_artifact_error is not None:
        metadata["error_artifact_error"] = error_artifact_error
    return AgentEvalTrial(
        id=f"{task.id}:codex",
        task_id=task.id,
        status=AgentEvalTrialStatus.FAILED,
        output=None,
        evidence=evidence,
        metadata=metadata,
    )


def _ensure_private_directory(path: Path) -> None:
    """Create or repair a host-owned directory without following a leaf symlink."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        path_stat = os.fstat(descriptor)
        if path_stat.st_uid != os.getuid():
            raise PermissionError(f"directory is not owned by the invoking host user: {path}")
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)


def _write_private_text(path: Path, content: str) -> None:
    """Atomically publish a host-created evidence artifact with owner-only access."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        temporary_file = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with temporary_file:
            temporary_file.write(content)
        os.replace(temporary_path, path)
    finally:
        if descriptor != -1:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def _read_private_final_output(path: Path, *, fallback: str) -> str:
    """Read a regular agent-created final output without following it, then republish it privately."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        _write_private_text(path, fallback)
        return fallback

    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PermissionError(f"final output is not a regular file: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8") as output_file:
            descriptor = -1
            output_text = output_file.read()
    finally:
        if descriptor != -1:
            os.close(descriptor)

    _write_private_text(path, output_text)
    return output_text


def _validate_private_tree(root: Path) -> None:
    """Require a host-owned, owner-only tree without following agent-created symlinks."""
    expected_uid = os.getuid()
    pending = [root]
    while pending:
        path = pending.pop()
        path_stat = path.lstat()
        if stat.S_ISLNK(path_stat.st_mode):
            continue
        if path_stat.st_uid != expected_uid:
            raise PermissionError(f"artifact is not owned by the invoking host user: {path}")

        mode = stat.S_IMODE(path_stat.st_mode)
        if mode & 0o077:
            raise PermissionError(f"artifact grants group or other access: {path} ({mode:o})")
        if stat.S_ISDIR(path_stat.st_mode):
            if mode & 0o700 != 0o700:
                raise PermissionError(f"directory is not owner-readable, writable, and traversable: {path} ({mode:o})")
            with os.scandir(path) as entries:
                pending.extend(Path(entry.path) for entry in entries)
        elif stat.S_ISREG(path_stat.st_mode):
            if mode & 0o600 != 0o600:
                raise PermissionError(f"file is not owner-readable and writable: {path} ({mode:o})")
        else:
            raise PermissionError(f"artifact is not a regular file or directory: {path}")


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
