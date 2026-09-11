# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Optuna numeric optimize backend."""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, ClassVar

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext

from nemo_optimization.atif_metadata import resolve_experiment_id
from nemo_optimization.backends.optuna.study_driver import (
    StudyDriverError,
    SyntheticTrialEvaluator,
    parse_numeric_study_config,
    run_numeric_study,
)
from nemo_optimization.backends.protocol import (
    OptimizationBackendCapabilities,
    OptimizationPhase,
    OptimizationPhaseRequest,
    OptimizationPhaseResult,
    OptimizationPhaseStatus,
)
from nemo_optimization.candidate import CandidateEvaluationError
from nemo_optimization.config import generate_optimize_id
from nemo_optimization.fabric_evaluator import FabricCandidateEvaluator

logger = logging.getLogger(__name__)

RESULT_NAME = "optimizer_results"


class OptunaBackend:
    """Numeric/categorical HPO via Optuna."""

    name: ClassVar[str] = "optuna"
    capabilities: ClassVar[OptimizationBackendCapabilities] = OptimizationBackendCapabilities(
        phases=(OptimizationPhase.NUMERIC,)
    )

    def run_study(
        self,
        payload: dict[str, Any],
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict[str, Any]:
        result = self.run_phase(
            OptimizationPhaseRequest(payload=payload, phase=OptimizationPhase.NUMERIC),
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
        if request.phase is not OptimizationPhase.NUMERIC:
            raise StudyDriverError(f"Optuna backend does not support the {request.phase.value!r} phase.")
        payload = request.payload
        output_dir = ctx.storage.persistent / "results" / RESULT_NAME
        if "optimizer" not in payload:
            raise StudyDriverError("payload must include an 'optimizer' section.")
        try:
            config = parse_numeric_study_config(payload["optimizer"])
        except StudyDriverError:
            raise
        except KeyError as exc:
            raise StudyDriverError(f"payload optimizer section is missing required key: {exc}") from exc

        metric_names = tuple(metric.name for metric in config.metrics)
        experiment_id = request.experiment_id or resolve_experiment_id(payload, generate_id=generate_optimize_id)
        try:
            evaluator = _build_trial_evaluator(
                payload,
                metric_names=metric_names,
                output_dir=output_dir,
                experiment_id=experiment_id,
            )
            result = run_numeric_study(payload, output_dir, evaluator)
        except (CandidateEvaluationError, StudyDriverError) as exc:
            return _failed_numeric_phase_result(
                payload,
                backend=self.name,
                output_dir=output_dir,
                ctx=ctx,
                experiment_id=experiment_id,
                error=str(exc),
                trial_number_offset=request.trial_number_offset,
            )
        summary = {
            "experiment_id": experiment_id,
            "n_trials": result.n_trials,
            "executed_trials": result.executed_trials,
            "best_trial": result.best_trial.number,
            "best_params": dict(result.best_trial.params),
            "best_values": list(result.best_trial.values or []),
            "metric_names": list(result.metric_names),
            "agent": payload.get("metadata", {}).get("name"),
        }
        summary_path = output_dir / "study_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "status": OptimizationPhaseStatus.COMPLETED.value,
                    "backend": self.name,
                    "phase": OptimizationPhase.NUMERIC.value,
                    **summary,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        debug_path = output_dir / "study_debug.json"
        debug_path.write_text(
            json.dumps(_study_debug_payload(result), indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        ref = ctx.results.save(RESULT_NAME, output_dir)
        return OptimizationPhaseResult(
            phase=OptimizationPhase.NUMERIC,
            backend=self.name,
            status=OptimizationPhaseStatus.COMPLETED,
            optimized_payload=result.optimized_payload,
            summary=summary,
            artifacts={"result": ref.model_dump(mode="json")},
            trial_count=result.executed_trials,
            trial_number_offset=request.trial_number_offset,
        )


def _study_debug_payload(result) -> dict[str, Any]:
    """JSON-serializable Optuna study snapshot for debugging (not the Study object itself)."""
    study = result.study
    trials: list[dict[str, Any]] = []
    for trial in study.trials:
        trials.append(
            {
                "number": trial.number,
                "state": trial.state.name,
                "params": dict(trial.params),
                "values": list(trial.values) if trial.values is not None else None,
                "user_attrs": dict(trial.user_attrs),
                "datetime_start": trial.datetime_start.isoformat() if trial.datetime_start else None,
                "datetime_complete": trial.datetime_complete.isoformat() if trial.datetime_complete else None,
                "duration_seconds": trial.duration.total_seconds() if trial.duration is not None else None,
            }
        )
    return {
        "study_name": study.study_name,
        "directions": [direction.name for direction in study.directions],
        "sampler": type(study.sampler).__name__,
        "n_trials": result.n_trials,
        "executed_trials": result.executed_trials,
        "metric_names": list(result.metric_names),
        "best_trial": result.best_trial.number,
        "best_params": dict(result.best_trial.params),
        "best_values": list(result.best_trial.values or []),
        "trials": trials,
    }


def _failed_numeric_phase_result(
    payload: dict[str, Any],
    *,
    backend: str,
    output_dir,
    ctx: JobContext,
    experiment_id: str,
    error: str,
    trial_number_offset: int,
) -> OptimizationPhaseResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": OptimizationPhaseStatus.FAILED.value,
        "backend": backend,
        "phase": OptimizationPhase.NUMERIC.value,
        "experiment_id": experiment_id,
        "error": error,
    }
    (output_dir / "numeric_phase_failure.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    ref = ctx.results.save(RESULT_NAME, output_dir)
    return OptimizationPhaseResult(
        phase=OptimizationPhase.NUMERIC,
        backend=backend,
        status=OptimizationPhaseStatus.FAILED,
        optimized_payload=copy.deepcopy(payload),
        summary={"experiment_id": experiment_id, "error": error},
        artifacts={"result": ref.model_dump(mode="json")},
        trial_count=0,
        trial_number_offset=trial_number_offset,
    )


def _build_trial_evaluator(
    payload: dict[str, Any],
    *,
    metric_names: tuple[str, ...],
    output_dir,
    experiment_id: str,
):
    if isinstance(payload.get("eval"), dict):
        return FabricCandidateEvaluator(
            payload=payload,
            metric_names=metric_names,
            output_dir=output_dir,
            experiment_id=experiment_id,
        )

    # Unit-test/scaffold path for configs that intentionally omit eval.
    logger.warning("Optuna study using SyntheticTrialEvaluator because payload.eval is absent.")
    return SyntheticTrialEvaluator(metric_names)
