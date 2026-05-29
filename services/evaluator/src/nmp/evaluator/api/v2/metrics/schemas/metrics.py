# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for metric creation and inline metric jobs.

These types inherit from app.* types and don't include name/workspace
(those come from path parameters). They're pure DTOs - model resolution
and entity construction happen in the service layer.
"""

from typing import Annotated, Union

import nmp.evaluator.app.values as app
from nemo_evaluator_sdk.values import metrics
from nmp.common.api.common import SecretRef as ApiSecretRef
from nmp.evaluator.api.v2.common.inline_models import Model
from nmp.evaluator.api.v2.common.model_resolution import ModelResolver, resolve_model_field
from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Resolution Mixins - provide Model-typed fields and resolve_models()
# =============================================================================


class _ResolvableBase(BaseModel):
    """Base class that terminates the resolve_models() super() chain.

    All _With* mixins inherit from this to ensure the cooperative inheritance
    chain has a proper termination point that returns an empty dict.
    """

    async def resolve_models(self, resolver: ModelResolver) -> dict[str, Model]:
        """Terminate the super() chain with an empty dict."""
        return {}


class WithModel(_ResolvableBase):
    """Mixin for types with a `model` field that needs resolution.

    Provides:
    - model: Model field (shadows parent's Model field)
    - resolve_models() implementation

    Place this mixin BEFORE the parent class that defines model: Model
    in the inheritance list to ensure proper field shadowing.
    """

    model: Model | app.ModelRef = Field(description="The model configuration.")  # noqa: F821

    async def resolve_models(self, resolver: ModelResolver) -> dict[str, Model]:
        """Resolve the model field."""
        result = await super().resolve_models(resolver)
        resolved = await resolve_model_field(self.model, resolver)
        if resolved is not None:
            result["model"] = resolved
        return result


class WithJudgeModel(_ResolvableBase):
    """Mixin for types with a `judge_model` field that needs resolution.

    Provides:
    - judge_model: Model field (shadows parent's Model field)
    - resolve_models() implementation

    Place this mixin BEFORE the parent class that defines judge_model: Model
    in the inheritance list to ensure proper field shadowing.
    """

    judge_model: Model | app.ModelRef = Field(description="The judge model configuration.")

    async def resolve_models(self, resolver: ModelResolver) -> dict[str, Model]:
        """Resolve the judge_model field."""
        result = await super().resolve_models(resolver)
        resolved = await resolve_model_field(self.judge_model, resolver)
        if resolved is not None:
            result["judge_model"] = resolved
        return result


class WithEmbeddingsModel(_ResolvableBase):
    """Mixin for types with an `embeddings_model` field that needs resolution.

    Provides:
    - embeddings_model: Model field (shadows parent's Model field)
    - resolve_models() implementation

    Place this mixin BEFORE the parent class that defines embeddings_model: Model
    in the inheritance list to ensure proper field shadowing.
    """

    embeddings_model: Model | app.ModelRef = Field(description="The embeddings model configuration.")

    async def resolve_models(self, resolver: ModelResolver) -> dict[str, Model]:
        """Resolve the embeddings_model field."""
        result = await super().resolve_models(resolver)
        resolved = await resolve_model_field(self.embeddings_model, resolver)
        if resolved is not None:
            result["embeddings_model"] = resolved
        return result


class WithApiKeySecret(BaseModel):
    """Mixin that overrides SDK ``api_key_secret`` with the strict service ``ApiSecretRef``.

    The SDK's ``SecretRef`` allows mixed case; the service public API keeps the
    original lowercase-only pattern. Service-layer schemas mix this in to
    enforce the stricter pattern on ``api_key_secret`` fields.
    """

    api_key_secret: ApiSecretRef | None = Field(
        default=None,
        description=metrics.Remote.model_fields["api_key_secret"].description,
    )


# =============================================================================
# LLM Judge Request - allows Model URN or inline and optional prompt_template and score parsers
# =============================================================================


class LLMJudgeMetric(WithModel, metrics.LLMJudge):
    """Request type for creating LLM Judge metrics."""

    model_config = ConfigDict(extra="forbid")
    prompt_template: str | dict = Field(
        default_factory=lambda data: metrics.default_judge_prompt_template_for_model(data["model"]),
        description=metrics.LLMJudge.model_fields["prompt_template"].description,
        examples=metrics.LLMJudge.model_fields["prompt_template"].examples,
    )


# =============================================================================
# RAGAS Metric Requests - allow Model URN or inline for judge/embeddings
# =============================================================================


class TopicAdherenceMetric(WithJudgeModel, metrics.TopicAdherence):
    """Request type for TopicAdherence metrics."""

    pass


class AgentGoalAccuracyMetric(WithJudgeModel, metrics.AgentGoalAccuracy):
    """Request type for AgentGoalAccuracy metrics."""

    pass


class AnswerAccuracyMetric(WithJudgeModel, metrics.AnswerAccuracy):
    """Request type for AnswerAccuracy metrics."""

    pass


class ContextRelevanceMetric(WithJudgeModel, metrics.ContextRelevance):
    """Request type for ContextRelevance metrics."""

    pass


class ResponseGroundednessMetric(WithJudgeModel, metrics.ResponseGroundedness):
    """Request type for ResponseGroundedness metrics."""

    pass


class ContextRecallMetric(WithJudgeModel, metrics.ContextRecall):
    """Request type for ContextRecall metrics."""

    pass


class ContextPrecisionMetric(WithJudgeModel, metrics.ContextPrecision):
    """Request type for ContextPrecision metrics."""

    pass


class ContextEntityRecallMetric(WithJudgeModel, metrics.ContextEntityRecall):
    """Request type for ContextEntityRecall metrics."""

    pass


class ResponseRelevancyMetric(WithJudgeModel, WithEmbeddingsModel, metrics.ResponseRelevancy):
    """Request type for ResponseRelevancy metrics."""

    pass


class FaithfulnessMetric(WithJudgeModel, metrics.Faithfulness):
    """Request type for Faithfulness metrics."""

    pass


class NoiseSensitivityMetric(WithJudgeModel, metrics.NoiseSensitivity):
    """Request type for NoiseSensitivity metrics."""

    pass


class ToolCallAccuracyMetric(metrics.ToolCallAccuracy):
    """Request type for ToolCallAccuracy metrics (no judge required)."""

    pass


# =============================================================================
# Simple metric requests
# =============================================================================


class BLEUMetric(metrics.BLEU):
    """Request type for BLEUMetric."""

    pass


class ExactMatchMetric(metrics.ExactMatch):
    """Request type for ExactMatchMetric."""

    pass


class F1Metric(metrics.F1):
    """Request type for F1Metric."""

    pass


class NumberCheckMetric(metrics.NumberCheck):
    """Request type for NumberCheckMetric. Numeric-comparison metric with template-driven operands."""

    pass


class RemoteMetric(WithApiKeySecret, metrics.Remote):
    """Request type for RemoteMetric. A metric that computes scores via a remote endpoint."""

    pass


class NemoAgentToolkitRemoteMetric(WithApiKeySecret, metrics.NemoAgentToolkitRemote):
    """Request type for NemoAgentToolkitRemoteMetric. A remote metric that interfaces with NeMo Agent Toolkit evaluators."""

    pass


class ROUGEMetric(metrics.ROUGE):
    """Request type for ROUGEMetric. ROUGE metric for overlap-based summarization quality scoring."""

    pass


class StringCheckMetric(metrics.StringCheck):
    """Request type for StringCheckMetric. String-comparison metric with operator-based checks."""

    pass


class ToolCallingMetric(metrics.ToolCalling):
    """Request type for ToolCallingMetric. Tool-calling accuracy metric for structured function calls."""

    pass


# =============================================================================
# Union of all metric request types
# =============================================================================

Metric = Annotated[
    Union[
        # Metrics with models (may be ref or inline)
        LLMJudgeMetric,
        TopicAdherenceMetric,
        AgentGoalAccuracyMetric,
        AnswerAccuracyMetric,
        ContextRelevanceMetric,
        ResponseGroundednessMetric,
        ContextRecallMetric,
        ContextPrecisionMetric,
        ContextEntityRecallMetric,
        ResponseRelevancyMetric,
        FaithfulnessMetric,
        NoiseSensitivityMetric,
        ToolCallAccuracyMetric,
        # Simple metrics (no model resolution needed)
        BLEUMetric,
        ExactMatchMetric,
        F1Metric,
        NumberCheckMetric,
        RemoteMetric,
        NemoAgentToolkitRemoteMetric,
        ROUGEMetric,
        StringCheckMetric,
        ToolCallingMetric,
        # SystemMetric is not in input type for users via API
    ],
    Field(discriminator="type"),
]
