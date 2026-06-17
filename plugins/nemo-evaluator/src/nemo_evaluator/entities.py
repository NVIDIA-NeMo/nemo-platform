# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stored metric entity for the evaluator plugin.

A :class:`MetricBundleEntity` is the persisted, queryable index for a metric.
The full executable :class:`~nemo_evaluator.shared.metric_bundles.bundles.MetricBundle`
(including its potentially multi-MiB serialized payload) lives in the Files
service; the entity stores only the lightweight, searchable projection plus a
reference (``bundle_ref``) and integrity digest (``payload_digest``) that point
back at the canonical copy.
"""

from __future__ import annotations

from typing import ClassVar

from nemo_evaluator.shared.metric_bundles.bundles import BundledMetricOutputSpec
from nemo_evaluator_sdk.values.common import SecretRef
from nemo_platform_plugin.entities import EntityBase
from pydantic import Field

# Constants are intentionally local: nmp_common's entity constants are not
# re-exported to plugins. Keep these aligned with
# ``nmp.common.entities.constants``.
MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 1000
NAME_PATTERN = r"^[\w\-\.]+$"


class MetricBundleEntity(EntityBase):
    """Persisted index for a stored metric, addressed by workspace/name.

    The canonical, executable bundle is stored in the Files service and
    referenced by ``bundle_ref``; the fields here are a denormalized projection
    kept for display and filtering without downloading the payload.
    """

    __entity_type__: ClassVar[str] = "metric_bundle"

    metric_type: str = Field(
        description="Runtime metric type name captured from the bundled metric.",
        max_length=MAX_NAME_LENGTH,
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="Labels captured from the bundled metric's metadata.",
    )
    outputs: list[BundledMetricOutputSpec] = Field(
        default_factory=list,
        description="JSON-safe projection of the metric's output contracts.",
    )
    secrets: dict[str, SecretRef] = Field(
        default_factory=dict,
        description="Secret environment-variable references required to execute the metric.",
    )
    payload_kind: str = Field(
        description="Payload discriminator of the stored bundle (e.g. 'cloudpickle').",
        max_length=MAX_NAME_LENGTH,
    )
    payload_digest: str = Field(
        description="Format-specific digest of the stored payload, used to verify integrity on load.",
        max_length=MAX_NAME_LENGTH,
    )
    bundle_ref: str = Field(
        description="Files reference to the canonical serialized MetricBundle (format: workspace/fileset#path).",
    )
    description: str | None = Field(
        default=None,
        description="Description captured from the bundled metric's metadata.",
        max_length=MAX_DESCRIPTION_LENGTH,
    )
