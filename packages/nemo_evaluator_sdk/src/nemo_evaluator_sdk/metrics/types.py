# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discriminated unions for SDK metric configuration models."""

from typing import Annotated, TypeAlias

from nemo_evaluator_sdk.metrics.bleu import BLEUMetric
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_evaluator_sdk.metrics.f1 import F1Metric
from nemo_evaluator_sdk.metrics.llm_judge import LLMJudgeMetric
from nemo_evaluator_sdk.metrics.number_check import NumberCheckMetric
from nemo_evaluator_sdk.metrics.ragas.metrics import (
    AgentGoalAccuracyMetric,
    AnswerAccuracyMetric,
    ContextEntityRecallMetric,
    ContextPrecisionMetric,
    ContextRecallMetric,
    ContextRelevanceMetric,
    FaithfulnessMetric,
    NoiseSensitivityMetric,
    ResponseGroundednessMetric,
    ResponseRelevancyMetric,
    ToolCallAccuracyMetric,
    TopicAdherenceMetric,
)
from nemo_evaluator_sdk.metrics.remote import NemoAgentToolkitRemoteMetric, RemoteMetric
from nemo_evaluator_sdk.metrics.rouge import ROUGEMetric
from nemo_evaluator_sdk.metrics.string_check import StringCheckMetric
from nemo_evaluator_sdk.metrics.tool_calling import ToolCallingMetric
from pydantic import Field

MetricVariants: TypeAlias = (
    BLEUMetric
    | ExactMatchMetric
    | F1Metric
    | LLMJudgeMetric
    | NumberCheckMetric
    | RemoteMetric
    | NemoAgentToolkitRemoteMetric
    | ROUGEMetric
    | StringCheckMetric
    | ToolCallingMetric
    | TopicAdherenceMetric
    | ToolCallAccuracyMetric
    | AgentGoalAccuracyMetric
    | AnswerAccuracyMetric
    | ContextRelevanceMetric
    | ResponseGroundednessMetric
    | ContextRecallMetric
    | ContextPrecisionMetric
    | ContextEntityRecallMetric
    | ResponseRelevancyMetric
    | FaithfulnessMetric
    | NoiseSensitivityMetric
)
"""Raw union of SDK metric configuration models."""

MetricsUnion: TypeAlias = Annotated[MetricVariants, Field(discriminator="type")]
"""Discriminated union of SDK metric configuration models."""

__all__ = ["MetricVariants", "MetricsUnion"]
