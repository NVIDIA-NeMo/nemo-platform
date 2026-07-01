# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared metric-reference resolution for evaluator jobs.

Both ``EvaluateJob`` (row/model eval) and ``AgentEvalJob`` accept metrics as a
mix of inline bundles and references to stored metrics. During ``to_spec`` those
must be resolved into canonical inline metrics — stored refs loaded from the
entity store, and any model references carried by ``MetricWithModels`` resolved
through the platform. This module is the one place that logic lives.
"""

from __future__ import annotations

import asyncio

from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.metric_refs import MetricRefOrInline, resolve_metric_specs
from nemo_evaluator.resolvers import ModelResolverSDK, PlatformModelResolver
from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundle,
    bundle_metric,
    metric_bundle_packager_for_payload,
    unbundle_metric,
)
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricWithModels
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform


def unresolved_model_refs(metrics: list[Metric]) -> list[str]:
    """Return the sorted model references still unresolved across the given metrics."""
    refs = [
        model_ref.root
        for item in metrics
        if isinstance(item, MetricWithModels)
        for model_ref in item.model_refs().values()
    ]
    return sorted(refs)


def to_inline(bundle: MetricBundle) -> MetricInline:
    """Project a runtime bundle onto the wire DTO (JSON round-trip keeps base64 consistent)."""
    return MetricInline.model_validate_json(bundle.model_dump_json())


def to_runtime_bundle(metric: MetricInline) -> MetricBundle:
    """Reconstruct the runtime bundle from a wire DTO for execution."""
    return MetricBundle.model_validate_json(metric.model_dump_json())


def _bundle_resolved_metric(metric: Metric, source_bundle: MetricBundle) -> MetricBundle:
    packager = metric_bundle_packager_for_payload(source_bundle.payload)
    resolved_bundle = bundle_metric(metric, packager)
    return resolved_bundle.model_copy(update={"metadata": source_bundle.metadata})


async def resolve_metrics_to_inline(
    metrics: list[MetricRefOrInline],
    *,
    workspace: str,
    entity_client: object,
    async_sdk: AsyncNeMoPlatform | NeMoPlatform | None,
) -> list[MetricInline]:
    """Resolve a wire metric list (inline + stored refs) into canonical inline metrics.

    Stored references are loaded from the entity store; any ``MetricWithModels``
    model references are resolved through the platform. Raises if a model
    reference is present without a usable ``async_sdk`` connection.

    ``async_sdk`` accepts either client because the call sites differ: submit forwards a real
    ``AsyncNeMoPlatform``, while local execution forwards the *sync* ``NeMoPlatform``. The two
    resolution concerns then have *different* client requirements:

    * **Stored-ref loading** awaits real platform file I/O (``resolve_metric_ref`` → ``load_bundle``
      → ``await sdk.files._download_file``), so it needs a genuine ``AsyncNeMoPlatform``. Anything
      else (``None`` or the sync client) is narrowed to ``None`` and rejected with a clear error when
      a stored ``MetricRef`` is actually present — never awaited blindly.
    * **Model-ref resolution** duck-types the client (``PlatformModelResolver`` tolerates sync or
      async via ``_maybe_await``), so it accepts anything conforming to ``ModelResolverSDK``; a
      non-conforming or absent client is rejected up front rather than failing deep in resolution.
    """
    files_sdk = async_sdk if isinstance(async_sdk, AsyncNeMoPlatform) else None
    resolved_bundles = await resolve_metric_specs(
        metrics,
        workspace=workspace,
        entity_client=entity_client,
        async_sdk=files_sdk,
    )
    runtime_metrics = [unbundle_metric(bundle) for bundle in resolved_bundles]
    final_bundles = resolved_bundles
    unresolved = unresolved_model_refs(runtime_metrics)
    if unresolved:
        if not isinstance(async_sdk, ModelResolverSDK):
            raise ValueError(
                "ModelRef metrics require a platform connection (models + inference) to resolve: "
                + ", ".join(unresolved)
            )
        resolver = PlatformModelResolver(async_sdk)
        await asyncio.gather(
            *(metric.resolve_models(resolver) for metric in runtime_metrics if isinstance(metric, MetricWithModels))
        )
        final_bundles = [
            _bundle_resolved_metric(metric, bundle)
            for metric, bundle in zip(runtime_metrics, resolved_bundles, strict=True)
        ]
    return [to_inline(bundle) for bundle in final_bundles]
