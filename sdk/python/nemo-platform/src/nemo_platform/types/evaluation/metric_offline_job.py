# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing import Dict, Union, Optional
from typing_extensions import TypeAlias

from ..._models import BaseModel
from .metric_ref import MetricRef
from .run_config import RunConfig
from .fileset_ref import FilesetRef
from .dataset_rows import DatasetRows
from .field_mapping import FieldMapping
from .f1_metric_param import F1MetricParam
from .bleu_metric_param import BleuMetricParam
from .evaluation_fileset import EvaluationFileset
from .rouge_metric_param import RougeMetricParam
from .remote_metric_param import RemoteMetricParam
from .system_metric_param import SystemMetricParam
from .llm_judge_metric_param import LLMJudgeMetricParam
from .exact_match_metric_param import ExactMatchMetricParam
from .faithfulness_metric_param import FaithfulnessMetricParam
from .number_check_metric_param import NumberCheckMetricParam
from .string_check_metric_param import StringCheckMetricParam
from .tool_calling_metric_param import ToolCallingMetricParam
from .context_recall_metric_param import ContextRecallMetricParam
from .answer_accuracy_metric_param import AnswerAccuracyMetricParam
from .topic_adherence_metric_param import TopicAdherenceMetricParam
from .context_precision_metric_param import ContextPrecisionMetricParam
from .context_relevance_metric_param import ContextRelevanceMetricParam
from .noise_sensitivity_metric_param import NoiseSensitivityMetricParam
from .response_relevancy_metric_param import ResponseRelevancyMetricParam
from .tool_call_accuracy_metric_param import ToolCallAccuracyMetricParam
from .agent_goal_accuracy_metric_param import AgentGoalAccuracyMetricParam
from .context_entity_recall_metric_param import ContextEntityRecallMetricParam
from .response_groundedness_metric_param import ResponseGroundednessMetricParam
from .nemo_agent_toolkit_remote_metric_param import NeMoAgentToolkitRemoteMetricParam

__all__ = ["MetricOfflineJob", "Dataset", "Metric"]

Dataset: TypeAlias = Union[DatasetRows, FilesetRef, EvaluationFileset]

Metric: TypeAlias = Union[
    MetricRef,
    LLMJudgeMetricParam,
    TopicAdherenceMetricParam,
    AgentGoalAccuracyMetricParam,
    AnswerAccuracyMetricParam,
    ContextRelevanceMetricParam,
    ResponseGroundednessMetricParam,
    ContextRecallMetricParam,
    ContextPrecisionMetricParam,
    ContextEntityRecallMetricParam,
    ResponseRelevancyMetricParam,
    FaithfulnessMetricParam,
    NoiseSensitivityMetricParam,
    ToolCallAccuracyMetricParam,
    BleuMetricParam,
    ExactMatchMetricParam,
    F1MetricParam,
    NumberCheckMetricParam,
    RemoteMetricParam,
    NeMoAgentToolkitRemoteMetricParam,
    RougeMetricParam,
    StringCheckMetricParam,
    ToolCallingMetricParam,
    SystemMetricParam,
]


class MetricOfflineJob(BaseModel):
    """An offline metric job."""

    dataset: Dataset
    """The dataset to evaluate which may represent generated outputs from a model."""

    metric: Metric
    """The metric for evaluation."""

    field_mapping: Optional[FieldMapping] = None
    """
    Maps canonical evaluator fields to raw dataset column paths. Example: {'input':
    'question', 'output': 'answer', 'reference': 'gold', 'trajectory': 'steps'}
    """

    metric_params: Optional[Dict[str, object]] = None
    """Additional parameters for the metric.

    Required for system metrics, optional overrides for custom metrics.
    """

    params: Optional[RunConfig] = None
    """Job parameters."""
