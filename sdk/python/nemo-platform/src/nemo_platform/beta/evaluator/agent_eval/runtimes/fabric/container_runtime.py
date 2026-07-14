# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Containerized NeMo Fabric agent-eval runtime.

``FabricContainerRuntime`` is the sandboxed sibling of
:class:`~nemo_platform.beta.evaluator.agent_eval.runtimes.fabric.runtime.FabricAgentRuntime`: instead of
running the Fabric harness on the host filesystem, it runs it **inside a sandbox** (Docker now,
Kubernetes/agent-sandbox later) through the provider-neutral
:class:`~nemo_platform.beta.evaluator.agent_eval.runtimes.sandbox.api.AsyncSandbox` seam.

Per task it:

1. seeds ``/in`` with the Fabric agent config, profiles, and framed input, plus the task's workspace
   seed files;
2. execs Fabric's own CLI (``fabric run``), which writes a normalized ``RunResult`` to stdout and the
   workspace + Relay ATIF trajectory under a fixed ``/out`` layout;
3. downloads ``/out`` across the boundary into the durable per-task evidence dir; and
4. maps it into the shared :class:`CandidateEvidence` contract the eval metrics consume — ``result``
   (json), ``trace`` (ATIF), plus ``workspace`` (filesystem) and ``logs`` — so the workspace-file,
   held-out ``run_verifier``, and trajectory metrics score container trials with no metric changes.
   (``FabricAgentRuntime`` surfaces ``workspace``/``logs`` only when Fabric promotes them as artifacts;
   the container always captures them from the ``/out`` tree, so its evidence is a superset.)

Relay writes ATIF **inside the image** (no host gateway), which removes the bare-``python3`` /
``tomli_w`` adapter-interpreter problem the host runtime has to work around.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from nemo_platform.beta.evaluator.agent_eval.runtimes.fabric import _common
from nemo_platform.beta.evaluator.agent_eval.runtimes.fabric.image import ensure_fabric_image
from nemo_platform.beta.evaluator.agent_eval.runtimes.sandbox.api import AsyncSandbox
from nemo_platform.beta.evaluator.agent_eval.runtimes.sandbox.base import SandboxExecResult, SandboxProvider, SandboxSpec
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_platform.beta.evaluator.agent_eval.workspace_seeds import SEED_FILES_INPUT_KEY, seed_workspace
from nemo_platform.beta.evaluator.resolver_protocols import SecretResolver
from nemo_platform.beta.evaluator.resolvers import LocalSecretResolver
from nemo_platform.beta.evaluator.values.common import SecretRef
from nemo_platform.beta.evaluator.values.evidence import (
    EVIDENCE_FORMAT_ATIF,
    EVIDENCE_LOGS,
    EVIDENCE_TRACE,
    CandidateEvidence,
    EvidenceDescriptor,
)
from pydantic import JsonValue

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # nemo_fabric is an optional native dep (see FabricAgentRuntime); imported for typing only. Configs
    # are consumed structurally via ``to_mapping()`` at runtime, so this module stays importable without it.
    from nemo_fabric import FabricConfig, FabricProfileConfig  # ty: ignore[unresolved-import]

# Default per-task exec budget. Timeout is really task-specific (see AALGO-323 to move it onto
# AgentEvalTask); until then it is an internal default rather than a runtime-construction knob.
DEFAULT_FABRIC_TIMEOUT_S = 600
_RUNTIME_NAME = "fabric_container"

# Fixed in-container layout. The runtime seeds ``/in`` (agent config, profiles, input), execs Fabric's
# CLI, and reads the produced ``/out`` subtree back across the boundary.
_IN_DIR = "/in"
_OUT_DIR = "/out"
_WORKSPACE_DIR = f"{_OUT_DIR}/workspace"
_RELAY_DIR = f"{_OUT_DIR}/relay"
_ARTIFACTS_DIR = f"{_OUT_DIR}/artifacts"
_LOGS_DIR = f"{_OUT_DIR}/logs"
_RESULT_PATH = f"{_OUT_DIR}/fabric_result.json"
_FABRIC_STDERR = f"{_LOGS_DIR}/fabric-stderr.txt"
_AGENT_PATH = f"{_IN_DIR}/agent.yaml"
_INPUT_PATH = f"{_IN_DIR}/input.txt"
_WORKSPACE_PROFILE_NAME = "eval_workspace"


class FabricContainerRuntime:
    """AgentTaskRunner that generates trials by running Fabric tasks inside a sandbox."""

    def __init__(
        self,
        config: FabricConfig | Mapping[str, Any],
        *,
        provider: SandboxProvider,
        profiles: Sequence[FabricProfileConfig | Mapping[str, Any]] = (),
        secrets: Mapping[str, SecretRef] = {},
    ) -> None:
        # The Fabric agent is fully described by its ``FabricConfig`` (harness + model + runtime); it is
        # consumed structurally as a mapping to cross the sandbox boundary as JSON.
        self._config = _to_mapping(config)
        self._profiles = [_to_mapping(profile) for profile in profiles]
        self._provider = provider
        # ``secrets`` maps the env-var name a Fabric harness reads its credential from (declared by the
        # adapter's ``requirements.env``) to a SecretRef. The runner only *declares* them; the resolver
        # is owned by the orchestrator (see ``resolve_secrets``), mirroring ``MetricWithSecrets``.
        self._secrets = dict(secrets)
        self._resolved_env: dict[str, str] = {}
        self._secrets_resolved = False
        # Provisioned opaquely on first run (build-if-missing from the config's harness).
        self._image: str | None = None

    async def resolve_secrets(self, secret_resolver: SecretResolver) -> None:
        """Resolve declared ``SecretRef``\\ s to values, keyed by the env var each harness reads.

        Mirrors ``MetricWithSecrets.resolve_secrets``: the resolver is owned by the orchestrator (the
        AgentEvaluator / execution backend), not the runner. Call before :meth:`run_tasks`; a standalone
        ``run_tasks`` falls back to local env resolution when this was not called.
        """
        env: dict[str, str] = {}
        for env_var, secret_ref in self._secrets.items():
            value = await secret_resolver.resolve_secret(secret_ref)
            if value is None:
                raise ValueError(f"could not resolve secret {secret_ref.root!r} for env var {env_var!r}")
            env[env_var] = value
        self._resolved_env = env
        self._secrets_resolved = True

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalTrial]:
        resolved_config = config or AgentEvalRunConfig()
        semaphore = asyncio.Semaphore(resolved_config.parallelism)

        async def run_one(index: int, task: AgentEvalTask) -> AgentEvalTrial:
            async with semaphore:
                logger.info("running task", extra={"index": index + 1, "task_id": task.id})
                result = await self._run_task(index, task, resolved_config)
                logger.info("task completed", extra={"index": index + 1, "task_id": task.id})
                return result

        try:
            # Provision the harness-agnostic Fabric image once, build-if-missing (a first build compiles
            # nemo-fabric — minutes); keep the blocking build off the shared event loop. Inside the guard
            # so the provider is disposed even if provisioning or secret resolution raises.
            self._image = await asyncio.to_thread(ensure_fabric_image)
            if self._secrets and not self._secrets_resolved:
                # No orchestrator resolved our secrets (standalone run) — fall back to local env resolution.
                await self.resolve_secrets(LocalSecretResolver())
            return await asyncio.gather(*(run_one(index, task) for index, task in enumerate(tasks)))
        finally:
            # Each sandbox tears itself down; the provider is shared across the batch, so its
            # process-wide resources are disposed once here, when the batch completes.
            await self._provider.aclose()

    async def _run_task(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> AgentEvalTrial:
        evidence_dir = self._evidence_dir(index, task, config)
        out_dir = evidence_dir / "out"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # The whole per-task flow — framing input, seeding, exec, download, and parsing the result — is
        # guarded so any failure (bad seed, sandbox crash, unreadable result) fails only this task's
        # trial rather than aborting the gathered batch.
        try:
            seed_files, profile_paths = self._seed_files(task)
            spec = SandboxSpec(
                image=self._image, workdir=_WORKSPACE_DIR, env=dict(self._resolved_env), files=seed_files
            )
            async with AsyncSandbox(self._provider, spec) as sandbox:
                await sandbox.start()
                await self._seed_workspace(sandbox, task)
                result = await sandbox.exec(self._fabric_command(profile_paths), timeout_s=DEFAULT_FABRIC_TIMEOUT_S)
                await sandbox.download_dir(_OUT_DIR, out_dir)
            return self._to_trial(task, out_dir, evidence_dir, result)
        except Exception as exc:  # noqa: BLE001 - a task failure must not abort the whole run
            return self._failed_trial(task, evidence_dir, exc)

    def _fabric_command(self, profile_paths: Sequence[str]) -> str:
        """The ``fabric run`` invocation: pre-create the /out dirs Fabric chdirs into, run, capture stdout."""
        profiles = " ".join(f"--profile {shlex.quote(path)}" for path in profile_paths)
        run = f"fabric run {shlex.quote(_AGENT_PATH)} {profiles} --input-file {shlex.quote(_INPUT_PATH)}"
        return (
            f"mkdir -p {_WORKSPACE_DIR} {_RELAY_DIR} {_ARTIFACTS_DIR} {_LOGS_DIR} && "
            f"{run} > {shlex.quote(_RESULT_PATH)} 2> {shlex.quote(_FABRIC_STDERR)}"
        )

    def _seed_files(self, task: AgentEvalTask) -> tuple[dict[str, str], list[str]]:
        """Return (files to seed into /in, profile paths for --profile). Configs are written as JSON,
        which the Fabric CLI parses as YAML. Base profiles are followed by the per-task workspace overlay
        and the trajectory profile (built as plain dicts — no host nemo_relay dependency)."""
        files: dict[str, str] = {
            _AGENT_PATH: json.dumps(self._config),
            _INPUT_PATH: task.agent_prompt(),
        }
        profile_paths: list[str] = []
        profiles = [*self._profiles, self._workspace_profile(), self._trajectory_profile()]
        for index, profile in enumerate(profiles):
            path = f"{_IN_DIR}/profile-{index}.yaml"
            files[path] = json.dumps(profile)
            profile_paths.append(path)
        return files, profile_paths

    @staticmethod
    def _workspace_profile() -> dict[str, Any]:
        # Pin the harness working directory to the retrievable workspace; ``provider`` is required by the
        # native planner (it does not inject the Python default into a raw overlay).
        return {"name": _WORKSPACE_PROFILE_NAME, "environment": {"provider": "local", "workspace": _WORKSPACE_DIR}}

    @staticmethod
    def _trajectory_profile() -> dict[str, Any]:
        # Relay ATIF/ATOF file exporter (sdk mode). The telemetry block is built from nemo_relay's typed
        # config via the shared helper (single source of truth with the host runtime); ``provider:local``
        # is required by the native planner in the container (it does not inject the Python default).
        return {
            "name": _common.TRAJECTORY_PROFILE_NAME,
            "runtime": {"artifacts": _ARTIFACTS_DIR},
            "environment": {"provider": "local", "artifacts": _ARTIFACTS_DIR},
            "telemetry": _common.trajectory_telemetry(
                relay_dir=_RELAY_DIR, agent_name=_RUNTIME_NAME, agent_version=_RUNTIME_NAME
            ),
        }

    async def _seed_workspace(self, sandbox: AsyncSandbox, task: AgentEvalTask) -> None:
        seeds = task.inputs.get(SEED_FILES_INPUT_KEY)
        if not seeds:
            return
        # Transient host-side staging (a tmpdir, not part of the evidence bundle): seed with the SDK
        # handlers, then upload across the boundary. seed_workspace is synchronous and a handler may do
        # blocking I/O (e.g. a fileset download), so run it off the event loop shared by concurrent tasks.
        with tempfile.TemporaryDirectory(prefix="nemo-fabric-seed-") as staging_dir:
            staging = Path(staging_dir)
            await asyncio.to_thread(seed_workspace, staging, seeds)
            await sandbox.upload_dir(staging, _WORKSPACE_DIR)

    def _to_trial(
        self, task: AgentEvalTask, out_dir: Path, evidence_dir: Path, result: SandboxExecResult
    ) -> AgentEvalTrial:
        base_metadata: dict[str, object] = {
            "runtime": _RUNTIME_NAME,
            "image": self._image,
            "sandbox_provider": self._provider.name,
        }

        # Gate on the exec outcome first: a timed-out or non-zero ``fabric run`` is untrustworthy even
        # when a stale/partial fabric_result.json is left behind (the shell ``>`` redirect truncates the
        # file regardless), so never grade such a run off that file.
        if result.error_type or result.return_code != 0:
            stderr = _read_text(out_dir / "logs" / "fabric-stderr.txt") or (result.stderr or "")
            detail = stderr.strip() or result.error_type or f"exit code {result.return_code}"
            return self._failed_trial(
                task, evidence_dir, RuntimeError(f"fabric run failed: {detail}"), extra_metadata=base_metadata
            )

        result_path = out_dir / "fabric_result.json"
        result_payload = _read_json(result_path)
        # `fabric run` writes a normalized RunResult object (a failed harness run still produces one, with
        # status != "succeeded"). A missing, non-object, or unreadable payload means no usable result.
        if not isinstance(result_payload, Mapping):
            stderr = _read_text(out_dir / "logs" / "fabric-stderr.txt") or (result.stderr or "")
            return self._failed_trial(
                task,
                evidence_dir,
                RuntimeError(f"fabric run produced no usable result: {stderr.strip()}"),
                extra_metadata=base_metadata,
            )

        status = str(result_payload.get("status"))
        if status != "succeeded":
            return self._failed_trial(task, evidence_dir, _result_error(result_payload), extra_metadata=base_metadata)

        return AgentEvalTrial(
            id=f"{task.id}:fabric_container",
            task_id=task.id,
            status=AgentEvalTrialStatus.COMPLETED,
            output=AgentOutput(
                # ``response`` is the RunResult *output* payload (matching the host FabricAgentRuntime),
                # not the whole normalized envelope, so metrics reading ``sample.response`` see one shape.
                output_text=_common.extract_output_text(result_payload.get("output")),
                response=cast(JsonValue, result_payload.get("output")),
                metadata={**base_metadata, "evidence_dir": str(evidence_dir)},
            ),
            evidence=self._evidence(out_dir, result_path),
            metadata={**base_metadata, "generated": True, "agent_ok": True},
        )

    def _evidence(self, out_dir: Path, result_path: Path) -> CandidateEvidence:
        descriptors: dict[str, EvidenceDescriptor] = {
            "result": EvidenceDescriptor(kind="json", format="json", ref=str(result_path)),
        }
        workspace_dir = out_dir / "workspace"
        if workspace_dir.is_dir():
            descriptors["workspace"] = EvidenceDescriptor(kind="filesystem", ref=str(workspace_dir))
        logs_dir = out_dir / "logs"
        if logs_dir.is_dir():
            descriptors[EVIDENCE_LOGS] = EvidenceDescriptor(kind="logs", ref=str(logs_dir))
        atif = _find_atif(out_dir / "relay")
        if atif is not None:
            descriptors[EVIDENCE_TRACE] = EvidenceDescriptor(
                kind=EVIDENCE_TRACE, format=EVIDENCE_FORMAT_ATIF, ref=str(atif)
            )
        return CandidateEvidence(
            descriptors=descriptors,
            metadata={"runtime": _RUNTIME_NAME, "sandbox_provider": self._provider.name, "image": self._image},
        )

    def _failed_trial(
        self,
        task: AgentEvalTask,
        evidence_dir: Path,
        error: Exception | Mapping[str, object],
        *,
        extra_metadata: Mapping[str, object] | None = None,
    ) -> AgentEvalTrial:
        # Bind this runtime's name + trial-id suffix to the shared FAILED-trial builder.
        return _common.build_failed_trial(
            task,
            evidence_dir,
            error,
            runtime_name=_RUNTIME_NAME,
            trial_id_suffix=_RUNTIME_NAME,
            extra_metadata=extra_metadata,
        )

    def _evidence_dir(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> Path:
        # Evidence lands under the run's output dir (like every other runtime); the container's own
        # working state lives at /out inside the sandbox and is downloaded here.
        root = (config.output_dir or Path.cwd()) / "evidence" / "fabric_container"
        return root / _common.task_subdir_name(index, task.id)


def _to_mapping(config: FabricConfig | Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a typed Fabric config/profile or a plain mapping to a plain dict for JSON transport."""
    # A typed Fabric config/profile exposes ``to_mapping()``; a plain mapping is used as-is. Both are
    # str-keyed at runtime, but the getattr + optional (unresolved) ``FabricConfig`` type defeat static
    # narrowing, so cast the known-good source before building the dict.
    to_mapping = getattr(config, "to_mapping", None)
    source = to_mapping() if callable(to_mapping) else config
    return dict(cast(Mapping[str, Any], source))


def _find_atif(relay_dir: Path) -> Path | None:
    # Relay nests the trajectory under a per-run subdir (relay/runtime-<id>/trajectory-*.atif.json),
    # so search recursively rather than only relay's direct children.
    if not relay_dir.is_dir():
        return None
    matches = sorted(relay_dir.rglob("trajectory-*.atif.json"))
    return matches[0] if matches else None


def _read_json(path: Path) -> JsonValue | None:
    if not path.is_file():
        return None
    # A truncated/binary/unreadable result (e.g. a crashed CLI that left partial or non-UTF-8 bytes)
    # is treated as "no usable result" rather than propagating and aborting the batch.
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except (UnicodeDecodeError, OSError):
        return ""


def _result_error(payload: object) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        return {"code": "FabricError", "message": "Fabric run did not produce a result"}
    error = payload.get("error")
    if isinstance(error, Mapping):
        return {"stage": error.get("stage"), "code": error.get("code"), "message": error.get("message")}
    return {"code": payload.get("status"), "message": "Fabric run did not succeed"}
