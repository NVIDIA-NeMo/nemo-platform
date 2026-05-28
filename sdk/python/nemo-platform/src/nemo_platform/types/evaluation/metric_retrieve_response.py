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

from typing import Union
from typing_extensions import Annotated, TypeAlias

from ..._utils import PropertyInfo
from .f1_metric_response import F1MetricResponse
from .bleu_metric_response import BleuMetricResponse
from .rouge_metric_response import RougeMetricResponse
from .remote_metric_response import RemoteMetricResponse
from .llm_judge_metric_response import LLMJudgeMetricResponse
from .exact_match_metric_response import ExactMatchMetricResponse
from .faithfulness_metric_response import FaithfulnessMetricResponse
from .number_check_metric_response import NumberCheckMetricResponse
from .string_check_metric_response import StringCheckMetricResponse
from .tool_calling_metric_response import ToolCallingMetricResponse
from .context_recall_metric_response import ContextRecallMetricResponse
from .answer_accuracy_metric_response import AnswerAccuracyMetricResponse
from .topic_adherence_metric_response import TopicAdherenceMetricResponse
from .context_precision_metric_response import ContextPrecisionMetricResponse
from .context_relevance_metric_response import ContextRelevanceMetricResponse
from .noise_sensitivity_metric_response import NoiseSensitivityMetricResponse
from .response_relevancy_metric_response import ResponseRelevancyMetricResponse
from .tool_call_accuracy_metric_response import ToolCallAccuracyMetricResponse
from .agent_goal_accuracy_metric_response import AgentGoalAccuracyMetricResponse
from .context_entity_recall_metric_response import ContextEntityRecallMetricResponse
from .response_groundedness_metric_response import ResponseGroundednessMetricResponse
from .nemo_agent_toolkit_remote_metric_response import NeMoAgentToolkitRemoteMetricResponse

__all__ = ["MetricRetrieveResponse"]

MetricRetrieveResponse: TypeAlias = Annotated[
    Union[
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
        BleuMetricResponse,
        ExactMatchMetricResponse,
        F1MetricResponse,
        NumberCheckMetricResponse,
        RemoteMetricResponse,
        NeMoAgentToolkitRemoteMetricResponse,
        RougeMetricResponse,
        StringCheckMetricResponse,
        ToolCallingMetricResponse,
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
        BleuMetricResponse,
        ExactMatchMetricResponse,
        F1MetricResponse,
        NumberCheckMetricResponse,
        RemoteMetricResponse,
        NeMoAgentToolkitRemoteMetricResponse,
        RougeMetricResponse,
        StringCheckMetricResponse,
        ToolCallingMetricResponse,
    ],
    PropertyInfo(discriminator="type"),
]
