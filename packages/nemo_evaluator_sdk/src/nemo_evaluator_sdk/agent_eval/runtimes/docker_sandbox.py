# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Docker-backed sandbox runtime for agent-eval attempts."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tarfile
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalTask,
    AgentOutput,
)
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor
from pydantic import BaseModel

DEFAULT_INSTRUCTIONS = (
    "Complete the task inside the sandbox workspace. Inspect the provided task files, "
    "write any durable artifacts under output/, and return a concise final answer."
)
_RUNTIME_NAME = "docker_sandbox"
_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class SandboxSDK:
    """Loaded OpenAI Agents SDK symbols used by the runtime."""

    Runner: Any
    RunConfig: Any
    SandboxRunConfig: Any
    Manifest: Any
    SandboxAgent: Any
    DockerSandboxClient: Any
    DockerSandboxClientOptions: Any
    File: Any
    Dir: Any
    LocalDir: Any
    DEFAULT_PYTHON_SANDBOX_IMAGE: str
    docker_from_env: Callable[[], Any]


def _load_agents_sdk() -> SandboxSDK:
    try:
        from agents import Runner
        from agents.run import RunConfig
        from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
        from agents.sandbox.config import DEFAULT_PYTHON_SANDBOX_IMAGE
        from agents.sandbox.entries import Dir, File, LocalDir
        from agents.sandbox.sandboxes.docker import (
            DockerSandboxClient,
            DockerSandboxClientOptions,
        )
        from docker import from_env as docker_from_env
    except ImportError as exc:
        raise RuntimeError(
            "DockerSandboxAgentRuntime requires `nemo-evaluator-sdk[agent-runtimes]`"
        ) from exc

    return SandboxSDK(
        Runner=Runner,
        RunConfig=RunConfig,
        SandboxRunConfig=SandboxRunConfig,
        Manifest=Manifest,
        SandboxAgent=SandboxAgent,
        DockerSandboxClient=DockerSandboxClient,
        DockerSandboxClientOptions=DockerSandboxClientOptions,
        File=File,
        Dir=Dir,
        LocalDir=LocalDir,
        DEFAULT_PYTHON_SANDBOX_IMAGE=DEFAULT_PYTHON_SANDBOX_IMAGE,
        docker_from_env=docker_from_env,
    )


class DockerSandboxAgentRuntime:
    """Generate agent-eval attempts by running a SandboxAgent in Docker per task."""

    def __init__(
        self,
        *,
        model: str | None = None,
        instructions: str | None = None,
        image: str | None = None,
        work_root: Path | None = None,
        timeout_s: float | None = None,
        agent_factory: Callable[..., Any] | None = None,
        sandbox_client_factory: Callable[[], Any] | None = None,
        runner: Any | None = None,
    ) -> None:
        self._model = model
        self._instructions = instructions or DEFAULT_INSTRUCTIONS
        self._image = image
        self._work_root = work_root
        self._timeout_s = timeout_s
        self._agent_factory = agent_factory
        self._sandbox_client_factory = sandbox_client_factory
        self._runner = runner

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalAttempt]:
        resolved_config = config or AgentEvalRunConfig()
        if resolved_config.run_id is None:
            resolved_config = resolved_config.model_copy(update={"run_id": _new_runtime_run_id()})
        sdk = _load_agents_sdk()
        semaphore = asyncio.Semaphore(resolved_config.parallelism)

        async def run_one(index: int, task: AgentEvalTask) -> AgentEvalAttempt:
            async with semaphore:
                return await self._run_task(index, task, resolved_config, sdk)

        return await asyncio.gather(*(run_one(index, task) for index, task in enumerate(tasks)))

    async def _run_task(
        self,
        index: int,
        task: AgentEvalTask,
        config: AgentEvalRunConfig,
        sdk: SandboxSDK,
    ) -> AgentEvalAttempt:
        evidence_dir = self._evidence_dir(index, task, config)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        prompt = _task_prompt(task)
        manifest = self._build_manifest(task, sdk)
        agent = self._build_agent(manifest, sdk)
        client = self._build_client(sdk)
        sandbox = None

        try:
            sandbox = await client.create(
                manifest=manifest,
                options=sdk.DockerSandboxClientOptions(
                    image=self._image or sdk.DEFAULT_PYTHON_SANDBOX_IMAGE
                ),
            )
            async with sandbox:
                result = await self._run_agent(agent, prompt, sandbox, sdk)
                return await self._completed_attempt(task, result, sandbox, evidence_dir)
        except Exception as exc:
            return self._failed_attempt(task, exc, evidence_dir)
        finally:
            if sandbox is not None:
                await client.delete(sandbox)

    def _build_manifest(self, task: AgentEvalTask, sdk: SandboxSDK) -> Any:
        entries: dict[str, Any] = {
            "instruction.md": sdk.File(content=_task_prompt(task).encode("utf-8")),
            "task.json": sdk.File(content=task.model_dump_json().encode("utf-8")),
            "output": sdk.Dir(),
        }
        workspace_dir = task.inputs.get("workspace_dir")
        if workspace_dir is not None:
            entries["workspace"] = sdk.LocalDir(src=Path(workspace_dir))
        return sdk.Manifest(root="/workspace", entries=entries)

    def _build_agent(self, manifest: Any, sdk: SandboxSDK) -> Any:
        agent_factory = self._agent_factory or sdk.SandboxAgent
        kwargs = {
            "name": "NeMo Agent Eval Docker Sandbox Runtime",
            "instructions": self._instructions,
            "default_manifest": manifest,
        }
        if self._model is not None:
            kwargs["model"] = self._model
        return agent_factory(**kwargs)

    def _build_client(self, sdk: SandboxSDK) -> Any:
        if self._sandbox_client_factory is not None:
            return self._sandbox_client_factory()
        return sdk.DockerSandboxClient(sdk.docker_from_env())

    async def _run_agent(self, agent: Any, prompt: str, sandbox: Any, sdk: SandboxSDK) -> Any:
        runner = self._runner or sdk.Runner
        run = runner.run(
            agent,
            prompt,
            run_config=sdk.RunConfig(sandbox=sdk.SandboxRunConfig(session=sandbox)),
        )
        if self._timeout_s is not None:
            return await asyncio.wait_for(_maybe_await(run), timeout=self._timeout_s)
        return await _maybe_await(run)

    async def _completed_attempt(
        self,
        task: AgentEvalTask,
        result: Any,
        sandbox: Any,
        evidence_dir: Path,
    ) -> AgentEvalAttempt:
        final_output = getattr(result, "final_output", None)
        final_output_text = "" if final_output is None else str(final_output)

        final_output_path = evidence_dir / "final_output.txt"
        run_items_path = evidence_dir / "run_items.json"
        raw_responses_path = evidence_dir / "raw_responses.json"
        workspace_tar_path = evidence_dir / "workspace.tar"
        final_state_dir = evidence_dir / "final_state"

        final_output_path.write_text(final_output_text, encoding="utf-8")
        _write_json(run_items_path, _jsonable(getattr(result, "new_items", [])))
        _write_json(raw_responses_path, _jsonable(getattr(result, "raw_responses", [])))
        await _persist_workspace(sandbox, workspace_tar_path, final_state_dir)

        return AgentEvalAttempt(
            id=f"{task.id}:docker-sandbox",
            task_id=task.id,
            status="completed",
            output=AgentOutput(
                text=final_output_text,
                response={"final_output": final_output_text},
                metadata={
                    "runtime": _RUNTIME_NAME,
                    "evidence_dir": str(evidence_dir),
                },
            ),
            evidence=CandidateEvidence(
                descriptors={
                    "final_state": EvidenceDescriptor(kind="filesystem", ref=str(final_state_dir)),
                    "workspace_archive": EvidenceDescriptor(
                        kind="archive", format="tar", ref=str(workspace_tar_path)
                    ),
                    "run_items": EvidenceDescriptor(
                        kind="run_items", format="json", ref=str(run_items_path)
                    ),
                    "raw_responses": EvidenceDescriptor(
                        kind="raw_responses", format="json", ref=str(raw_responses_path)
                    ),
                    "final_output": EvidenceDescriptor(
                        kind="text", format="txt", ref=str(final_output_path)
                    ),
                },
                metadata={"runtime": _RUNTIME_NAME, "sandbox_backend": "docker"},
            ),
            metadata={"runtime": _RUNTIME_NAME, "generated": True},
        )

    def _failed_attempt(self, task: AgentEvalTask, exc: Exception, evidence_dir: Path) -> AgentEvalAttempt:
        error_path = evidence_dir / "error.json"
        _write_json(
            error_path,
            {
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            },
        )
        return AgentEvalAttempt(
            id=f"{task.id}:docker-sandbox",
            task_id=task.id,
            status="failed",
            output=None,
            evidence=CandidateEvidence(
                descriptors={
                    "error": EvidenceDescriptor(kind="error", format="json", ref=str(error_path)),
                },
                metadata={"runtime": _RUNTIME_NAME, "sandbox_backend": "docker"},
            ),
            metadata={
                "runtime": _RUNTIME_NAME,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            },
        )

    def _evidence_dir(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> Path:
        root = config.output_dir if config.output_dir is not None else self._work_root
        if root is None:
            root = Path(tempfile.gettempdir()) / "nemo-evaluator-agent-runtime"
        run_id = config.run_id or _new_runtime_run_id()
        task_name = _safe_path_name(task.id) or f"task-{index}"
        return Path(root) / "agent-runtime" / run_id / task_name


def _task_prompt(task: AgentEvalTask) -> str:
    return str(task.inputs.get("prompt") or task.inputs.get("instruction") or task.intent)


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def _persist_workspace(sandbox: Any, workspace_tar_path: Path, final_state_dir: Path) -> None:
    archive = await sandbox.persist_workspace()
    try:
        with workspace_tar_path.open("wb") as out:
            shutil.copyfileobj(archive, out)
    finally:
        close = getattr(archive, "close", None)
        if close is not None:
            close()

    _extract_tar_safely(workspace_tar_path, final_state_dir)


def _extract_tar_safely(archive_path: Path, destination_root: Path) -> None:
    if destination_root.exists():
        shutil.rmtree(destination_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:*") as archive:
        for member in archive.getmembers():
            destination = _safe_tar_member_destination(member, destination_root)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"workspace archive contains unsupported member {member.name!r}")

            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"workspace archive member {member.name!r} is not readable")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source, destination.open("wb") as out:
                shutil.copyfileobj(source, out)


def _safe_tar_member_destination(member: tarfile.TarInfo, destination_root: Path) -> Path:
    member_path = Path(member.name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError(f"workspace archive contains unsafe member {member.name!r}")
    if member.issym() or member.islnk():
        raise ValueError(f"workspace archive contains unsupported link member {member.name!r}")

    destination = (destination_root / member_path).resolve()
    resolved_root = destination_root.resolve()
    if destination != resolved_root and resolved_root not in destination.parents:
        raise ValueError(f"workspace archive member {member.name!r} resolves outside destination")
    return destination


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


def _safe_path_name(value: str) -> str:
    sanitized = _SAFE_NAME_PATTERN.sub("-", value).strip(".-")
    return sanitized[:120]


def _new_runtime_run_id() -> str:
    return f"agent-runtime-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
