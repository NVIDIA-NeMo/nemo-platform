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

from __future__ import annotations

from typing import Dict, Union
from typing_extensions import Required, TypeAlias, TypedDict

from ..._types import SequenceNotStr
from .metric_ref import MetricRef
from .agent_param import AgentParam
from .fileset_ref import FilesetRef
from .dataset_rows_param import DatasetRowsParam
from .field_mapping_param import FieldMappingParam
from .f1_metric_param_param import F1MetricParamParam
from .bleu_metric_param_param import BleuMetricParamParam
from .run_config_online_param import RunConfigOnlineParam
from .evaluation_fileset_param import EvaluationFilesetParam
from .rouge_metric_param_param import RougeMetricParamParam
from .remote_metric_param_param import RemoteMetricParamParam
from .system_metric_param_param import SystemMetricParamParam
from .llm_judge_metric_param_param import LLMJudgeMetricParamParam
from .exact_match_metric_param_param import ExactMatchMetricParamParam
from .faithfulness_metric_param_param import FaithfulnessMetricParamParam
from .number_check_metric_param_param import NumberCheckMetricParamParam
from .string_check_metric_param_param import StringCheckMetricParamParam
from .tool_calling_metric_param_param import ToolCallingMetricParamParam
from .context_recall_metric_param_param import ContextRecallMetricParamParam
from .answer_accuracy_metric_param_param import AnswerAccuracyMetricParamParam
from .topic_adherence_metric_param_param import TopicAdherenceMetricParamParam
from .context_precision_metric_param_param import ContextPrecisionMetricParamParam
from .context_relevance_metric_param_param import ContextRelevanceMetricParamParam
from .noise_sensitivity_metric_param_param import NoiseSensitivityMetricParamParam
from .response_relevancy_metric_param_param import ResponseRelevancyMetricParamParam
from .tool_call_accuracy_metric_param_param import ToolCallAccuracyMetricParamParam
from .agent_goal_accuracy_metric_param_param import AgentGoalAccuracyMetricParamParam
from .context_entity_recall_metric_param_param import ContextEntityRecallMetricParamParam
from .response_groundedness_metric_param_param import ResponseGroundednessMetricParamParam
from .nemo_agent_toolkit_remote_metric_param_param import NeMoAgentToolkitRemoteMetricParamParam

__all__ = ["MetricOnlineAgentJobParam", "Dataset", "Metric"]

Dataset: TypeAlias = Union[DatasetRowsParam, FilesetRef, EvaluationFilesetParam]

Metric: TypeAlias = Union[
    MetricRef,
    LLMJudgeMetricParamParam,
    TopicAdherenceMetricParamParam,
    AgentGoalAccuracyMetricParamParam,
    AnswerAccuracyMetricParamParam,
    ContextRelevanceMetricParamParam,
    ResponseGroundednessMetricParamParam,
    ContextRecallMetricParamParam,
    ContextPrecisionMetricParamParam,
    ContextEntityRecallMetricParamParam,
    ResponseRelevancyMetricParamParam,
    FaithfulnessMetricParamParam,
    NoiseSensitivityMetricParamParam,
    ToolCallAccuracyMetricParamParam,
    BleuMetricParamParam,
    ExactMatchMetricParamParam,
    F1MetricParamParam,
    NumberCheckMetricParamParam,
    RemoteMetricParamParam,
    NeMoAgentToolkitRemoteMetricParamParam,
    RougeMetricParamParam,
    StringCheckMetricParamParam,
    ToolCallingMetricParamParam,
    SystemMetricParamParam,
]


class MetricOnlineAgentJobParam(TypedDict, total=False):
    """An online metric job that evaluates an agent."""

    agent: Required[AgentParam]
    """Agent definition for inference in online evaluation jobs.

    An agent is an endpoint that accepts a request and returns a response,
    potentially with a trajectory. Two formats are supported:

    - `generic`: configurable HTTP POST with Jinja-templated body and JSONPath
      extraction for response and trajectory.
    - `nemo_agent_toolkit`: NeMo Agent Toolkit SSE streaming protocol
      (`/generate/full?filter_steps=none`).
    """

    dataset: Required[Dataset]
    """The dataset to use for agent prompts and evaluation."""

    metric: Required[Metric]
    """The metric for evaluation."""

    prompt_template: Required[Union[str, Dict[str, object]]]
    """The jinja template to prompt the agent for evaluation.

    Can be either a simple string or a structured object (e.g., OpenAI messages
    format). Use Jinja template variables like {{input}}, {{output}}, {{context}},
    {{reference}} to reference input columns.
    """

    field_mapping: FieldMappingParam
    """
    Maps canonical evaluator fields to raw dataset column paths. Example: {'input':
    'question', 'output': 'answer', 'reference': 'gold', 'trajectory': 'steps'}
    """

    metric_params: Dict[str, object]
    """Additional parameters for the metric.

    Required for system metrics, optional overrides for custom metrics.
    """

    optional_fields: SequenceNotStr[str]
    """
    Prompt template fields that should remain available to the prompt template but
    not be required by dataset schema validation.
    """

    params: RunConfigOnlineParam
    """Job parameters for online evaluation."""
