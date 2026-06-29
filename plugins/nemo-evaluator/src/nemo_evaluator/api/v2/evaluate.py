# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Synchronous evaluate route — the HTTP equivalent of `nemo evaluator evaluate run`.

Scoped to what is safe in the long-lived API process: offline, inline metrics over inline rows,
models by platform ModelRef only. Heavier or untrusted work goes through `/evaluate/jobs`.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.authz import scope
from nemo_evaluator.jobs.evaluate import run_evaluation, to_runtime_bundle
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.shared.metric_bundles.bundles import unbundle_metric
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.execution.config import resolve_params
from nemo_evaluator_sdk.execution.values import EvaluationError
from nemo_evaluator_sdk.metrics.protocol import MetricWithModels
from nemo_evaluator_sdk.values import FieldMapping, Model, RunConfig
from nemo_evaluator_sdk.values.models import ModelRef
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.results import EvaluationResult
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.authz import CallerKind, PermissionSet, path_rule, perm
from nemo_platform_plugin.dependencies import get_sdk_client
from nemo_platform_plugin.sdk_provider import get_forwarding_headers
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class EvaluateSyncPerms(PermissionSet, namespace="evaluator.evaluate"):
    """Permission for the synchronous evaluate execution route."""

    EXEC = perm("Execute synchronous evaluator evaluations")


MAX_SYNC_ROWS = 10
SYNC_EVALUATE_TIMEOUT_SECONDS = 60.0

# Dedicated bounded pool so a stuck (uncancellable) sync eval can't starve the main request pool.
_SYNC_EVAL_MAX_WORKERS = 4
_SYNC_EVAL_EXECUTOR = ThreadPoolExecutor(max_workers=_SYNC_EVAL_MAX_WORKERS, thread_name_prefix="evaluator-sync")

# Metric types that call a user-supplied URL during evaluation (SSRF surface).
_NETWORK_BACKED_METRIC_TYPES = frozenset({MetricType.REMOTE.value, MetricType.NEMO_AGENT_TOOLKIT_REMOTE.value})

router = APIRouter()


class _ForwardedHeaderModelResolver:
    """Resolve a ModelRef to its IGW Model, stamping the caller's request-scoped headers on it so
    the in-process call runs as the caller with no secret."""

    def __init__(self, inner: PlatformModelResolver, headers: dict[str, str]) -> None:
        self._inner = inner
        self._headers = headers

    async def resolve_model(self, model_ref: ModelRef) -> Model:
        model = await self._inner.resolve_model(model_ref)
        return model.with_default_headers(self._headers)


class _SlotCounter:
    """In-flight counter for sync-eval backpressure; mutated only on the event-loop thread."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._in_flight = 0

    def try_acquire(self) -> bool:
        if self._in_flight >= self._limit:
            return False
        self._in_flight += 1
        return True

    def release(self) -> None:
        self._in_flight = max(0, self._in_flight - 1)


_SYNC_SLOTS = _SlotCounter(_SYNC_EVAL_MAX_WORKERS)


def _has_inline_model(metric: object) -> bool:
    """True if any top-level metric field is an inline Model (vs a platform ModelRef)."""
    return any(isinstance(value, Model) for value in vars(metric).values())


class EvaluateSyncRequest(BaseModel):
    """Bounded offline evaluation request: inline metrics over inline rows, models by ModelRef.

    See the handler for the inputs it rejects (online targets, inline models, secrets, cloudpickle,
    network metrics).
    """

    model_config = ConfigDict(extra="forbid")

    metrics: Annotated[list[MetricInline], Field(min_length=1, description="Inline metrics to evaluate.")]
    dataset: Annotated[
        list[dict[str, Any]],
        Field(min_length=1, max_length=MAX_SYNC_ROWS, description="Inline dataset rows to evaluate."),
    ]
    params: RunConfig | None = Field(default=None, description="Optional offline execution parameters.")
    field_mapping: FieldMapping | None = Field(
        default=None, description="Optional mapping from canonical evaluator fields to dataset columns."
    )


@router.post(
    "/evaluate",
    summary="Evaluate Synchronously",
    response_description="The inline evaluation result (aggregate and row scores)",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Invalid request or unsupported metric/model"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Synchronous evaluation capacity is full"},
        status.HTTP_504_GATEWAY_TIMEOUT: {"description": "Evaluation exceeded the synchronous time limit"},
    },
)
@scope.write
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[EvaluateSyncPerms.EXEC])
async def evaluate_sync(
    workspace: str,
    request: EvaluateSyncRequest,
    async_sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
) -> EvaluationResult | BenchmarkEvaluationResult:
    """Run a bounded offline evaluation in-process and return the result."""
    del workspace  # route is workspace-scoped for authz only

    for metric in request.metrics:
        if metric.payload.kind == "cloudpickle":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Synchronous evaluation supports inline (built-in) metrics only. "
                    "Submit cloudpickle metric bundles as a durable job via /evaluate/jobs."
                ),
            )
        if metric.metric_type in _NETWORK_BACKED_METRIC_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Metric type '{metric.metric_type}' calls an external endpoint and is not "
                    "allowed on the synchronous path. Submit it as a durable job via /evaluate/jobs."
                ),
            )
        if metric.secrets:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Metrics with secret references are not allowed on the synchronous path. "
                    "Reference a platform-registered model (workspace/model) or submit a durable job."
                ),
            )

    try:
        runtime_metrics = [unbundle_metric(to_runtime_bundle(metric)) for metric in request.metrics]

        # An inline model's URL/secret would SSRF/exfiltrate from the API process; require a ModelRef.
        for runtime_metric in runtime_metrics:
            if _has_inline_model(runtime_metric):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Metric models must be platform references (workspace/model). Inline model "
                        "definitions are not allowed on the synchronous path; submit a durable job."
                    ),
                )

        # Resolve refs as the caller (forward request-scoped headers); skip when no metric uses a model.
        metrics_with_models = [m for m in runtime_metrics if isinstance(m, MetricWithModels)]
        if metrics_with_models:
            resolver = _ForwardedHeaderModelResolver(
                PlatformModelResolver(async_sdk), get_forwarding_headers(async_sdk)
            )
            await asyncio.gather(*(m.resolve_models(resolver) for m in metrics_with_models))

        params = resolve_params(request.params, None)

        if not _SYNC_SLOTS.try_acquire():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Synchronous evaluation capacity is full; retry shortly or submit a durable job via /evaluate/jobs.",
            )
        loop = asyncio.get_running_loop()
        future = _SYNC_EVAL_EXECUTOR.submit(
            functools.partial(
                run_evaluation,
                metrics=runtime_metrics,
                dataset=request.dataset,
                params=params,
                target=None,
                prompt_template=None,
                field_mapping=request.field_mapping,
            )
        )
        # Free the slot only on true completion, so an orphaned (timed-out) run can't oversubscribe.
        future.add_done_callback(lambda _f: loop.call_soon_threadsafe(_SYNC_SLOTS.release))
        result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=SYNC_EVALUATE_TIMEOUT_SECONDS)
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.warning(
            "Synchronous evaluation exceeded %.0fs; worker may still be running.", SYNC_EVALUATE_TIMEOUT_SECONDS
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                f"Synchronous evaluation exceeded {SYNC_EVALUATE_TIMEOUT_SECONDS:.0f}s. "
                "Submit as a durable job via /evaluate/jobs instead."
            ),
        )
    except (TypeError, ValueError, EvaluationError):
        logger.warning("Synchronous evaluation could not be completed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Evaluation request was invalid or could not be completed.",
        )
    except Exception:
        logger.exception("Synchronous evaluation failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

    return result
