# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""References to persisted metrics and their resolution into executable bundles.

A :class:`MetricRef` lets an evaluation job point at a stored metric by
``workspace/name`` instead of inlining it. During spec resolution (``to_spec``),
references are loaded from storage and inline :class:`MetricInline` DTOs are
converted, so the canonical job spec and execution path only ever see runtime
:class:`MetricBundle` objects.
"""

from __future__ import annotations

from typing import Any

from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.entities import MetricBundleEntity
from nemo_evaluator.metric_storage import load_bundle
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundle
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.entities import EntityNotFoundError
from pydantic import Field, RootModel

# A reference is ``name`` or ``workspace/name``, each segment using the platform
# name charset. Enforced on the field so empty/malformed refs are rejected at
# validation time rather than during parsing.
_METRIC_REF_PATTERN = r"^[\w\-.]+(/[\w\-.]+)?$"


class MetricRef(RootModel[str]):
    """Reference to a persisted metric (format: ``workspace/name`` or ``name``)."""

    root: str = Field(
        pattern=_METRIC_REF_PATTERN,
        description="Reference to a stored metric (format: workspace/metric-name, or metric-name in the job workspace).",
    )


def parse_metric_ref(root: str, default_workspace: str) -> tuple[str, str]:
    """Split a validated metric reference into ``(workspace, name)``.

    The ``workspace/name`` vs bare-``name`` shape is guaranteed by
    :class:`MetricRef`'s field pattern, so this only needs to split.
    """
    workspace, separator, name = root.partition("/")
    if separator:
        return workspace, name
    return default_workspace, root


async def resolve_metric_ref(
    ref: MetricRef,
    *,
    workspace: str,
    entity_client: Any,
    async_sdk: AsyncNeMoPlatform | None,
) -> MetricBundle:
    """Load and reconstruct the stored metric a reference points at."""
    if entity_client is None or async_sdk is None:
        raise ValueError(
            "MetricRef metrics require a platform connection (entity store and async SDK) to resolve; "
            "they cannot be used in local execution. Pass an inline metric instead."
        )
    ref_workspace, name = parse_metric_ref(ref.root, workspace)
    try:
        entity = await entity_client.get(MetricBundleEntity, name=name, workspace=ref_workspace)
    except EntityNotFoundError as exc:
        raise ValueError(
            f"Metric reference '{ref.root}' not found. "
            f"Ensure a stored metric named '{name}' exists in workspace '{ref_workspace}', "
            "or pass an inline metric instead."
        ) from exc
    return await load_bundle(async_sdk, entity.bundle_ref, expected_digest=entity.payload_digest)


async def resolve_metric_specs(
    metrics: list[MetricInline | MetricRef],
    *,
    workspace: str,
    entity_client: Any,
    async_sdk: AsyncNeMoPlatform | None,
) -> list[MetricBundle]:
    """Resolve a wire metric list into runtime bundles.

    References are loaded from storage; inline :class:`MetricInline` DTOs are
    converted to runtime bundles by JSON round-trip (which keeps the base64
    payload encoding consistent).
    """
    resolved: list[MetricBundle] = []
    for item in metrics:
        if isinstance(item, MetricRef):
            resolved.append(
                await resolve_metric_ref(
                    item,
                    workspace=workspace,
                    entity_client=entity_client,
                    async_sdk=async_sdk,
                )
            )
        else:
            resolved.append(MetricBundle.model_validate_json(item.model_dump_json()))
    return resolved
