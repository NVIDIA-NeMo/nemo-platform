# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Response schemas for metric entities and metric jobs.

These types have ref/inline unions and optional entity fields (workspace/name, etc).
"""

from datetime import datetime
from typing import Annotated, Union

import nmp.evaluator.app.values as app
import nmp.evaluator.entities as entities
from nemo_evaluator_sdk.enums import MetricType
from nmp.common.api.common import Page
from nmp.common.entities.values import DatetimeFilter, Filter, StringFilter, map_entity_field
from nmp.evaluator.api.v2.metrics.schemas import metrics as schema_metrics
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# =============================================================================
# Metric response types can either be an app value (/metric-jobs) or entity (/metrics)
# =============================================================================


class _OptionalEntity(BaseModel):
    """
    Base class for optional entity fields to use with response types
    """

    name: str | None = Field(default=None, description="Entity name within the workspace")
    workspace: str | None = Field(default=None, description="Workspace identifier")
    project: str | None = Field(default=None, description="The name of the project associated with this entity.")
    id: str | None = Field(default=None, description="Entity name within the workspace")
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)
    parent: str | None = Field(default=None)


# =============================================================================
# Metric response types
# =============================================================================


class LLMJudgeMetricResponse(schema_metrics.LLMJudgeMetric, _OptionalEntity):
    model_config = ConfigDict(extra="ignore")


# =============================================================================
# RAGAS Metric Requests - allow Model URN or inline for judge/embeddings
# =============================================================================


class TopicAdherenceMetricResponse(schema_metrics.TopicAdherenceMetric, _OptionalEntity):
    """Response type for TopicAdherence metrics."""

    pass


class AgentGoalAccuracyMetricResponse(schema_metrics.AgentGoalAccuracyMetric, _OptionalEntity):
    """Response type for AgentGoalAccuracy metrics."""

    pass


class AnswerAccuracyMetricResponse(schema_metrics.AnswerAccuracyMetric, _OptionalEntity):
    """Response type for AnswerAccuracy metrics."""

    pass


class ContextRelevanceMetricResponse(schema_metrics.ContextRelevanceMetric, _OptionalEntity):
    """Response type for ContextRelevance metrics."""

    pass


class ResponseGroundednessMetricResponse(schema_metrics.ResponseGroundednessMetric, _OptionalEntity):
    """Response type for ResponseGroundedness metrics."""

    pass


class ContextRecallMetricResponse(schema_metrics.ContextRecallMetric, _OptionalEntity):
    """Response type for ContextRecall metrics."""

    pass


class ContextPrecisionMetricResponse(schema_metrics.ContextPrecisionMetric, _OptionalEntity):
    """Response type for ContextPrecision metrics."""

    pass


class ContextEntityRecallMetricResponse(schema_metrics.ContextEntityRecallMetric, _OptionalEntity):
    """Response type for ContextEntityRecall metrics."""

    pass


class ResponseRelevancyMetricResponse(schema_metrics.ResponseRelevancyMetric, _OptionalEntity):
    """Response type for ResponseRelevancy metrics."""

    pass


class FaithfulnessMetricResponse(schema_metrics.FaithfulnessMetric, _OptionalEntity):
    """Response type for Faithfulness metrics."""

    pass


class NoiseSensitivityMetricResponse(schema_metrics.NoiseSensitivityMetric, _OptionalEntity):
    """Response type for NoiseSensitivity metrics."""

    pass


class ToolCallAccuracyMetricResponse(schema_metrics.ToolCallAccuracyMetric, _OptionalEntity):
    """Response type for ToolCallAccuracy metrics (no judge required)."""

    pass


# =============================================================================
# Simple metric requests - these don't have models, just use inline types directly
# =============================================================================


# These are just aliases for the inline types since they don't need any changes
class BLEUMetricResponse(schema_metrics.BLEUMetric, _OptionalEntity):
    """Response type for BLEUMetric."""

    pass


class ExactMatchMetricResponse(schema_metrics.ExactMatchMetric, _OptionalEntity):
    """Response type for ExactMatchMetric."""

    pass


class F1MetricResponse(schema_metrics.F1Metric, _OptionalEntity):
    """Response type for F1Metric."""

    pass


class NumberCheckMetricResponse(schema_metrics.NumberCheckMetric, _OptionalEntity):
    """Response type for NumberCheckMetric."""

    pass


class RemoteMetricResponse(schema_metrics.RemoteMetric, _OptionalEntity):
    """Response type for RemoteMetric."""

    pass


class NemoAgentToolkitRemoteMetricResponse(schema_metrics.NemoAgentToolkitRemoteMetric, _OptionalEntity):
    """Response type for NemoAgentToolkitRemoteMetric."""

    pass


class ROUGEMetricResponse(schema_metrics.ROUGEMetric, _OptionalEntity):
    """Response type for ROUGEMetric."""

    pass


class StringCheckMetricResponse(schema_metrics.StringCheckMetric, _OptionalEntity):
    """Response type for StringCheckMetric."""

    pass


class ToolCallingMetricResponse(schema_metrics.ToolCallingMetric, _OptionalEntity):
    """Response type for ToolCallingMetric."""

    pass


class SystemMetricResponse(app.SystemMetric, _OptionalEntity):
    """Response type for SystemMetric."""

    pass


MetricResponse = Annotated[
    Union[
        # Metrics with models (may be ref or inline)
        LLMJudgeMetricResponse,
        TopicAdherenceMetricResponse,
        AgentGoalAccuracyMetricResponse,
        AnswerAccuracyMetricResponse,
        ContextRelevanceMetricResponse,
        ResponseGroundednessMetricResponse,
        ContextRecallMetricResponse,
        ContextPrecisionMetricResponse,
        ContextEntityRecallMetricResponse,
        ResponseRelevancyMetricResponse,
        FaithfulnessMetricResponse,
        NoiseSensitivityMetricResponse,
        ToolCallAccuracyMetricResponse,
        # Simple metrics (no model resolution needed)
        BLEUMetricResponse,
        ExactMatchMetricResponse,
        F1MetricResponse,
        NumberCheckMetricResponse,
        RemoteMetricResponse,
        NemoAgentToolkitRemoteMetricResponse,
        ROUGEMetricResponse,
        StringCheckMetricResponse,
        ToolCallingMetricResponse,
        SystemMetricResponse,
    ],
    Field(discriminator="type"),
]
MetricResponseAdapter = TypeAdapter(MetricResponse)


# =============================================================================
# List Metrics
# =============================================================================


class MetricsListFilter(Filter):
    """Filter for list metrics query."""

    name: StringFilter | str | None = Field(default=None, description="Filter metrics by name.")
    description: StringFilter | str | None = Field(default=None, description="Filter metrics by description.")
    type: MetricType | None = Field(
        default=None, description="Filter metrics by metric type (e.g. llm-judge, exact-match, route, system)"
    )
    project: str | None = Field(default=None, description="Filter metrics by project name.")
    created_at: DatetimeFilter | None = Field(default=None, description="Filter metrics by creation date range.")
    updated_at: DatetimeFilter | None = Field(default=None, description="Filter metrics by last update date range.")
    labels: Annotated[dict[str, str] | None, map_entity_field("data.labels", namespace=True)] = Field(
        default=None,
        description="Filter by labels. Address an individual label as a sub-path, e.g. filter[labels.team]=eval.",
    )


# This is needed to ensure the generated OAS has a better name than UnionsPage.
class MetricsListResponse(Page[MetricResponse]): ...


# =============================================================================
# List Job Results
# =============================================================================


class MetricJobResultsListFilter(Filter):
    """Filter for list metric job results."""

    name: StringFilter | str | None = Field(default=None, description="Filter job results by name.")
    metric: app.MetricRef | None = Field(
        default=None,
        description="Filter results by metric reference. Jobs with inline metric configuration will not be included when filtering by metric.",
    )
    dataset: app.FilesetRef | None = Field(
        default=None,
        description="Filter results by dataset if the metric job is configured with the fileset reference.",
    )
    model: app.ModelRef | None = Field(
        default=None, description="Filter results by model if the metric job is configured with the model reference."
    )
    created_at: DatetimeFilter | None = Field(default=None, description="Filter job results by creation date range.")


class MetricJobResult(entities.MetricJobResult):
    """Response type for metric job result."""

    pass


class MetricJobResultsListResponse(Page[MetricJobResult]): ...
