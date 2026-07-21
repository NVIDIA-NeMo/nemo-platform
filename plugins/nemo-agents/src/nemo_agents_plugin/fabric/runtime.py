# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Runtime execution helpers for Fabric-backed agents.

This module is the internal Platform boundary around Fabric SDK runtime
execution. It accepts already-translated in-memory FabricConfig objects and
normalizes Fabric runtime results/errors for Platform callers.

It intentionally does not own Platform agent config loading, FabricConfig
translation, CLI/API wiring, deploy semantics, or durable session management.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# CI type-checks this plugin via ty extra-paths without installing nemo-agents deps.
from nemo_fabric import Fabric, FabricConfig, FabricError, RunRequest, RunResult  # ty: ignore[unresolved-import]


@dataclass(frozen=True, slots=True)
class FabricRuntimeRequest:
    """Platform-owned request for one Fabric runtime invocation.

    This is an internal bridge type. The fields are intentionally close to
    Fabric's ``RunRequest`` while preserving Platform-owned lifecycle inputs
    such as ``base_dir`` and timeout policy.
    """

    fabric_config: FabricConfig
    base_dir: Path | str
    input: Any = ""
    request_id: str | None = None
    caller_context: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class FabricRuntimeStartRequest:
    """Platform-owned request for starting a managed Fabric runtime."""

    fabric_config: FabricConfig
    base_dir: Path | str
    overrides: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FabricRuntimeHandle:
    """Handle for a Fabric runtime kept alive by the Platform deployment backend."""

    # Deployment start/stop happen in separate controller cycles, so this stores
    # the async context manager that `async with await start_runtime(...)` would
    # normally enter and exit in one lexical block.
    runtime: Any
    context_manager: Any
    runtime_id: str | None = None


@dataclass(frozen=True, slots=True)
class FabricRuntimeResult:
    """Platform-normalized result for one Fabric runtime invocation.

    This internal shape preserves Fabric's correlation IDs separately so it can
    later map cleanly into Platform's ``AgentRun.output`` / ``RunOutput``.
    """

    status: str
    output: Any = None
    response: Any | None = None
    error: Any | None = None
    artifacts: Any | None = None
    telemetry: list[Any] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    runtime_id: str | None = None
    invocation_id: str | None = None
    request_id: str | None = None


class FabricRuntimeExecutionError(RuntimeError):
    """Raised when Fabric cannot return a normalized runtime result."""


class FabricRuntimeTimeoutError(FabricRuntimeExecutionError):
    """Raised when a Fabric runtime invocation exceeds the Platform timeout."""


async def start_fabric_agent_runtime(
    request: FabricRuntimeStartRequest,
    *,
    fabric: Any | None = None,
) -> FabricRuntimeHandle:
    """Start a managed Fabric runtime and return a handle that must be stopped."""
    fabric_client = fabric or Fabric()

    try:
        context_manager = await fabric_client.start_runtime(
            request.fabric_config,
            base_dir=request.base_dir,
            overrides=request.overrides,
        )
        runtime = await context_manager.__aenter__()
    except FabricError as error:
        raise FabricRuntimeExecutionError(f"Fabric runtime start failed: {error}") from error

    return FabricRuntimeHandle(
        runtime=runtime,
        context_manager=context_manager,
        runtime_id=getattr(runtime, "runtime_id", None),
    )


async def stop_fabric_agent_runtime(handle: FabricRuntimeHandle) -> None:
    """Stop a managed Fabric runtime previously returned by start_fabric_agent_runtime."""
    try:
        await handle.context_manager.__aexit__(None, None, None)
    except FabricError as error:
        raise FabricRuntimeExecutionError(f"Fabric runtime stop failed: {error}") from error


async def run_fabric_agent_once(
    request: FabricRuntimeRequest,
    *,
    fabric: Any | None = None,
) -> FabricRuntimeResult:
    """Start an ephemeral Fabric runtime, invoke it once, and stop it."""
    fabric_client = fabric or Fabric()

    try:
        result = await asyncio.wait_for(
            _invoke_fabric_agent_once(request, fabric=fabric_client),
            timeout=request.timeout_seconds,
        )
    except TimeoutError as error:
        raise FabricRuntimeTimeoutError(
            f"Fabric runtime invocation timed out after {request.timeout_seconds:g}s.",
        ) from error
    except FabricError as error:
        raise FabricRuntimeExecutionError(
            f"Fabric runtime invocation failed: {error}",
        ) from error

    return _normalize_fabric_run_result(result)


async def _invoke_fabric_agent_once(
    request: FabricRuntimeRequest,
    *,
    fabric: Any,
) -> RunResult:
    async with await fabric.start_runtime(
        request.fabric_config,
        base_dir=request.base_dir,
        overrides=request.overrides,
    ) as runtime:
        return await runtime.invoke(request=_with_platform_invocation_context(request))


def _with_platform_invocation_context(request: FabricRuntimeRequest) -> RunRequest:
    """Preserve Platform invocation metadata when calling Fabric."""
    request_kwargs: dict[str, Any] = {
        "context": request.caller_context,
        "input": request.input,
    }
    if request.request_id is not None:
        request_kwargs["request_id"] = request.request_id

    return RunRequest(**request_kwargs)


def _normalize_fabric_run_result(result: RunResult) -> FabricRuntimeResult:
    """Convert Fabric's SDK result into the Platform runtime result shape."""
    output = _to_plain_value(result.output)
    return FabricRuntimeResult(
        status=result.status,
        output=output,
        response=output.get("response") if isinstance(output, Mapping) else None,
        error=_to_plain_value(result.error),
        artifacts=_to_plain_value(result.artifacts),
        telemetry=_to_plain_value(result.telemetry),
        events=_to_plain_value(result.events),
        metadata=_to_plain_value(result.metadata),
        runtime_id=result.runtime_id,
        invocation_id=result.invocation_id,
        request_id=result.request_id,
    )


def _to_plain_value(value: Any) -> Any:
    """Convert Fabric SDK mapping objects into plain Platform-owned values."""
    if hasattr(value, "to_mapping"):
        return _to_plain_value(value.to_mapping())
    if isinstance(value, Mapping):
        return {key: _to_plain_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_to_plain_value(item) for item in value]
    return value
