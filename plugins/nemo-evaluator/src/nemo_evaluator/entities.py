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
from nemo_evaluator_sdk.values.results import AggregatedMetricResult
from nemo_platform_plugin.entities import EntityBase
from pydantic import BaseModel, Field

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


# --- Eval result entities ----------------------------------------------------
#
# A result entity is the persisted, *queryable* record of one eval run: the
# aggregated scores plus the traits you'd filter on (target, dataset). The
# detailed per-row / per-trial output that doesn't fit a concise record stays in
# the run's fileset bundle, referenced here by ``bundle_ref``. The entity — not
# Intake — is the evaluator's source of truth; Intake is a denormalized, optional
# downstream copy.
#
# Both result types share the SAME record (``_EvalResultCommon``): provenance, the target it ran
# against, the aggregated ``scores`` rollup, and a ``bundle_ref`` to the full detail. They differ
# only where the domain genuinely differs — row-eval has *referenceable inputs* (its dataset fileset
# + metric refs), which the entity records; agent-eval's tasks are inline, so it has no input ref yet
# (the "Taskset" gap). Run counts / per-metric coverage are derivable rollups that live in the
# bundle's summary, not on the record. This keeps the two entities aligned and matches the lean legacy
# ``BaseJobResult`` → ``MetricJobResult`` / ``BenchmarkJobResult`` shape (refs + scores).


class _EvalResultCommon(BaseModel):
    """Fields shared by every persisted eval-result record (aggregates + filterable traits).

    A mixin (not itself an ``EntityBase``) so the concrete result entities can each declare their own
    ``__entity_type__`` — same split as the legacy ``BaseJobResult`` → ``MetricJobResult`` /
    ``BenchmarkJobResult``.

    Every field is required — a result is only persisted once the run has produced all of it, so the
    caller populates each value (no schema defaults papering over missing data). "What it ran
    against" is denormalized into flat ``target_*`` fields so the list route can filter by them (the
    entity filter matches top-level fields; a nested object wouldn't filter cleanly); they're nullable
    because an offline run (precomputed trials) has no target, but the caller must still pass them.

    (``labels`` and a run ``status`` are intentionally absent: there's no labels source on the spec
    yet, and persistence happens only on success — both would be schema defaults with no real data.
    Add them when there's a source — labels alongside a spec ``labels`` field, status if/when partial
    or failed runs are persisted.)
    """

    job_id: str = Field(description="Identifier of the job run that produced this result (one result per run).")
    target_kind: str | None = Field(
        description="Target discriminator: 'model', 'agent', or a runner kind e.g. 'codex'."
    )
    target_name: str | None = Field(description="Model/agent entity name, or the runner's model — filterable trait.")
    target_url: str | None = Field(description="Endpoint URL, when the target is an HTTP model/agent.")
    scores: AggregatedMetricResult = Field(
        description="Aggregated metric scores for the run (the concise, queryable rollup)."
    )
    bundle_ref: str = Field(
        description="Reference to the full result bundle in the Files service (rows/trials), e.g. a 'fileset://...' URL.",
    )


class AgentEvalResultEntity(_EvalResultCommon, EntityBase):
    """Persisted, queryable record of an ``AgentEvalJob`` run.

    Carries only the shared record — its tasks are inline, so (unlike row-eval) it has no input ref
    to record yet. Trials, per-metric coverage, and run counts live in the bundle's summary.
    """

    __entity_type__: ClassVar[str] = "agent_eval_result"


class EvaluateResultEntity(_EvalResultCommon, EntityBase):
    """Persisted, queryable record of an ``EvaluateJob`` (row-eval) run.

    Adds the run's *referenceable inputs* — the evaluated dataset and the metrics applied — which the
    shared record can't capture. Row-level detail lives in the bundle.
    """

    __entity_type__: ClassVar[str] = "evaluate_result"

    dataset_ref: str | None = Field(
        description="Reference to the dataset evaluated (e.g. 'workspace/fileset'); None for an inline dataset."
    )
    metric_types: list[str] = Field(
        description="Runtime metric type names applied in the run (e.g. 'exact_match'). Not metric refs: "
        "by run time the submitted refs are resolved to inline bundles, so the originals aren't available."
    )
