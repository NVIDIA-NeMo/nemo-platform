# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Optuna numeric optimize backend."""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext

from nemo_optimization.backends.optuna.atif_metadata import resolve_experiment_id
from nemo_optimization.backends.optuna.fabric_trial import FabricTrialEvaluator
from nemo_optimization.backends.optuna.study_driver import (
    StudyDriverError,
    SyntheticTrialEvaluator,
    parse_numeric_study_config,
    run_numeric_study,
)
from nemo_optimization.config import generate_optimize_id

logger = logging.getLogger(__name__)

RESULT_NAME = "optimizer_results"


class OptunaBackend:
    """Numeric/categorical HPO via Optuna."""

    name: ClassVar[str] = "optuna"

    def run_study(
        self,
        payload: dict[str, Any],
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict[str, Any]:
        del sdk
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
        experiment_id = resolve_experiment_id(payload, generate_id=generate_optimize_id)
        evaluator = _build_trial_evaluator(
            payload,
            metric_names=metric_names,
            output_dir=output_dir,
            experiment_id=experiment_id,
        )

        result = run_numeric_study(payload, output_dir, evaluator)
        summary = {
            "status": "completed",
            "backend": self.name,
            "phase": "core",
            "experiment_id": experiment_id,
            "n_trials": result.n_trials,
            "best_trial": result.best_trial.number,
            "best_params": dict(result.best_trial.params),
            "best_values": list(result.best_trial.values or []),
            "metric_names": list(result.metric_names),
            "agent": payload.get("metadata", {}).get("name"),
        }
        (output_dir / "study_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        ref = ctx.results.save(RESULT_NAME, output_dir)
        return {
            **summary,
            "result": ref.model_dump(mode="json"),
        }


def _build_trial_evaluator(
    payload: dict[str, Any],
    *,
    metric_names: tuple[str, ...],
    output_dir,
    experiment_id: str,
):
    if isinstance(payload.get("eval"), dict):
        return FabricTrialEvaluator(
            payload=payload,
            metric_names=metric_names,
            output_dir=output_dir,
            experiment_id=experiment_id,
        )

    # Unit-test/scaffold path for configs that intentionally omit eval.
    logger.warning("Optuna study using SyntheticTrialEvaluator because payload.eval is absent.")
    return SyntheticTrialEvaluator(metric_names)
