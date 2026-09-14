# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OptimizeRouter — dispatches Fabric-native optimize payloads to Tune backends.

Integration boundaries (Part A §3):

| Component | Owns |
|-----------|------|
| ``OptimizeJob`` | Optional platform agent ref resolution; Fabric payload assembly; IGW preflight; `OptimizeRouter.dispatch()` |
| ``OptimizeRouter`` | Backend selection from ``optimizer.*.enabled`` flags |
| Tune backend (``optuna``) | Study loop, profile overlays, artifact writers, rep averaging |
| ``AgentEvaluator`` + ``FabricAgentRuntime`` | Per-trial agent execution, scoring input, ATIF evidence |
| NeMo Fabric + adapters | Harness runtime (e.g. ``nvidia.fabric.hermes``) |
| Jobs | ``ctx.results.save`` persistence for study artifacts |
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext

from nemo_optimization.artifact_utils import sanitize_config_for_artifact
from nemo_optimization.atif_metadata import resolve_experiment_id
from nemo_optimization.backends.ga.config import GaConfigError
from nemo_optimization.backends.ga.transform import PromptTransformError
from nemo_optimization.backends.optuna.study_driver import StudyDriverError
from nemo_optimization.backends.protocol import (
    OptimizationBackend,
    OptimizationPhase,
    OptimizationPhaseRequest,
    OptimizationPhaseResult,
    OptimizationPhaseStatus,
)
from nemo_optimization.candidate import CandidateEvaluationError
from nemo_optimization.config import generate_optimize_id
from nemo_optimization.config_overlay import apply_suggestions
from nemo_optimization.fabric import build_optimize_payload, require_fabric_agent_config
from nemo_optimization.registry import OptimizationBackendDiscoveryError, require_optimization_backend
from nemo_optimization.search_space import DEFAULT_PROMPT_BACKEND

DEFAULT_NUMERIC_BACKEND = "optuna"
RESULT_NAME = "optimizer_results"
ORCHESTRATOR_BACKEND = "orchestrator"
MULTI_PHASE = "multi"
_EXPECTED_PHASE_ERRORS = (GaConfigError, PromptTransformError, StudyDriverError, CandidateEvaluationError)


class OptimizeRouterError(RuntimeError):
    """Raised when optimize routing fails."""


@dataclass(frozen=True)
class _PhasePlan:
    phase: OptimizationPhase
    backend_name: str
    backend: OptimizationBackend


class OptimizeRouter:
    """Routing hub for agent optimize jobs (Optuna / GA backends)."""

    @staticmethod
    def dispatch(
        *,
        agent_config: dict[str, Any] | None,
        optimize_config: dict[str, Any],
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict[str, Any]:
        """Route a Fabric-native optimize study to the selected Tune backend."""
        payload = build_optimize_payload(agent_config=agent_config, optimize_config=optimize_config)
        return _run_phases(payload, ctx=ctx, sdk=sdk)

    @staticmethod
    def dispatch_payload(
        payload: dict[str, Any],
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict[str, Any]:
        """Route an already-merged Fabric payload (used by tests and future job types)."""
        require_fabric_agent_config(payload, label="optimize payload")
        return _run_phases(payload, ctx=ctx, sdk=sdk)


def _run_phases(
    payload: dict[str, Any],
    *,
    ctx: JobContext,
    sdk: NeMoPlatform | None,
) -> dict[str, Any]:
    plan = _phase_plan(payload)
    experiment_id = resolve_experiment_id(payload, generate_id=generate_optimize_id)
    output_dir = ctx.storage.persistent / "results" / RESULT_NAME
    phase_results: list[OptimizationPhaseResult] = []
    current_payload = copy.deepcopy(payload)
    trial_number_offset = 0

    for index, phase_plan in enumerate(plan):
        try:
            result = phase_plan.backend.run_phase(
                OptimizationPhaseRequest(
                    payload=current_payload,
                    phase=phase_plan.phase,
                    experiment_id=experiment_id,
                    trial_number_offset=trial_number_offset,
                ),
                ctx=ctx,
                sdk=sdk,
            )
        except _EXPECTED_PHASE_ERRORS as exc:
            result = _failed_phase_result(
                phase_plan,
                payload=current_payload,
                output_dir=output_dir,
                experiment_id=experiment_id,
                trial_number_offset=trial_number_offset,
                error=exc,
            )
        phase_results.append(result)
        trial_number_offset += result.trial_count
        current_payload = copy.deepcopy(result.optimized_payload)
        _write_orchestration_artifacts(
            output_dir,
            experiment_id=experiment_id,
            phase_results=phase_results,
            planned_phase_count=len(plan),
        )
        if result.status is not OptimizationPhaseStatus.COMPLETED:
            phase_results.extend(
                _skipped_phase_results(
                    plan[index + 1 :],
                    payload=current_payload,
                    trial_number_offset=trial_number_offset,
                    reason=f"Skipped because {result.phase.value!r} phase returned status {result.status.value!r}.",
                )
            )
            _write_orchestration_artifacts(
                output_dir,
                experiment_id=experiment_id,
                phase_results=phase_results,
                planned_phase_count=len(plan),
            )
            break

    if len(phase_results) == 1 and len(plan) == 1:
        phase_result = phase_results[0].to_result_dict()
        phase_result.setdefault("experiment_id", experiment_id)
        ref = ctx.results.save(RESULT_NAME, output_dir)
        phase_result["result"] = ref.model_dump(mode="json")
        return phase_result
    return _combined_result(phase_results, experiment_id=experiment_id, ctx=ctx)


def _phase_plan(payload: dict[str, Any]) -> list[_PhasePlan]:
    optimizer = payload.get("optimizer")
    if not isinstance(optimizer, Mapping):
        raise OptimizeRouterError("optimizer section must be a mapping.")

    numeric = _phase_section(optimizer, "numeric")
    prompt = _phase_section(optimizer, "prompt")
    numeric_enabled = bool(numeric.get("enabled")) if numeric is not None else False
    prompt_enabled = bool(prompt.get("enabled")) if prompt is not None else False

    plan: list[_PhasePlan] = []
    if numeric_enabled:
        assert numeric is not None
        backend_name = _backend_name(numeric, default=DEFAULT_NUMERIC_BACKEND)
        plan.append(
            _PhasePlan(
                phase=OptimizationPhase.NUMERIC,
                backend_name=backend_name,
                backend=_require_backend(backend_name, phase=OptimizationPhase.NUMERIC),
            )
        )
    if prompt_enabled:
        assert prompt is not None
        backend_name = _backend_name(prompt, default=DEFAULT_PROMPT_BACKEND)
        plan.append(
            _PhasePlan(
                phase=OptimizationPhase.PROMPT,
                backend_name=backend_name,
                backend=_require_backend(backend_name, phase=OptimizationPhase.PROMPT),
            )
        )
    if plan:
        return plan

    raise OptimizeRouterError(
        "No Tune backend selected. Set optimizer.numeric.enabled: true for numeric HPO "
        "or optimizer.prompt.enabled: true for prompt GA."
    )


def _phase_section(optimizer: Mapping[str, Any], name: str) -> dict[str, Any] | None:
    if name not in optimizer:
        return None
    raw = optimizer[name]
    if not isinstance(raw, Mapping):
        raise OptimizeRouterError(f"optimizer.{name} must be a mapping.")
    section = dict(raw)
    enabled = section.get("enabled")
    if not isinstance(enabled, bool):
        raise OptimizeRouterError(f"optimizer.{name}.enabled must be a boolean.")
    return section


def _backend_name(section: dict[str, Any], *, default: str) -> str:
    raw = section.get("backend", default)
    if not isinstance(raw, str):
        raise OptimizeRouterError("Optimizer backend name must be a string.")
    if not raw.strip():
        raise OptimizeRouterError("Optimizer backend name must not be empty.")
    return raw.strip()


def _require_backend(backend_name: str, *, phase: OptimizationPhase) -> OptimizationBackend:
    try:
        return require_optimization_backend(backend_name, phase=phase)
    except OptimizationBackendDiscoveryError as exc:
        raise OptimizeRouterError(str(exc)) from exc


def _skipped_phase_results(
    remaining: list[_PhasePlan],
    *,
    payload: dict[str, Any],
    trial_number_offset: int,
    reason: str,
) -> list[OptimizationPhaseResult]:
    return [
        OptimizationPhaseResult(
            phase=phase_plan.phase,
            backend=phase_plan.backend_name,
            status=OptimizationPhaseStatus.SKIPPED,
            optimized_payload=copy.deepcopy(payload),
            summary={"reason": reason},
            trial_count=0,
            trial_number_offset=trial_number_offset,
        )
        for phase_plan in remaining
    ]


def _failed_phase_result(
    phase_plan: _PhasePlan,
    *,
    payload: dict[str, Any],
    output_dir: Path,
    experiment_id: str,
    trial_number_offset: int,
    error: Exception,
) -> OptimizationPhaseResult:
    trial_count = getattr(error, "trial_count", 0)
    if not isinstance(trial_count, int):
        trial_count = 0
    optimized_payload = getattr(error, "optimized_payload", None)
    if not isinstance(optimized_payload, dict):
        optimized_payload = payload
    summary = {
        "experiment_id": experiment_id,
        "error": str(error),
        "error_type": type(error).__name__,
        "executed_trials": trial_count,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    failure_path = output_dir / f"{phase_plan.phase.value}_phase_failure.json"
    failure_path.write_text(
        json.dumps(
            {
                "status": OptimizationPhaseStatus.FAILED.value,
                "backend": phase_plan.backend_name,
                "phase": phase_plan.phase.value,
                **summary,
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return OptimizationPhaseResult(
        phase=phase_plan.phase,
        backend=phase_plan.backend_name,
        status=OptimizationPhaseStatus.FAILED,
        optimized_payload=copy.deepcopy(optimized_payload),
        summary=summary,
        artifacts={"failure": {"path": failure_path.name}},
        trial_count=trial_count,
        trial_number_offset=trial_number_offset,
    )


def _combined_result(
    phase_results: list[OptimizationPhaseResult],
    *,
    experiment_id: str,
    ctx: JobContext,
) -> dict[str, Any]:
    output_dir = ctx.storage.persistent / "results" / RESULT_NAME
    ref = ctx.results.save(RESULT_NAME, output_dir)
    status = _overall_status(phase_results)
    return {
        "status": status.value,
        "backend": ORCHESTRATOR_BACKEND,
        "phase": MULTI_PHASE,
        "experiment_id": experiment_id,
        "trial_number_range": _trial_number_range(phase_results),
        "phases": [_phase_result_summary(result) for result in phase_results],
        "result": ref.model_dump(mode="json"),
    }


def _write_orchestration_artifacts(
    output_dir: Path,
    *,
    experiment_id: str,
    phase_results: list[OptimizationPhaseResult],
    planned_phase_count: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    status = _overall_status(phase_results)
    summary = {
        "status": status.value,
        "backend": ORCHESTRATOR_BACKEND,
        "phase": MULTI_PHASE if planned_phase_count > 1 else phase_results[0].phase.value,
        "experiment_id": experiment_id,
        "trial_number_range": _trial_number_range(phase_results),
        "phases": [_phase_result_summary(result) for result in phase_results],
    }
    (output_dir / "optimization_summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (output_dir / "phase_results.json").write_text(
        json.dumps([_phase_result_detail(result) for result in phase_results], indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    numeric_result = _completed_phase_result(phase_results, OptimizationPhase.NUMERIC)
    if numeric_result is not None and planned_phase_count > 1:
        _write_payload_artifact(output_dir / "intermediate_numeric_payload.json", numeric_result.optimized_payload)
        _write_config_artifact(output_dir / "intermediate_numeric_config.yml", numeric_result.optimized_payload)

    if status is OptimizationPhaseStatus.COMPLETED and len(phase_results) == planned_phase_count:
        final_payload = phase_results[-1].optimized_payload
        _write_payload_artifact(output_dir / "final_optimized_payload.json", final_payload)
        _write_config_artifact(output_dir / "final_optimized_config.yml", final_payload)


def _phase_result_summary(result: OptimizationPhaseResult) -> dict[str, Any]:
    return {
        "phase": result.phase.value,
        "backend": result.backend,
        "status": result.status.value,
        "trial_number_range": result.trial_number_range,
        "summary": copy.deepcopy(dict(result.summary)),
    }


def _phase_result_detail(result: OptimizationPhaseResult) -> dict[str, Any]:
    return {
        **_phase_result_summary(result),
        "artifacts": copy.deepcopy(dict(result.artifacts)),
    }


def _completed_phase_result(
    phase_results: list[OptimizationPhaseResult],
    phase: OptimizationPhase,
) -> OptimizationPhaseResult | None:
    for result in phase_results:
        if result.phase is phase and result.status is OptimizationPhaseStatus.COMPLETED:
            return result
    return None


def _overall_status(phase_results: list[OptimizationPhaseResult]) -> OptimizationPhaseStatus:
    if any(result.status is OptimizationPhaseStatus.FAILED for result in phase_results):
        return OptimizationPhaseStatus.FAILED
    if any(result.status is OptimizationPhaseStatus.SKIPPED for result in phase_results):
        return OptimizationPhaseStatus.FAILED
    return OptimizationPhaseStatus.COMPLETED


def _trial_number_range(phase_results: list[OptimizationPhaseResult]) -> dict[str, int]:
    if not phase_results:
        return {"start": 0, "end_exclusive": 0, "count": 0}
    start = phase_results[0].trial_number_offset
    count = sum(result.trial_count for result in phase_results)
    return {"start": start, "end_exclusive": start + count, "count": count}


def _write_payload_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(sanitize_config_for_artifact(payload), indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _write_config_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(sanitize_config_for_artifact(apply_suggestions(payload, {})), sort_keys=False),
        encoding="utf-8",
    )
