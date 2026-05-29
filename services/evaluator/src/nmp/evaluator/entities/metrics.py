# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Metric entity types for the evaluator service.

This module contains the persisted metric types that inherit from EntityBase.
The inline metric types (no workspace/name) are defined in values/app.py.
"""

from __future__ import annotations

from typing import Annotated, Union

import nmp.evaluator.app.values as app
from nemo_evaluator_sdk.values import metrics
from nmp.common.api.common import SecretRef as ApiSecretRef
from nmp.common.entities import SYSTEM_WORKSPACE
from nmp.common.entities.client import EntityBase
from nmp.evaluator.api.v2.common.inline_models import Model
from pydantic import BaseModel, Field

# =============================================================================
# System Metric Types
# =============================================================================


class SystemMetric(app.SystemMetric, EntityBase):
    workspace: str = Field(default=SYSTEM_WORKSPACE)


# =============================================================================
# Field-override mixins
#
# Entity types appear in the public OpenAPI surface (for example via
# Benchmark.metrics). They must use the strict service `ApiSecretRef` and the
# wrapper `Model` from `inline_models`, not the relaxed SDK types — otherwise
# the SDK's broader `SecretRef` pattern leaks into the spec. Mixins (rather
# than per-class re-annotations) preserve the parent's field metadata
# (`description`, `examples`) which Pydantic v2 does not inherit on
# annotation-only overrides.
# =============================================================================


class WithModel(BaseModel):
    model: Model = Field(
        description=metrics.LLMJudge.model_fields["model"].description,
        examples=metrics.LLMJudge.model_fields["model"].examples,
    )


class WithJudgeModel(BaseModel):
    judge_model: Model = Field(description=metrics.TopicAdherence.model_fields["judge_model"].description)


class WithEmbeddingsModel(BaseModel):
    embeddings_model: Model = Field(description=metrics.ResponseRelevancy.model_fields["embeddings_model"].description)


class WithApiKeySecret(BaseModel):
    api_key_secret: ApiSecretRef | None = Field(
        default=None,
        description=metrics.Remote.model_fields["api_key_secret"].description,
    )


# =============================================================================
# Persisted Metric Types (with workspace/name from EntityBase)
#
# These inherit from the SDK types + EntityBase to add persistence fields.
# Each `With*` mixin must come BEFORE the SDK base in the MRO so its field
# annotation shadows the parent's.
# =============================================================================


class BLEUMetric(metrics.BLEU, EntityBase):
    """Persisted BLEU metric."""

    pass


class ExactMatchMetric(metrics.ExactMatch, EntityBase):
    """Persisted Exact Match metric."""

    pass


class F1Metric(metrics.F1, EntityBase):
    """Persisted F1 metric."""

    pass


class LLMJudgeMetric(WithModel, metrics.LLMJudge, EntityBase):
    """Persisted LLM-as-a-Judge metric."""

    prompt_template: str | dict = Field(
        default_factory=lambda data: metrics.default_judge_prompt_template_for_model(data["model"]),
        description=metrics.LLMJudge.model_fields["prompt_template"].description,
        examples=metrics.LLMJudge.model_fields["prompt_template"].examples,
    )


class NumberCheckMetric(metrics.NumberCheck, EntityBase):
    """Persisted number check metric."""

    pass


class RemoteMetric(WithApiKeySecret, metrics.Remote, EntityBase):
    """Persisted Remote metric."""

    pass


class NemoAgentToolkitRemoteMetric(WithApiKeySecret, metrics.NemoAgentToolkitRemote, EntityBase):
    """Persisted NeMo Agent Toolkit Remote metric."""

    pass


class ROUGEMetric(metrics.ROUGE, EntityBase):
    """Persisted ROUGE metric."""

    pass


class StringCheckMetric(metrics.StringCheck, EntityBase):
    """Persisted string check metric."""

    pass


class ToolCallingMetric(metrics.ToolCalling, EntityBase):
    """Persisted Tool Calling metric."""

    pass


# =============================================================================
# RAGAS Metrics - Persisted versions of SDK types + EntityBase
# =============================================================================


class TopicAdherenceMetric(WithJudgeModel, metrics.TopicAdherence, EntityBase):
    """RAGAS metric for measuring topic adherence."""

    pass


class ToolCallAccuracyMetric(metrics.ToolCallAccuracy, EntityBase):
    """RAGAS metric for measuring tool call accuracy."""

    pass


class AgentGoalAccuracyMetric(WithJudgeModel, metrics.AgentGoalAccuracy, EntityBase):
    """RAGAS metric for measuring agent goal accuracy."""

    pass


class AnswerAccuracyMetric(WithJudgeModel, metrics.AnswerAccuracy, EntityBase):
    """RAGAS metric for measuring answer accuracy."""

    pass


class ContextRelevanceMetric(WithJudgeModel, metrics.ContextRelevance, EntityBase):
    """RAGAS metric for measuring context relevance."""

    pass


class ResponseGroundednessMetric(WithJudgeModel, metrics.ResponseGroundedness, EntityBase):
    """RAGAS metric for measuring response groundedness."""

    pass


class ContextRecallMetric(WithJudgeModel, metrics.ContextRecall, EntityBase):
    """RAGAS metric for measuring context recall."""

    pass


class ContextPrecisionMetric(WithJudgeModel, metrics.ContextPrecision, EntityBase):
    """RAGAS metric for measuring context precision."""

    pass


class ContextEntityRecallMetric(WithJudgeModel, metrics.ContextEntityRecall, EntityBase):
    """RAGAS metric for measuring context entity recall."""

    pass


class ResponseRelevancyMetric(WithJudgeModel, WithEmbeddingsModel, metrics.ResponseRelevancy, EntityBase):
    """RAGAS metric for measuring response relevancy."""

    pass


class FaithfulnessMetric(WithJudgeModel, metrics.Faithfulness, EntityBase):
    """RAGAS metric for measuring faithfulness."""

    pass


class NoiseSensitivityMetric(WithJudgeModel, metrics.NoiseSensitivity, EntityBase):
    """RAGAS metric for measuring noise sensitivity."""

    pass


# =============================================================================
# Union of all persisted metric types (with workspace/name)
# =============================================================================

Metric = Annotated[
    Union[
        BLEUMetric,
        ExactMatchMetric,
        F1Metric,
        LLMJudgeMetric,
        NumberCheckMetric,
        RemoteMetric,
        NemoAgentToolkitRemoteMetric,
        ROUGEMetric,
        StringCheckMetric,
        ToolCallingMetric,
        # RAGAS Agentic Metrics
        TopicAdherenceMetric,
        ToolCallAccuracyMetric,
        AgentGoalAccuracyMetric,
        # RAGAS NVIDIA Metrics
        AnswerAccuracyMetric,
        ContextRelevanceMetric,
        ResponseGroundednessMetric,
        # RAGAS RAG Metrics
        ContextRecallMetric,
        ContextPrecisionMetric,
        ContextEntityRecallMetric,
        ResponseRelevancyMetric,
        FaithfulnessMetric,
        NoiseSensitivityMetric,
        # EvalFactory System Metrics
        SystemMetric,
    ],
    Field(discriminator="type"),
]
setattr(Metric, "__entity_type__", "metric")
