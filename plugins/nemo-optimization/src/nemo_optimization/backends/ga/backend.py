# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prompt GA backend stub."""

from __future__ import annotations

import copy
import json
from typing import Any, ClassVar

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext

from nemo_optimization.backends.protocol import (
    OptimizationBackendCapabilities,
    OptimizationPhase,
    OptimizationPhaseRequest,
    OptimizationPhaseResult,
    OptimizationPhaseStatus,
)
from nemo_optimization.search_space import parse_prompt_optimizer_config

RESULT_NAME = "optimizer_results"


class GaBackendError(RuntimeError):
    """Raised when prompt GA is requested before the backend ships."""


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
        parse_prompt_optimizer_config(request.payload)
        message = (
            "optimizer.prompt.enabled is not supported yet. "
            "Prompt GA is tracked separately and will be implemented in the GA algorithm stack."
        )
        output_dir = ctx.storage.persistent / "results" / RESULT_NAME
        output_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "status": OptimizationPhaseStatus.FAILED.value,
            "backend": self.name,
            "phase": OptimizationPhase.PROMPT.value,
            "error": message,
        }
        (output_dir / "prompt_phase_failure.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        ref = ctx.results.save(RESULT_NAME, output_dir)
        return OptimizationPhaseResult(
            phase=OptimizationPhase.PROMPT,
            backend=self.name,
            status=OptimizationPhaseStatus.FAILED,
            optimized_payload=copy.deepcopy(request.payload),
            summary={"error": message},
            artifacts={"result": ref.model_dump(mode="json")},
            trial_count=0,
            trial_number_offset=request.trial_number_offset,
        )
