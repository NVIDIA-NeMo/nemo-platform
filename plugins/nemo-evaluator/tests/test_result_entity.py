# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Serialization round-trip tests for the eval-result entities.

The entity store persists an entity's custom fields with
``model_dump(exclude=base, mode="json")`` into a JSON column and rebuilds it with
``model_validate``. These tests exercise that exact round-trip (which the in-memory fakes elsewhere
bypass) to guard the aggregated ``scores`` rollup and the row-eval input refs that carry nested types.
"""

from __future__ import annotations

import json
from typing import TypeVar

import pytest
from nemo_evaluator.entities import AgentEvalResultEntity, EvaluateResultEntity
from nemo_evaluator_sdk.values.results import AggregatedMetricResult, AggregateRangeScore
from pydantic import ValidationError

# Constrained (not bound) so _E resolves to a concrete entity — which has EntityBase's name/workspace/
# __base_fields__ plus its own result fields — rather than the abstract _EvalResultCommon mixin.
_E = TypeVar("_E", AgentEvalResultEntity, EvaluateResultEntity)


def _scores() -> AggregatedMetricResult:
    return AggregatedMetricResult(scores=[AggregateRangeScore(name="accuracy", count=10, nan_count=0, mean=0.9)])


def _roundtrip(entity: _E) -> _E:
    """Mirror the entity store: dump custom fields to JSON, prove it's JSON-safe, then rebuild."""
    cls = type(entity)
    data = entity.model_dump(exclude=cls.__base_fields__, exclude_computed_fields=True, mode="json")
    data = json.loads(json.dumps(data))
    return cls.model_validate({"name": entity.name, "workspace": entity.workspace, **data})


def test_agent_eval_result_roundtrip_preserves_scores_and_target() -> None:
    entity = AgentEvalResultEntity(
        name="job-123",
        workspace="default",
        job_id="job-123",
        target_kind="codex",
        target_name="gpt-5.5",
        target_url=None,
        scores=_scores(),
        bundle_ref="fileset://default/agent-eval-results#bundle",
    )

    restored = _roundtrip(entity)

    assert restored.job_id == "job-123"
    assert restored.target_kind == "codex"
    assert restored.target_name == "gpt-5.5"
    assert restored.target_url is None
    assert restored.bundle_ref == entity.bundle_ref
    # The nested AggregatedMetricResult must survive the JSON column intact.
    assert restored.scores == entity.scores
    assert restored.scores.scores[0].mean == 0.9


def test_evaluate_result_roundtrip_preserves_dataset_and_metric_types() -> None:
    entity = EvaluateResultEntity(
        name="job-456",
        workspace="default",
        job_id="job-456",
        target_kind="model",
        target_name="my-model",
        target_url="https://model.test/v1/chat/completions",
        scores=_scores(),
        bundle_ref="fileset://default/eval-results#bundle",
        dataset_ref="default/my-dataset",
        metric_types=["exact_match", "string_check"],
    )

    restored = _roundtrip(entity)

    assert restored.dataset_ref == "default/my-dataset"
    assert restored.metric_types == ["exact_match", "string_check"]
    assert restored.target_url == "https://model.test/v1/chat/completions"
    assert restored.scores == entity.scores


def test_entity_types_are_distinct() -> None:
    # Distinct __entity_type__ keeps the two collections from colliding in the store.
    assert AgentEvalResultEntity.__entity_type__ == "agent_eval_result"
    assert EvaluateResultEntity.__entity_type__ == "evaluate_result"
    assert AgentEvalResultEntity.__entity_type__ != EvaluateResultEntity.__entity_type__


def test_shared_fields_are_required() -> None:
    # A result is only persisted once the run produced all of it — no schema defaults papering over
    # missing data. job_id (and the rest of the shared record) must be supplied by the caller.
    with pytest.raises(ValidationError):
        AgentEvalResultEntity(name="x", workspace="default", scores=_scores())  # ty: ignore[missing-argument]
