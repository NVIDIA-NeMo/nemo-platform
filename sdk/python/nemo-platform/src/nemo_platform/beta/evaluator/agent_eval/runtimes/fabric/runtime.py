# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Fabric-backed agent-eval runtime.

``FabricAgentRuntime`` drives an agent harness (Codex, Hermes, ...) through the
NeMo Fabric Python SDK and adapts each normalized Fabric ``RunResult`` into an
:class:`AgentEvalTrial`. The harness is chosen by the supplied Fabric config's
``harness.adapter_id`` (never inferred from a model); an optional ``model`` slug
is applied as the config's default model, mirroring Fabric's own Harbor integration.

Per-task settings (workspace, model, trajectory capture) are composed directly onto
a copy of the supplied config via the SDK's config helpers (``model_copy`` +
``enable_relay`` + ``environment``), rather than layered as profile overlays.

Every task runs in its own fresh workspace: the runtime seeds it from
``inputs['files']`` (a no-op when there are none), runs the harness in it (via
``environment.workspace``), and exposes its final file tree as ``workspace``
filesystem evidence, so workspace-reading metrics score a Fabric trial alongside
the ATIF trajectory. Any ``environment.workspace`` set in the supplied config is
overridden per task.

``nemo_fabric`` is an optional native dependency: its types are imported for
annotations under ``TYPE_CHECKING`` and the package is loaded lazily at runtime,
so this module stays importable without it.
"""

from __future__ import annotations

import asyncio
import copy
import json
import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from nemo_platform.beta.evaluator.agent_eval.runtimes.fabric.skills import (
    SKILL_MODE_CODEX_SKILLS_DIR,
    AgentSkill,
    SkillProvenance,
    install_skill,
    resolve_skill_mode,
)
from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_platform.beta.evaluator.agent_eval.workspace_seeds import SEED_FILES_INPUT_KEY, seed_workspace
from nemo_platform.beta.evaluator.values.evidence import (
    EVIDENCE_FORMAT_ATIF,
    EVIDENCE_TRACE,
    CandidateEvidence,
    EvidenceDescriptor,
)
from pydantic import JsonValue

if TYPE_CHECKING:
    # Annotations use nemo_fabric's real types (single source of truth). nemo_fabric is an optional
    # native package not yet in our locked dependency set, so it is imported for typing only and
    # loaded lazily at runtime (see ``run_tasks``). Drop the ty:ignore once nemo-fabric is a
    # resolvable dependency and the checker can see it.
    from nemo_fabric import (  # ty: ignore[unresolved-import]
        Fabric,
        FabricConfig,
        FabricProfileConfig,
        RunOutput,
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
# Per-task workspace: where seed files are staged and where the harness reads/writes. We
# create it, point Fabric's ``environment.workspace`` at it, and expose it as ``workspace`` evidence.
_WORKSPACE_SUBDIR = "workspace"
# Per-task skill staging dir (native injection): the skill's files are resolved here and a per-task
# ``skills`` profile overlay points Fabric at it. For codex self-injection the skill lands in the
# workspace instead (no overlay).
_SKILL_SUBDIR = "skill"
# Sentinel skill path attached only to probe Fabric's capability planner for the selected adapter's
# skills routing (see ``_resolve_skill_mode``). Never staged and need not exist on disk — the planner
# just reports how it would route a skill for this adapter.
_SKILL_PROBE_PATH = "nemo-eval-skill-capability-probe"
# Evidence key + descriptor kind for the staged workspace, consumed by the
# workspace-reading metrics.
_WORKSPACE_EVIDENCE_KEY = "workspace"
_WORKSPACE_EVIDENCE_KIND = "filesystem"
# File-exporter output names we choose for the Relay ATIF/ATOF trajectory (Relay accepts these as inputs).
_ATIF_FILENAME_TEMPLATE = "trajectory-{session_id}.atif.json"
_ATOF_FILENAME = "events.atof.jsonl"
# ``kind`` Fabric stamps on the promoted Relay ATIF artifact; used to surface it as trace evidence.
_ATIF_ARTIFACT_KIND = "atif"
# Names for the trailing overlays that re-assert the evaluator-owned per-task settings (see
# ``_eval_lock_profiles``): Fabric applies caller profiles over the config, so these must trail them.
_WORKSPACE_PROFILE_NAME = "eval_workspace"
_MODEL_PROFILE_NAME = "eval_model"
_ARTIFACTS_PROFILE_NAME = "eval_artifacts"


class FabricAgentRuntime:
    """AgentTaskRunner that generates trials by running tasks through NeMo Fabric.

    The harness is selected entirely by ``config["harness"]["adapter_id"]``. Across harnesses the
    config shape differs mainly in that ``adapter_id``, ``runtime.transport``, and any harness-specific
    ``harness.settings`` — e.g. Codex runs as a subprocess (``transport="cli"``) while the Hermes SDK
    harness runs in-library (``transport="library"``). See
    ``examples/fabric_harness_runtimes.py`` for full Codex-CLI and Hermes-SDK config examples.
    """

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
        skill: AgentSkill | None = None,
    ) -> None:
        self._config = config
        self._profiles = list(profiles or [])
        self._model = model
        self._base_dir = Path(base_dir).expanduser() if base_dir is not None else None
        self._work_root = Path(work_root).expanduser() if work_root is not None else None
        self._timeout_s = timeout_s
        self._capture_trajectory = capture_trajectory
        self._runtime_name = runtime_name
        self._skill = skill

    def with_skill(self, skill: AgentSkill | None) -> FabricAgentRuntime:
        """Return a copy of this runtime with the skill replaced; ``self`` is not modified.

        Lets an A/B eval run the same taskset with and without a skill by deriving both runtimes from
        one configured instance (baseline = ``with_skill(None)``, treated = ``with_skill(the_skill)``),
        so they differ in exactly the skill and nothing else. A shallow copy suffices — the shared
        fields are immutable config/paths.
        """
        clone = copy.copy(self)
        clone._skill = skill
        return clone

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> Sequence[AgentEvalTrial]:
        try:
            # nemo_fabric ships a native (pyo3) core and is an optional dependency, so it is imported
            # lazily here rather than at module load.
            from nemo_fabric import Fabric, FabricConfig, FabricProfileConfig  # ty: ignore[unresolved-import]
        except ImportError as exc:
            raise RuntimeError(_MISSING_FABRIC_MSG) from exc

        resolved_config = config or AgentEvalRunConfig()
        # Assign a run id once per run so two runs (e.g. an A/B baseline vs. skilled variant) written
        # under the same work_root/output_dir land in distinct, non-colliding evidence trees. Callers
        # that set run_id keep their identifier.
        if resolved_config.run_id is None:
            resolved_config = resolved_config.model_copy(update={"run_id": _new_run_id()})
        agent_config = FabricConfig.from_mapping(self._config)
        # Fail fast (once) if trajectory capture is requested but the nemo-relay gateway isn't
        # importable, rather than failing every task the same way inside the per-task guard.
        if self._capture_trajectory:
            try:
                import nemo_relay.observability  # noqa: F401  # ty: ignore[unresolved-import]
            except ImportError as exc:
                raise RuntimeError(_MISSING_RELAY_MSG) from exc
        # Caller-supplied profile overlays pass through as-is; this runtime's per-task workspace, model,
        # and trajectory settings are composed directly onto a copy of the config (config-first), not
        # layered as profiles.
        base_profiles = [FabricProfileConfig.from_mapping(profile) for profile in self._profiles]

        # ``Fabric`` (formerly ``FabricClient``) is a lightweight, reusable facade — not a lifecycle
        # context manager — so it is created once and reused across tasks with no cleanup.
        client = Fabric()

        # Resolve once how a skill would reach this harness (the adapter is constant across tasks) by
        # asking Fabric's own capability planner, so any adapter that declares native skills support — ours
        # or an end-user's — is picked up automatically instead of via a hardcoded allow-list. Fail fast
        # rather than silently run a skill-free trial mislabeled as "with skill", which would corrupt an
        # A/B comparison. Only touched when a skill is set, so the no-skill path is unaffected.
        skill_mode: str | None = None
        if self._skill is not None:
            skill_mode = self._resolve_skill_mode(client, agent_config, base_profiles)
            if skill_mode is None:
                adapter_id = agent_config.harness.adapter_id
                raise RuntimeError(
                    f"FabricAgentRuntime received a skill but adapter {adapter_id!r} has no known "
                    "skill-injection strategy: Fabric does not route skills to it natively and it is not a "
                    "codex harness. Use a skills-native or codex harness, or drop the skill."
                )

        semaphore = asyncio.Semaphore(resolved_config.parallelism)

        async def run_one(index: int, task: AgentEvalTask) -> AgentEvalTrial:
            async with semaphore:
                return await self._run_task(
                    client, agent_config, base_profiles, index, task, resolved_config, skill_mode
                )

        return await asyncio.gather(*(run_one(index, task) for index, task in enumerate(tasks)))

    def _resolve_skill_mode(
        self,
        client: Fabric,
        agent_config: FabricConfig,
        base_profiles: list[FabricProfileConfig],
    ) -> str | None:
        """Ask Fabric how a skill would reach the selected harness, or ``None`` if it can't.

        Probes Fabric's capability planner: plan a copy of the config with a sentinel skill path attached
        (it need not exist on disk) and read how the adapter routes skills. Querying the authoritative
        source at runtime means adapters that declare native skills support — ours or an end-user's — are
        detected without a hardcoded list. See :func:`~...skills.resolve_skill_mode`.
        """
        probe_config = agent_config.model_copy(deep=True)
        probe_config.add_skill_path(_SKILL_PROBE_PATH)
        plan = client.plan(probe_config, profiles=base_profiles, base_dir=self._base_dir)
        return resolve_skill_mode(capability_plan=plan.capability_plan, harness=plan.adapter.harness)

    def _existing_skill_paths(self) -> list[str]:
        """Skill paths the base config/profiles already declare (union, order-preserved).

        Fabric applies profile ``skills.paths`` last-wins, so the native skill overlay has to re-list
        these alongside the evaluated skill or the treated arm would silently drop them (see
        ``install_skill``). Read from the raw config/profile mappings the runtime was given, so it covers
        both config- and profile-declared skills without a Fabric round-trip.
        """
        paths: list[str] = []
        for section in (self._config, *self._profiles):
            skills = section.get("skills") if isinstance(section, Mapping) else None
            declared = skills.get("paths") if isinstance(skills, Mapping) else None
            for path in declared or []:
                if isinstance(path, str) and path not in paths:
                    paths.append(path)
        return paths

    async def _run_task(
        self,
        client: Fabric,
        agent_config: FabricConfig,
        base_profiles: list[FabricProfileConfig],
        index: int,
        task: AgentEvalTask,
        config: AgentEvalRunConfig,
        skill_mode: str | None,
    ) -> AgentEvalTrial:
        # nemo_fabric is already imported+validated in ``run_tasks``; this is a cached sys.modules
        # lookup, not a re-load, so the types are used where they're constructed instead of threaded down.
        from nemo_fabric import FabricProfileConfig, RunRequest  # ty: ignore[unresolved-import]

        evidence_dir = self._evidence_dir(index, task, config)
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Every task runs in its own fresh workspace: seed any ``inputs['files']`` into it (a no-op when
        # there are none), point the harness at it, and expose it as ``workspace`` filesystem evidence —
        # a uniform per-task dir that maps cleanly onto a per-task container volume later. Seeding runs
        # inside the guarded block so a bad seed (a path escaping the workspace, an unresolvable fileset)
        # fails just this task, not the whole run; it is synchronous and may block (a fileset handler
        # downloads), so it is offloaded off the shared event loop.
        workspace_dir = evidence_dir / _WORKSPACE_SUBDIR
        workspace_dir.mkdir(parents=True, exist_ok=True)
        skill_provenance: SkillProvenance | None = None
        try:
            # Stage seed files into the workspace for their on-disk side effect; the prompt is the task
            # instruction only, so the returned paths are unused.
            await asyncio.to_thread(seed_workspace, workspace_dir, task.inputs.get(SEED_FILES_INPUT_KEY))

            # Inject the skill (if any) for this task. A native harness gets a per-task ``skills`` profile
            # overlay; codex self-injection stages the bundle into the workspace and emits no overlay.
            # Provenance is stamped on the trial for the A/B diff. Blocking file I/O, off the event loop.
            skill_profiles: list[FabricProfileConfig] = []
            if self._skill is not None and skill_mode is not None:
                installation = await asyncio.to_thread(
                    install_skill,
                    skill=self._skill,
                    adapter_id=agent_config.harness.adapter_id,
                    mode=skill_mode,
                    workspace_dir=workspace_dir,
                    skill_stage_dir=(evidence_dir / _SKILL_SUBDIR).resolve(),
                    existing_skill_paths=self._existing_skill_paths(),
                )
                skill_provenance = installation.provenance
                skill_profiles = [FabricProfileConfig.from_mapping(p) for p in installation.profiles]

            task_config = self._compose_config(agent_config, evidence_dir, workspace_dir)
            # Caller ``base_profiles`` are applied by Fabric over the config; the evaluator-owned
            # settings are re-asserted as trailing overlays so they win over any caller profile.
            lock_profiles = self._eval_lock_profiles(
                FabricProfileConfig, workspace_dir=workspace_dir, evidence_dir=evidence_dir
            )

            result = await asyncio.wait_for(
                # ``Fabric.run`` folds the per-invocation input + request id into a ``RunRequest``.
                client.run(
                    task_config,
                    # Caller profiles, then the native skill overlay, then the evaluator lock overlays;
                    # the lock overlays trail so the per-task workspace/model/artifacts stay authoritative.
                    profiles=[*base_profiles, *skill_profiles, *lock_profiles],
                    base_dir=self._base_dir,
                    request=RunRequest(input=task.agent_prompt(), request_id=task.id),
                ),
                timeout=self._timeout_s,
            )
        except TimeoutError as exc:
            return self._failed_trial(task, evidence_dir, exc, extra_metadata={"skill": skill_provenance})
        except Exception as exc:  # noqa: BLE001 - a task failure must not abort the whole run
            return self._failed_trial(task, evidence_dir, exc, extra_metadata={"skill": skill_provenance})

        # Codex self-injection staged the bundle *inside* the workspace so the harness could discover it.
        # Now that the run is done (and captured in the trajectory), remove it before the workspace is
        # exposed as filesystem evidence — otherwise the injected files read as agent output and skew
        # workspace-reading metrics (a treated run with no agent-created files would look non-empty).
        if skill_mode == SKILL_MODE_CODEX_SKILLS_DIR and skill_provenance is not None:
            await asyncio.to_thread(_remove_injected_bundle, workspace_dir, skill_provenance["location"])
        return self._to_trial(task, result, evidence_dir, workspace_dir, skill_provenance=skill_provenance)

    def _to_trial(
        self,
        task: AgentEvalTask,
        result: RunResult,
        evidence_dir: Path,
        workspace_dir: Path,
        *,
        skill_provenance: SkillProvenance | None = None,
    ) -> AgentEvalTrial:
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
            # Skill provenance (name + content hash + injection mode) for the A/B diff; None baseline.
            "skill": skill_provenance,
        }

        if result.status != "succeeded":
            return self._failed_trial(task, evidence_dir, _result_error(result), extra_metadata=base_metadata)

        # Fabric wraps the output in a ``RunOutput`` mapping (RunOutput response contract, #52),
        # which is not itself a JSON value; normalize it to a plain mapping so it round-trips through the
        # trial's ``JsonValue``-typed response.
        output = _normalize_output(result.output)
        return AgentEvalTrial(
            id=f"{task.id}:fabric",
            task_id=task.id,
            status=AgentEvalTrialStatus.COMPLETED,
            output=AgentOutput(
                output_text=_extract_output_text(output),
                response=output,
                metadata={**base_metadata, "evidence_dir": str(evidence_dir)},
            ),
            evidence=self._evidence(result, result_path, workspace_dir),
            # AgentPhaseSuccessMetric reads agent_ok to score whether the agent phase finished cleanly
            # (an explicit bool, not just trial status).
            metadata={**base_metadata, "generated": True, "agent_ok": True},
        )

    def _evidence(self, result: RunResult, result_path: Path, workspace_dir: Path) -> CandidateEvidence:
        # The workspace is a host directory the harness ran in, so its final file tree is available on
        # disk — expose it as filesystem evidence so workspace-reading metrics can score a Fabric trial.
        descriptors: dict[str, EvidenceDescriptor] = {
            "result": EvidenceDescriptor(kind="json", format="json", ref=str(result_path)),
            _WORKSPACE_EVIDENCE_KEY: EvidenceDescriptor(kind=_WORKSPACE_EVIDENCE_KIND, ref=str(workspace_dir)),
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
                "agent_ok": False,
                "error_type": error_type,
                "error": error_message,
            },
        )

    def _compose_config(
        self,
        agent_config: FabricConfig,
        evidence_dir: Path,
        workspace_dir: Path,
    ) -> FabricConfig:
        # nemo_fabric is already imported+validated in ``run_tasks``; this is a cached sys.modules
        # lookup, not a re-load, so the type is used where it's constructed instead of threaded down.
        from nemo_fabric import EnvironmentConfig  # ty: ignore[unresolved-import]

        # Config-first composition (the SDK's recommended in-memory pattern): copy the base config and
        # apply this task's workspace, model, and trajectory settings directly onto it, rather than
        # layering FabricProfileConfig overlays.
        cfg = agent_config.model_copy(deep=True)

        # Point the harness at this task's staged workspace (the codex-cli adapter resolves its cwd from
        # it). ``provider="local"`` is required by the native planner. Any config-supplied
        # environment.workspace is overridden per task.
        environment = cfg.environment or EnvironmentConfig(provider="local")
        environment.provider = environment.provider or "local"
        environment.workspace = str(workspace_dir)
        cfg.environment = environment

        # Apply the model as the config's default (mirrors nemo_fabric.integrations.harbor).
        if self._model:
            provider = self._model.split("/", maxsplit=1)[0] if "/" in self._model else "openai"
            cfg.models["default"] = {"provider": provider, "model": self._model}

        if self._capture_trajectory:
            # Enable Relay's ATIF/ATOF file exporter under this task's durable evidence dir, and pin the
            # Fabric artifact root so the promoted ``trajectory-*.atif.json`` persists. Requires the
            # ``nemo-relay`` gateway on PATH in the runtime.
            relay_dir = evidence_dir / _RELAY_SUBDIR
            artifacts_dir = evidence_dir / _ARTIFACTS_SUBDIR
            relay_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            cfg.enable_relay(output_dir=str(relay_dir), config=self._relay_config(relay_dir))
            cfg.runtime.artifacts = str(artifacts_dir)
            cfg.environment.artifacts = str(artifacts_dir)

        return cfg

    def _eval_lock_profiles(
        self,
        profile_cls: type[FabricProfileConfig],
        *,
        workspace_dir: Path,
        evidence_dir: Path,
    ) -> list[FabricProfileConfig]:
        # ``_compose_config`` composes the evaluator's per-task settings onto the config, but Fabric
        # applies caller-supplied profiles OVER the config (last-wins), so a caller profile could
        # otherwise override them. Re-assert the evaluator-owned settings here as trailing overlays —
        # applied after the caller profiles — so the per-task workspace (isolation + ``workspace``
        # evidence integrity), the model under evaluation, and the trajectory artifact location stay
        # authoritative and non-overridable.
        overlays = [
            profile_cls.from_mapping(
                {"name": _WORKSPACE_PROFILE_NAME, "environment": {"workspace": str(workspace_dir)}}
            )
        ]
        if self._model:
            provider = self._model.split("/", maxsplit=1)[0] if "/" in self._model else "openai"
            overlays.append(
                profile_cls.from_mapping(
                    {"name": _MODEL_PROFILE_NAME, "models": {"default": {"provider": provider, "model": self._model}}}
                )
            )
        if self._capture_trajectory:
            artifacts_dir = str(evidence_dir / _ARTIFACTS_SUBDIR)
            overlays.append(
                profile_cls.from_mapping(
                    {
                        "name": _ARTIFACTS_PROFILE_NAME,
                        "runtime": {"artifacts": artifacts_dir},
                        "environment": {"artifacts": artifacts_dir},
                    }
                )
            )
        return overlays

    def _relay_config(self, relay_dir: Path) -> dict[str, Any]:
        # The observability component is built from nemo_relay's own typed config objects so Relay owns
        # its schema (no hand-maintained dict that silently drifts when Relay changes it); imported
        # lazily since nemo-relay, like nemo-fabric, is an optional native dependency.
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
        return {"version": 1, "components": [observability.to_dict()]}

    def _evidence_dir(self, index: int, task: AgentEvalTask, config: AgentEvalRunConfig) -> Path:
        root = self._work_root
        if root is None:
            root = (config.output_dir or Path.cwd()) / "evidence" / "fabric"
        # The run id isolates this run's evidence from other runs sharing the same root (A/B baseline
        # vs. skilled); run_tasks always populates it, so the fallback only guards a direct call.
        run_id = config.run_id or _new_run_id()
        safe_task_id = _safe_path_name(task.id)
        task_dir = f"{index:06d}-{safe_task_id}" if safe_task_id else f"task-{index:06d}"
        return Path(root) / _safe_path_name(run_id) / task_dir


def _remove_injected_bundle(workspace_dir: Path, location: str) -> None:
    """Remove the Codex-injected skill subtree from ``workspace_dir`` and prune emptied parents.

    ``location`` is workspace-relative (``.agents/skills/<name>``). Best-effort: the skill was already
    captured in the run's trajectory, so SkillUsedMetric (which reads the trace, not the workspace) is
    unaffected, and any filesystem error here must not fail an otherwise-successful trial.
    """
    workspace_root = workspace_dir.resolve()
    injected = (workspace_dir / location).resolve()
    # Guard against a location escaping the workspace (defensive; provenance is evaluator-authored).
    if workspace_root not in injected.parents or not injected.exists():
        return
    shutil.rmtree(injected, ignore_errors=True)
    # Prune now-empty reserved parents (``.agents/skills``, ``.agents``) but never the workspace itself.
    parent = injected.parent
    while parent != workspace_root and parent.is_dir():
        try:
            parent.rmdir()  # only succeeds while empty
        except OSError:
            break
        parent = parent.parent


def _normalize_output(output: RunOutput | JsonValue) -> JsonValue:
    """Unwrap a Fabric ``RunResult.output`` into the plain JSON value the trial response stores.

    Newer Fabric wraps output in a ``RunOutput`` (the RunOutput response contract), which is a
    ``Mapping``; copy it into a plain dict (equivalent to its ``to_mapping()``). Raw/older JSON outputs
    are already JSON values and pass through unchanged.
    """
    if isinstance(output, Mapping):
        return dict(output)
    return output


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


def _new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    return f"fabric-{timestamp}-{uuid4().hex[:8]}"
