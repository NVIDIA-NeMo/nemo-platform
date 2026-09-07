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

from typing import Any

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext

from nemo_optimization.backends.protocol import OptimizationBackend, OptimizationPhase, OptimizationPhaseRequest
from nemo_optimization.fabric import build_optimize_payload, require_fabric_agent_config
from nemo_optimization.registry import OptimizationBackendDiscoveryError, require_optimization_backend
from nemo_optimization.search_space import DEFAULT_PROMPT_BACKEND

DEFAULT_NUMERIC_BACKEND = "optuna"


class OptimizeRouterError(RuntimeError):
    """Raised when optimize routing fails."""


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
        backend_name, phase = _select_backend(payload)
        backend = _require_backend(backend_name, phase=phase)
        return backend.run_phase(
            OptimizationPhaseRequest(payload=payload, phase=phase),
            ctx=ctx,
            sdk=sdk,
        ).to_result_dict()

    @staticmethod
    def dispatch_payload(
        payload: dict[str, Any],
        *,
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict[str, Any]:
        """Route an already-merged Fabric payload (used by tests and future job types)."""
        require_fabric_agent_config(payload, label="optimize payload")
        backend_name, phase = _select_backend(payload)
        backend = _require_backend(backend_name, phase=phase)
        return backend.run_phase(
            OptimizationPhaseRequest(payload=payload, phase=phase),
            ctx=ctx,
            sdk=sdk,
        ).to_result_dict()


def _select_backend(payload: dict[str, Any]) -> tuple[str, OptimizationPhase]:
    optimizer = payload.get("optimizer")
    if not isinstance(optimizer, dict):
        raise OptimizeRouterError("optimizer section must be a mapping.")

    numeric = optimizer.get("numeric") or {}
    prompt = optimizer.get("prompt") or {}
    numeric_enabled = bool(numeric.get("enabled")) if isinstance(numeric, dict) else False
    prompt_enabled = bool(prompt.get("enabled")) if isinstance(prompt, dict) else False

    if prompt_enabled:
        return _backend_name(prompt, default=DEFAULT_PROMPT_BACKEND), OptimizationPhase.PROMPT
    if numeric_enabled:
        return _backend_name(numeric, default=DEFAULT_NUMERIC_BACKEND), OptimizationPhase.NUMERIC

    raise OptimizeRouterError(
        "No Tune backend selected. Set optimizer.numeric.enabled: true for numeric HPO "
        "(optimizer.prompt.enabled is not supported in this release)."
    )


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
