# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prompt GA optimize backend."""

from __future__ import annotations

import copy
import json
from typing import Any, ClassVar

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext

from nemo_optimization.atif_metadata import resolve_experiment_id
from nemo_optimization.backends.ga.config import (
    GaConfigError,
    GaPromptOptimizerConfig,
    parse_ga_prompt_optimizer_config,
)
from nemo_optimization.backends.ga.driver import (
    GaPromptOptimizationResult,
    GaPromptOptimizerError,
    run_ga_prompt_optimization,
)
from nemo_optimization.backends.ga.transform import (
    ModelPromptTransformer,
    PromptTransformer,
    PromptTransformError,
)
from nemo_optimization.backends.protocol import (
    OptimizationBackendCapabilities,
    OptimizationPhase,
    OptimizationPhaseRequest,
    OptimizationPhaseResult,
    OptimizationPhaseStatus,
)
from nemo_optimization.candidate import CandidateEvaluationError, CandidateEvaluator
from nemo_optimization.config import generate_optimize_id
from nemo_optimization.fabric_evaluator import FabricCandidateEvaluator

RESULT_NAME = "optimizer_results"


class GaBackendError(RuntimeError):
    """Raised when prompt GA backend usage is invalid."""


class GaBackend:
    name: ClassVar[str] = "ga"
    capabilities: ClassVar[OptimizationBackendCapabilities] = OptimizationBackendCapabilities(
        phases=(OptimizationPhase.PROMPT,)
    )

    def run_study(
        self,
        payload: dict[str, Any],
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict[str, Any]:
        result = self.run_phase(
            OptimizationPhaseRequest(payload=payload, phase=OptimizationPhase.PROMPT),
            ctx=ctx,
            sdk=sdk,
        )
        return result.to_result_dict()

    def run_phase(
        self,
        request: OptimizationPhaseRequest,
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> OptimizationPhaseResult:
        del sdk
        if request.phase is not OptimizationPhase.PROMPT:
            raise GaBackendError(f"GA backend does not support the {request.phase.value!r} phase.")
        payload = request.payload
        output_dir = ctx.storage.persistent / "results" / RESULT_NAME

        try:
            config = parse_ga_prompt_optimizer_config(payload)
        except GaConfigError:
            raise
        except KeyError as exc:
            raise GaConfigError(f"payload optimizer section is missing required key: {exc}") from exc

        experiment_id = request.experiment_id or resolve_experiment_id(payload, generate_id=generate_optimize_id)
        try:
            evaluator = _build_prompt_evaluator(
                payload,
                metric_names=config.metric_names,
                output_dir=output_dir,
                experiment_id=experiment_id,
            )
            transformer = _build_prompt_transformer(payload, model_name=config.model)
            result = run_ga_prompt_optimization(
                payload,
                output_dir,
                evaluator,
                transformer,
                config=config,
                trial_number_offset=request.trial_number_offset,
            )
        except (CandidateEvaluationError, GaPromptOptimizerError, PromptTransformError) as exc:
            return _failed_prompt_phase_result(
                payload,
                backend=self.name,
                output_dir=output_dir,
                ctx=ctx,
                experiment_id=experiment_id,
                error=str(exc),
                optimized_payload=getattr(exc, "optimized_payload", None),
                trial_count=getattr(exc, "trial_count", 0),
                trial_number_offset=request.trial_number_offset,
            )

        summary = _phase_summary(result, experiment_id=experiment_id, payload=payload, config=config)
        summary_path = output_dir / "prompt_phase_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "status": OptimizationPhaseStatus.COMPLETED.value,
                    "backend": self.name,
                    "phase": OptimizationPhase.PROMPT.value,
                    **summary,
                },
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        ref = ctx.results.save(RESULT_NAME, output_dir)
        return OptimizationPhaseResult(
            phase=OptimizationPhase.PROMPT,
            backend=self.name,
            status=OptimizationPhaseStatus.COMPLETED,
            optimized_payload=result.optimized_payload,
            summary=summary,
            artifacts={"result": ref.model_dump(mode="json")},
            trial_count=result.executed_trials,
            trial_number_offset=request.trial_number_offset,
        )


def _phase_summary(
    result: GaPromptOptimizationResult,
    *,
    experiment_id: str,
    payload: dict[str, Any],
    config: GaPromptOptimizerConfig,
) -> dict[str, Any]:
    best = result.best_individual
    return {
        "experiment_id": experiment_id,
        "population_size": config.population_size,
        "generations": config.generations,
        "generations_completed": result.generations_completed,
        "executed_trials": result.executed_trials,
        "best_individual": best.individual_id,
        "best_phase_trial_number": best.phase_trial_number,
        "best_global_trial_number": best.global_trial_number,
        "best_prompts": dict(best.prompts),
        "best_metrics": dict(best.aggregate_metrics),
        "best_fitness": best.fitness,
        "metric_names": list(result.metric_names),
        "agent": payload.get("metadata", {}).get("name"),
    }


def _failed_prompt_phase_result(
    payload: dict[str, Any],
    *,
    backend: str,
    output_dir,
    ctx: JobContext,
    experiment_id: str,
    error: str,
    optimized_payload: dict[str, Any] | None,
    trial_count: int,
    trial_number_offset: int,
) -> OptimizationPhaseResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    failure = {
        "status": OptimizationPhaseStatus.FAILED.value,
        "backend": backend,
        "phase": OptimizationPhase.PROMPT.value,
        "experiment_id": experiment_id,
        "error": error,
        "executed_trials": trial_count,
    }
    failure_path = output_dir / "prompt_phase_failure.json"
    if failure_path.is_file():
        try:
            existing = json.loads(failure_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if isinstance(existing, dict):
            failure = {**existing, **failure}
    failure_path.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
    ref = ctx.results.save(RESULT_NAME, output_dir)
    return OptimizationPhaseResult(
        phase=OptimizationPhase.PROMPT,
        backend=backend,
        status=OptimizationPhaseStatus.FAILED,
        optimized_payload=copy.deepcopy(optimized_payload if optimized_payload is not None else payload),
        summary={"experiment_id": experiment_id, "error": error, "executed_trials": trial_count},
        artifacts={"result": ref.model_dump(mode="json")},
        trial_count=trial_count,
        trial_number_offset=trial_number_offset,
    )


def _build_prompt_evaluator(
    payload: dict[str, Any],
    *,
    metric_names: tuple[str, ...],
    output_dir,
    experiment_id: str,
) -> CandidateEvaluator:
    if isinstance(payload.get("eval"), dict):
        return FabricCandidateEvaluator(
            payload=payload,
            metric_names=metric_names,
            output_dir=output_dir,
            experiment_id=experiment_id,
        )

    raise GaConfigError("Prompt GA optimization requires payload.eval; prompt-only means no numeric phase.")


def _build_prompt_transformer(payload: dict[str, Any], *, model_name: str) -> PromptTransformer:
    return ModelPromptTransformer(payload=payload, model_name=model_name)
