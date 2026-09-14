# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

import pytest
from nemo_optimization.backends.ga.config import GaConfigError
from nemo_optimization.backends.protocol import (
    OptimizationBackend,
    OptimizationBackendCapabilities,
    OptimizationPhase,
    OptimizationPhaseRequest,
    OptimizationPhaseResult,
    OptimizationPhaseStatus,
)
from nemo_optimization.router import OptimizeRouter, OptimizeRouterError
from nemo_platform_plugin.job_context import JobContext


def test_dispatch_routes_numeric_to_optuna_study(ctx: JobContext) -> None:
    payload = {
        "schema_version": "fabric.agent/v1alpha1",
        "metadata": {"name": "demo"},
        "optimizer": {
            "numeric": {"enabled": True, "n_trials": 2},
            "eval_metrics": {
                "average_score": {"direction": "maximize", "weight": 1.0},
            },
            "search_space": {
                "temperature": {
                    "type": "fabric",
                    "path": "models.default.temperature",
                    "values": [0.0, 0.2],
                },
            },
        },
    }
    result = OptimizeRouter.dispatch_payload(payload, ctx=ctx)
    assert result["status"] == "completed"
    assert result["backend"] == "optuna"
    assert result["phase"] == "numeric"
    assert result["n_trials"] == 2
    assert result["trial_number_range"] == {"start": 0, "end_exclusive": 2, "count": 2}

    out_dir = ctx.storage.persistent / "results" / "optimizer_results"
    summary = json.loads((out_dir / "study_summary.json").read_text(encoding="utf-8"))
    assert summary["backend"] == "optuna"
    debug = json.loads((out_dir / "study_debug.json").read_text(encoding="utf-8"))
    assert debug["n_trials"] == 2
    assert len(debug["trials"]) == 2
    assert {t["state"] for t in debug["trials"]} == {"COMPLETE"}
    assert (out_dir / "optimized_config.yml").is_file()


def test_dispatch_uses_executed_trial_count_for_phase_range(ctx: JobContext) -> None:
    payload = {
        "schema_version": "fabric.agent/v1alpha1",
        "metadata": {"name": "demo"},
        "optimizer": {
            "numeric": {"enabled": True, "n_trials": 20},
            "target": 0.5,
            "eval_metrics": {
                "average_score": {"direction": "maximize", "weight": 1.0},
            },
            "search_space": {
                "temperature": {
                    "type": "fabric",
                    "path": "models.default.temperature",
                    "values": [1.0, 2.0],
                },
            },
        },
    }

    result = OptimizeRouter.dispatch_payload(payload, ctx=ctx)

    assert result["n_trials"] == 20
    assert result["executed_trials"] == 1
    assert result["trial_number_range"] == {"start": 0, "end_exclusive": 1, "count": 1}


def test_dispatch_prompt_enabled_requires_eval(ctx: JobContext) -> None:
    payload = {
        "schema_version": "fabric.agent/v1alpha1",
        "models": {"prompt_optimizer": {"provider": "openai", "model": "gpt-5-mini"}},
        "instructions": {"system": {"content": "Base prompt."}},
        "optimizer": {
            "prompt": {
                "enabled": True,
                "backend": "ga",
                "model": "prompt_optimizer",
                "population_size": 3,
                "generations": 1,
            },
            "eval_metrics": {
                "average_score": {"direction": "maximize", "weight": 1.0},
            },
            "search_space": {
                "system_prompt": {
                    "type": "fabric",
                    "path": "instructions.system.content",
                    "is_prompt": True,
                    "purpose": "Answer accurately.",
                }
            },
        },
    }

    with pytest.raises(GaConfigError, match="requires payload.eval"):
        OptimizeRouter.dispatch_payload(payload, ctx=ctx)


def test_dispatch_prompt_backend_must_support_prompt_phase(ctx: JobContext) -> None:
    payload = {
        "schema_version": "fabric.agent/v1alpha1",
        "models": {"prompt_optimizer": {"provider": "openai", "model": "gpt-5-mini"}},
        "instructions": {"system": {"content": "Base prompt."}},
        "optimizer": {
            "prompt": {"enabled": True, "backend": "optuna", "model": "prompt_optimizer"},
            "search_space": {
                "system_prompt": {
                    "type": "fabric",
                    "path": "instructions.system.content",
                    "is_prompt": True,
                    "purpose": "Answer accurately.",
                }
            },
        },
    }
    with pytest.raises(OptimizeRouterError, match="does not support"):
        OptimizeRouter.dispatch_payload(payload, ctx=ctx)


def test_dispatch_rejects_non_string_backend_name(ctx: JobContext) -> None:
    payload = {
        "schema_version": "fabric.agent/v1alpha1",
        "optimizer": {
            "numeric": {"enabled": True, "backend": 123, "n_trials": 1},
            "eval_metrics": {
                "average_score": {"direction": "maximize", "weight": 1.0},
            },
            "search_space": {
                "temperature": {
                    "type": "fabric",
                    "path": "models.default.temperature",
                    "values": [0.0],
                },
            },
        },
    }

    with pytest.raises(OptimizeRouterError, match="must be a string"):
        OptimizeRouter.dispatch_payload(payload, ctx=ctx)


def test_dispatch_requires_enabled_backend(ctx: JobContext) -> None:
    payload = {"schema_version": "fabric.agent/v1alpha1", "optimizer": {}}
    with pytest.raises(OptimizeRouterError, match="No Tune backend selected"):
        OptimizeRouter.dispatch_payload(payload, ctx=ctx)


def test_phase_result_rejects_reserved_artifact_fields() -> None:
    result = OptimizationPhaseResult(
        phase=OptimizationPhase.PROMPT,
        backend="ga",
        status=OptimizationPhaseStatus.FAILED,
        optimized_payload={},
        artifacts={"status": {"path": "bad"}},
    )

    with pytest.raises(ValueError, match="reserved result field"):
        result.to_result_dict()


def test_backend_protocol_accepts_phase_only_backend() -> None:
    class PhaseOnlyBackend:
        name = "prompt-test"
        capabilities = OptimizationBackendCapabilities(phases=(OptimizationPhase.PROMPT,))

        def run_phase(
            self,
            request: OptimizationPhaseRequest,
            *,
            ctx: JobContext,
            sdk=None,  # noqa: ANN001
        ) -> OptimizationPhaseResult:
            del request, ctx, sdk
            return OptimizationPhaseResult(
                phase=OptimizationPhase.PROMPT,
                backend=self.name,
                status=OptimizationPhaseStatus.COMPLETED,
                optimized_payload={},
            )

    assert isinstance(PhaseOnlyBackend(), OptimizationBackend)
