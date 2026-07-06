# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Fabric-backed agent-eval runtime.

``FabricAgentRuntime`` drives an agent harness (Codex, Hermes, ...) through the
NeMo Fabric Python SDK and adapts each normalized Fabric ``RunResult`` into an
:class:`AgentEvalTrial`. The harness is chosen by the supplied Fabric config's
``harness.adapter_id`` (never inferred from a model); an optional ``model`` slug
is applied as a final profile overlay, mirroring Fabric's own Harbor integration.

``nemo_fabric`` is an optional native dependency: its types are imported for
annotations under ``TYPE_CHECKING`` and the package is loaded lazily at runtime,
so this module stays importable without it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.values.evidence import (
    EVIDENCE_FORMAT_ATIF,
    EVIDENCE_TRACE,
    CandidateEvidence,
    EvidenceDescriptor,
)

if TYPE_CHECKING:
    # Annotations use nemo_fabric's real types (single source of truth). nemo_fabric is an optional
    # native package not yet in our locked dependency set, so it is imported for typing only and
    # loaded lazily at runtime (see ``run_tasks``). Drop the ty:ignore once nemo-fabric is a
    # resolvable dependency and the checker can see it.
    from nemo_fabric import (  # ty: ignore[unresolved-import]
        FabricClient,
        FabricConfig,
        FabricProfileConfig,
        RunResult,
    )

DEFAULT_FABRIC_TIMEOUT_S = 600
_RUNTIME_NAME = "fabric"
_MISSING_FABRIC_MSG = "FabricAgentRuntime requires the `nemo-fabric` package (native NeMo Fabric SDK)."
_MISSING_RELAY_MSG = (
    "FabricAgentRuntime trajectory capture requires the `nemo-relay` package "
    "(install `nemo-fabric[relay]`), or set capture_trajectory=False."
)

# Evidence-dir layout for trajectory capture. These subdir names are our own local layout — we create
# them and hand them to Fabric/Relay, so they are not derived from either library.
_RELAY_SUBDIR = "relay"
_ARTIFACTS_SUBDIR = "artifacts"
# Trajectory profile identity + the file-exporter output names we choose (Relay accepts these as inputs).
_TRAJECTORY_PROFILE_NAME = "eval_trajectory"
_ATIF_FILENAME_TEMPLATE = "trajectory-{session_id}.atif.json"
_ATOF_FILENAME = "events.atof.jsonl"
# Fabric telemetry-profile selectors (file exporter, no OTLP endpoint).
_TELEMETRY_PROVIDER = "relay"
_TELEMETRY_MODE = "sdk"
# ``kind`` Fabric stamps on the promoted Relay ATIF artifact; used to surface it as trace evidence.
_ATIF_ARTIFACT_KIND = "atif"


class FabricAgentRuntime:
    """AgentTaskRunner that generates trials by running tasks through NeMo Fabric."""

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        profiles: Sequence[Mapping[str, Any]] | None = None,
        model: str | None = None,
        base_dir: str | Path | None = None,
        work_root: str | Path | None = None,
        timeout_s: int = DEFAULT_FABRIC_TIMEOUT_S,
        capture_trajectory: bool = True,
        runtime_name: str = _RUNTIME_NAME,
    ) -> None:
        self._config = config
        self._profiles = list(profiles or [])
        self._model = model
        self._base_dir = Path(base_dir).expanduser() if base_dir is not None else None
        self._work_root = Path(work_root).expanduser() if work_root is not None else None
        self._timeout_s = timeout_s
        self._capture_trajectory = capture_trajectory
        self._runtime_name = runtime_name

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalTrial]:
        try:
            # nemo_fabric ships a native (pyo3) core and is an optional dependency, so it is imported
            # lazily here rather than at module load.
            from nemo_fabric import FabricClient, FabricConfig, FabricProfileConfig  # ty: ignore[unresolved-import]
        except ImportError as exc:
            raise RuntimeError(_MISSING_FABRIC_MSG) from exc

        resolved_config = config or AgentEvalRunConfig()
        agent_config = FabricConfig.from_mapping(self._config)
        base_profiles = self._build_profiles(FabricProfileConfig)
        semaphore = asyncio.Semaphore(resolved_config.parallelism)

        async with FabricClient() as client:

            async def run_one(index: int, task: AgentEvalTask) -> AgentEvalTrial:
                async with semaphore:
                    return await self._run_task(
                        client, agent_config, base_profiles, FabricProfileConfig, index, task, resolved_config
                    )

            return await asyncio.gather(*(run_one(index, task) for index, task in enumerate(tasks)))

    async def _run_task(
        self,
        client: FabricClient,
        agent_config: FabricConfig,
        base_profiles: list[FabricProfileConfig],
        profile_cls: type[FabricProfileConfig],
        index: int,
        task: AgentEvalTask,
        config: AgentEvalRunConfig,
    ) -> AgentEvalTrial:
        evidence_dir = self._evidence_dir(index, task, config)
        evidence_dir.mkdir(parents=True, exist_ok=True)

        profiles = list(base_profiles)
        if self._capture_trajectory:
            # Enable Relay's ATIF file exporter, writing the trajectory under this task's durable
            # evidence dir; Fabric promotes the resulting file into RunResult.artifacts. Both the
            # Fabric artifact root and the relay output dir must exist and be durable.
            relay_dir = evidence_dir / _RELAY_SUBDIR
            artifacts_dir = evidence_dir / _ARTIFACTS_SUBDIR
            relay_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            profiles.append(self._trajectory_profile(profile_cls, relay_dir=relay_dir, artifacts_dir=artifacts_dir))

        try:
            result = await asyncio.wait_for(
                client.run(
                    agent_config,
                    profiles=profiles,
                    input=_fabric_input(task),
                    request_id=task.id,
                    base_dir=self._base_dir,
                ),
                timeout=self._timeout_s,
            )
        except TimeoutError as exc:
            return self._failed_trial(task, evidence_dir, exc)
        except Exception as exc:  # noqa: BLE001 - a task failure must not abort the whole run
            return self._failed_trial(task, evidence_dir, exc)

        return self._to_trial(task, result, evidence_dir)

    def _to_trial(self, task: AgentEvalTask, result: RunResult, evidence_dir: Path) -> AgentEvalTrial:
        # Persist the full normalized Fabric result so graders (and debugging) can see the raw
        # envelope, and expose it as an evidence descriptor.
        result_path = evidence_dir / "fabric_result.json"
        result_path.write_text(json.dumps(result.to_mapping(), indent=2, default=str), encoding="utf-8")

        base_metadata: dict[str, Any] = {
            "runtime": self._runtime_name,
            "harness": result.harness,
            "adapter_id": result.adapter_id,
            "adapter_kind": result.adapter_kind,
            "invocation_id": result.invocation_id,
            "agent_model": self._model,
        }

        if result.status != "succeeded":
            return self._failed_trial(task, evidence_dir, _result_error(result), extra_metadata=base_metadata)

        return AgentEvalTrial(
            id=f"{task.id}:fabric",
            task_id=task.id,
            status=AgentEvalTrialStatus.COMPLETED,
            output=AgentOutput(
                output_text=_extract_output_text(result.output),
                response=result.output,
                metadata={**base_metadata, "evidence_dir": str(evidence_dir)},
            ),
            evidence=self._evidence(result, result_path),
            metadata={**base_metadata, "generated": True},
        )

    def _evidence(self, result: RunResult, result_path: Path) -> CandidateEvidence:
        descriptors: dict[str, EvidenceDescriptor] = {
            "result": EvidenceDescriptor(kind="json", format="json", ref=str(result_path)),
        }
        for artifact in result.artifacts.artifacts:
            descriptors[artifact.name] = EvidenceDescriptor(
                kind=artifact.kind or "file",
                ref=str(artifact.path),
                metadata={"media_type": artifact.media_type},
            )
            # Surface the Relay ATIF trajectory under the standard trace evidence key so graders
            # that consume a normalized trajectory find it.
            if artifact.kind == _ATIF_ARTIFACT_KIND:
                descriptors[EVIDENCE_TRACE] = EvidenceDescriptor(
                    kind=EVIDENCE_TRACE,
                    format=EVIDENCE_FORMAT_ATIF,
                    ref=str(artifact.path),
                )
        return CandidateEvidence(
            descriptors=descriptors,
            metadata={
                "runtime": self._runtime_name,
                "harness": result.harness,
                "telemetry": [
                    {"provider": ref.provider, "kind": ref.kind, "uri": ref.uri, "trace_id": ref.trace_id}
                    for ref in result.telemetry
                ],
                "events": [{"kind": event.kind, "message": event.message} for event in result.events],
            },
        )

    def _failed_trial(
        self,
        task: AgentEvalTask,
        evidence_dir: Path,
        error: Exception | Mapping[str, Any],
        *,
        extra_metadata: Mapping[str, Any] | None = None,
    ) -> AgentEvalTrial:
        if isinstance(error, Mapping):
            error_type = str(error.get("code") or error.get("stage") or "FabricError")
            error_message = str(error.get("message") or error)
        else:
            error_type = error.__class__.__name__
            error_message = str(error)
        error_path = evidence_dir / "error.json"
        error_path.write_text(json.dumps({"error_type": error_type, "error": error_message}) + "\n", encoding="utf-8")
        return AgentEvalTrial(
            id=f"{task.id}:fabric",
            task_id=task.id,
            status=AgentEvalTrialStatus.FAILED,
            output=None,
            evidence=CandidateEvidence(
                descriptors={"error": EvidenceDescriptor(kind="error", format="json", ref=str(error_path))},
                metadata={"runtime": self._runtime_name},
            ),
            metadata={
                **(dict(extra_metadata) if extra_metadata else {}),
                "runtime": self._runtime_name,
                "error_type": error_type,
                "error": error_message,
            },
        )

    def _build_profiles(self, profile_cls: type[FabricProfileConfig]) -> list[FabricProfileConfig]:
        profiles = [profile_cls.from_mapping(profile) for profile in self._profiles]
        if self._model:
            # Apply the model as a final profile overlay (mirrors nemo_fabric.integrations.harbor).
            provider = self._model.split("/", maxsplit=1)[0] if "/" in self._model else "openai"
            profiles.append(
                profile_cls(
                    name="eval_model",
                    models={"default": {"provider": provider, "model": self._model}},
                )
            )
        return profiles

    def _trajectory_profile(
        self, profile_cls: type[FabricProfileConfig], *, relay_dir: Path, artifacts_dir: Path
    ) -> FabricProfileConfig:
        # Relay ATIF/ATOF file exporter (mode=sdk): the harness emits its trajectory to a local
        # nemo-relay gateway, which writes ``trajectory-*.atif.json`` under ``relay_dir``. No OTLP
        # collector endpoint is involved. Requires the ``nemo-relay`` gateway on PATH in the runtime.
        # The Fabric artifact root is pinned to a durable dir so the promoted trajectory persists.
        #
        # The observability component is built from nemo_relay's own typed config objects so Relay owns
        # its schema (no hand-maintained dict that silently drifts when Relay changes it); imported
        # lazily since nemo-relay, like nemo-fabric, is an optional native dependency. ``schema_version``
        # is omitted — ``FabricProfileConfig`` defaults it.
        try:
            from nemo_relay.observability import (  # ty: ignore[unresolved-import]
                AtifConfig,
                AtofConfig,
                ComponentSpec,
                ObservabilityConfig,
            )
        except ImportError as exc:
            raise RuntimeError(_MISSING_RELAY_MSG) from exc

        relay_dir_str = str(relay_dir)
        artifacts_dir_str = str(artifacts_dir)
        observability = ComponentSpec(
            config=ObservabilityConfig(
                atif=AtifConfig(
                    enabled=True,
                    output_directory=relay_dir_str,
                    filename_template=_ATIF_FILENAME_TEMPLATE,
                    agent_name=self._runtime_name,
                    agent_version="fabric",
                ),
                atof=AtofConfig(
                    enabled=True,
                    output_directory=relay_dir_str,
                    filename=_ATOF_FILENAME,
                    mode="overwrite",
                ),
            )
        )
        return profile_cls.from_mapping(
            {
                "name": _TRAJECTORY_PROFILE_NAME,
                "description": "Capture the agent trajectory as ATIF via the NeMo Relay file exporter.",
                "runtime": {"artifacts": artifacts_dir_str},
                "environment": {"artifacts": artifacts_dir_str},
                "telemetry": {
                    "enabled": True,
                    "provider": _TELEMETRY_PROVIDER,
                    "mode": _TELEMETRY_MODE,
                    "output_dir": relay_dir_str,
                    "config": {"version": 1, "components": [observability.to_dict()]},
                },
            }
        )

    def _evidence_dir(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> Path:
        root = self._work_root
        if root is None:
            root = (config.output_dir or Path.cwd()) / "evidence" / "fabric"
        safe_task_id = _safe_path_name(task.id)
        task_dir = f"{index:06d}-{safe_task_id}" if safe_task_id else f"task-{index:06d}"
        return Path(root) / task_dir


def _fabric_input(task: AgentEvalTask) -> str:
    return f"Task id: {task.id}\nIntent: {task.intent}\nInputs: {task.inputs}\n"


def _extract_output_text(output: object) -> str | None:
    """Pull the user-visible message out of a Fabric ``RunResult.output`` (JSON-shaped).

    Harness outputs vary; adapters commonly nest the final message under ``response`` (the codex-cli
    adapter does). Prefer a string ``response``/``output_text``, else stringify the whole value.
    """
    if output is None:
        return None
    if isinstance(output, str):
        return output
    if isinstance(output, Mapping):
        for key in ("response", "output_text", "text", "message"):
            value = output.get(key)
            if isinstance(value, str):
                return value
    return json.dumps(output, default=str)


def _result_error(result: RunResult) -> Mapping[str, Any]:
    error = result.error
    if error is None:
        return {"code": result.status, "message": "Fabric run did not succeed"}
    return {"stage": error.stage, "code": error.code, "message": error.message}


def _safe_path_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip(".-")[:120]
