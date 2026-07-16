# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Synchronous evaluate route — the HTTP equivalent of `nemo evaluator evaluate run`.

Scoped to what is safe in the long-lived API process: offline, inline metrics over inline rows,
models by platform ModelRef only. Heavier or untrusted work goes through `/evaluate/jobs`.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import logging
import threading
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.authz import scope
from nemo_evaluator.jobs.evaluate import EvaluationArtifactResult, run_evaluation, to_runtime_bundle
from nemo_evaluator.resolvers import PlatformModelResolver
from nemo_evaluator.shared.metric_bundles.bundles import unbundle_metric
from nemo_evaluator_sdk import inference as sdk_inference
from nemo_evaluator_sdk.enums import MetricType
from nemo_evaluator_sdk.execution.config import resolve_params
from nemo_evaluator_sdk.execution.values import EvaluationError
from nemo_evaluator_sdk.inference import InferenceFn
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricWithModels
from nemo_evaluator_sdk.metrics.ragas.base import BaseRAGASMetric
from nemo_evaluator_sdk.values import FieldMapping, Model, RunConfig
from nemo_evaluator_sdk.values.models import ModelRef
from nemo_evaluator_sdk.values.multi_metric_results import BenchmarkEvaluationResult
from nemo_evaluator_sdk.values.params import InferenceParams
from nemo_evaluator_sdk.values.results import EvaluationResult
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.authz import CallerKind, PermissionSet, path_rule, perm
from nemo_platform_plugin.dependencies import get_sdk_client
from nemo_platform_plugin.sdk_provider import get_forwarding_headers
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class EvaluateSyncPerms(PermissionSet, namespace="evaluator.evaluate"):
    """Permission for the synchronous evaluate execution route."""

    EXEC = perm("Execute synchronous evaluator evaluations")


MAX_SYNC_ROWS = 10
MAX_SYNC_METRICS = 10
SYNC_EVALUATE_TIMEOUT_SECONDS = 60.0

_SYNC_EVAL_MAX_WORKERS = 4
# Capped low so a detached (timed-out) worker's slot occupancy stays near the request timeout.
_SYNC_WORKER_MAX_RETRIES = 1

# Metric types that call a user-supplied URL during evaluation (SSRF surface).
_NETWORK_BACKED_METRIC_TYPES = frozenset({MetricType.REMOTE.value, MetricType.NEMO_AGENT_TOOLKIT_REMOTE.value})

# Released from the worker's done callback (worker thread), so it can't depend on any event loop.
_SYNC_SLOTS = threading.BoundedSemaphore(_SYNC_EVAL_MAX_WORKERS)

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


def _has_inline_model(value: object) -> bool:
    """True if an inline Model (vs a platform ModelRef) appears anywhere in a metric's fields."""
    if isinstance(value, Model):
        return True
    if isinstance(value, BaseModel):
        return any(_has_inline_model(field_value) for field_value in vars(value).values())
    if isinstance(value, dict):
        return any(_has_inline_model(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_has_inline_model(item) for item in value)
    return False


def _bounded_inference_fn(budget_seconds: float) -> InferenceFn:
    """Inference fn that caps per-request timeout and retries at the sync budget."""

    async def _fn(
        model: Model,
        request: dict,
        max_retries: int | None = None,
        *,
        client: AsyncOpenAI | None = None,
        api_key: str | None = None,
        default_headers: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        # Attribute access (not a bound import) so a patched make_inference_request still applies.
        return await sdk_inference.make_inference_request(
            model,
            request,
            min(max_retries if max_retries is not None else _SYNC_WORKER_MAX_RETRIES, _SYNC_WORKER_MAX_RETRIES),
            client=client,
            api_key=api_key,
            default_headers=default_headers,
            timeout=timeout if timeout is not None else budget_seconds,
        )

    return _fn


# RAGAS builds its judge ChatOpenAI client from `inference` (extra="allow"); only these
# generation params survive the sync path, so a caller can't smuggle transport/auth kwargs.
_ALLOWED_RAGAS_INFERENCE_KEYS = frozenset({"temperature", "max_tokens", "max_completion_tokens", "top_p", "stop"})


def _bound_worker_inference(metrics: list[Metric], budget_seconds: float) -> None:
    """Cap each metric's model calls at the sync budget so a detached worker frees its slot fast."""
    for metric in metrics:
        set_inference_fn = getattr(metric, "set_inference_fn", None)
        if callable(set_inference_fn):
            set_inference_fn(_bounded_inference_fn(budget_seconds))
        if isinstance(metric, BaseRAGASMetric):
            _sanitize_ragas_inference(metric, budget_seconds)


def _sanitize_ragas_inference(metric: BaseRAGASMetric, budget_seconds: float) -> None:
    """Drop caller transport/auth kwargs (forced from the resolved model) and clamp timeout/retries."""
    inference = getattr(metric, "inference", None)
    if not isinstance(inference, InferenceParams):
        return

    dumped = inference.model_dump(exclude_none=True)
    safe = {key: value for key, value in dumped.items() if key in _ALLOWED_RAGAS_INFERENCE_KEYS}

    existing_timeout = dumped.get("request_timeout")
    safe["request_timeout"] = min(existing_timeout, budget_seconds) if existing_timeout else budget_seconds
    existing_retries = dumped.get("max_retries")
    safe["max_retries"] = (
        min(existing_retries, _SYNC_WORKER_MAX_RETRIES) if existing_retries is not None else _SYNC_WORKER_MAX_RETRIES
    )

    # Set dynamically: inference lives on the RAGAS judge-config mixin, not the base. Applied
    # before resolve_models() re-runs _configure_models(), so RAGAS builds its client from these.
    setattr(metric, "inference", InferenceParams(**safe))


def _submit_sync_evaluation(run: Callable[[], EvaluationArtifactResult]) -> concurrent.futures.Future:
    """Run on a daemon thread (returns a Future) so a stuck eval can't block SIGTERM shutdown."""
    future: concurrent.futures.Future = concurrent.futures.Future()

    def _worker() -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(run())
        except BaseException as exc:  # noqa: BLE001 — the future is the error channel
            future.set_exception(exc)

    threading.Thread(target=_worker, name="evaluator-sync", daemon=True).start()
    return future


class EvaluateSyncError(BaseModel):
    """Error body for the synchronous evaluate route (422/503/504)."""

    detail: str = Field(description="Human-readable, actionable description of why the request failed.")


class EvaluateSyncRequest(BaseModel):
    """Bounded offline evaluation request: inline metrics over inline rows, models by ModelRef.

    See the handler for the inputs it rejects (online targets, inline models, secrets, cloudpickle,
    network metrics).
    """

    model_config = ConfigDict(extra="forbid")

    metrics: Annotated[
        list[MetricInline],
        Field(min_length=1, max_length=MAX_SYNC_METRICS, description="Inline metrics to evaluate."),
    ]
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
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": EvaluateSyncError,
            "description": "Invalid request or unsupported metric/model",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": EvaluateSyncError,
            "description": "Synchronous evaluation capacity is full",
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": EvaluateSyncError,
            "description": "Evaluation exceeded the synchronous time limit",
        },
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
        # Allow-list, not deny-list: any future payload kind fails closed.
        if metric.payload.kind != "inline":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Synchronous evaluation supports inline (built-in) metrics only, "
                    f"not '{metric.payload.kind}' payloads. Submit them as a durable job via /evaluate/jobs."
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

    # Cheap request-shape validation — no slot held, no remote calls.
    try:
        runtime_metrics = [unbundle_metric(to_runtime_bundle(metric)) for metric in request.metrics]

        # Inline models carry an arbitrary URL/secret (SSRF); require a ModelRef.
        for runtime_metric in runtime_metrics:
            if _has_inline_model(runtime_metric):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Metric models must be platform references (workspace/model). Inline model "
                        "definitions are not allowed on the synchronous path; submit a durable job."
                    ),
                )

        params = resolve_params(request.params, None)
    except HTTPException:
        raise
    except (TypeError, ValueError, EvaluationError) as exc:
        logger.warning("Synchronous evaluation request was invalid", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Evaluation request was invalid: {exc}",
        ) from exc

    # Reserve capacity before model resolution so backpressure gates its remote lookups.
    if not _SYNC_SLOTS.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Synchronous evaluation capacity is full; retry shortly or submit a durable job via /evaluate/jobs.",
        )

    slot_held = True
    try:
        try:
            _bound_worker_inference(runtime_metrics, SYNC_EVALUATE_TIMEOUT_SECONDS)

            # Resolve refs as the caller (forward request-scoped headers).
            metrics_with_models = [m for m in runtime_metrics if isinstance(m, MetricWithModels)]
            if metrics_with_models:
                resolver = _ForwardedHeaderModelResolver(
                    PlatformModelResolver(async_sdk), get_forwarding_headers(async_sdk)
                )
                await asyncio.gather(*(m.resolve_models(resolver) for m in metrics_with_models))
        except (TypeError, ValueError, EvaluationError) as exc:
            logger.warning("Synchronous evaluation request was invalid", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Evaluation request was invalid: {exc}",
            ) from exc

        future = _submit_sync_evaluation(
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
        # Slot ownership passes to the done callback (fires on true completion, so a timed-out
        # run can't oversubscribe). Clear slot_held first: an already-done future runs the
        # callback inline, and a double release trips BoundedSemaphore.
        slot_held = False
        future.add_done_callback(lambda _f: _SYNC_SLOTS.release())
    finally:
        if slot_held:
            _SYNC_SLOTS.release()

    # asyncio.wait (not wait_for): not-done is the only timeout signal, so a worker-raised
    # TimeoutError isn't mistaken for the sync budget expiring.
    wrapped = asyncio.wrap_future(future)
    done, _ = await asyncio.wait({wrapped}, timeout=SYNC_EVALUATE_TIMEOUT_SECONDS)
    if not done:
        logger.warning(
            "Synchronous evaluation exceeded %.0fs; worker keeps its slot until its bounded inference calls finish.",
            SYNC_EVALUATE_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                f"Synchronous evaluation exceeded {SYNC_EVALUATE_TIMEOUT_SECONDS:.0f}s. "
                "Submit as a durable job via /evaluate/jobs instead."
            ),
        )

    try:
        return wrapped.result()
    except EvaluationError as exc:
        # Caller-actionable; internal TypeError/ValueError bugs stay 500s below.
        logger.warning("Synchronous evaluation failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Evaluation failed: {exc}",
        ) from exc
    except Exception:
        logger.exception("Synchronous evaluation failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
