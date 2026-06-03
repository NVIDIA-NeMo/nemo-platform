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

from typing import Dict, List, Union, Optional
from datetime import datetime
from typing_extensions import Annotated, TypeAlias

from ..._utils import PropertyInfo
from ..._models import BaseModel
from .f1_metric import F1Metric
from .bleu_metric import BleuMetric
from .fileset_ref import FilesetRef
from .dataset_rows import DatasetRows
from .rouge_metric import RougeMetric
from .field_mapping import FieldMapping
from .remote_metric import RemoteMetric
from .system_metric import SystemMetric
from .llm_judge_metric import LLMJudgeMetric
from .evaluation_fileset import EvaluationFileset
from .exact_match_metric import ExactMatchMetric
from .faithfulness_metric import FaithfulnessMetric
from .number_check_metric import NumberCheckMetric
from .string_check_metric import StringCheckMetric
from .tool_calling_metric import ToolCallingMetric
from .context_recall_metric import ContextRecallMetric
from .answer_accuracy_metric import AnswerAccuracyMetric
from .topic_adherence_metric import TopicAdherenceMetric
from .context_precision_metric import ContextPrecisionMetric
from .context_relevance_metric import ContextRelevanceMetric
from .noise_sensitivity_metric import NoiseSensitivityMetric
from .response_relevancy_metric import ResponseRelevancyMetric
from .tool_call_accuracy_metric import ToolCallAccuracyMetric
from .agent_goal_accuracy_metric import AgentGoalAccuracyMetric
from .context_entity_recall_metric import ContextEntityRecallMetric
from .response_groundedness_metric import ResponseGroundednessMetric
from .nemo_agent_toolkit_remote_metric import NeMoAgentToolkitRemoteMetric

__all__ = ["ExtendedBenchmark", "Dataset", "Metric"]

Dataset: TypeAlias = Union[DatasetRows, EvaluationFileset, FilesetRef]

Metric: TypeAlias = Annotated[
    Union[
        BleuMetric,
        ExactMatchMetric,
        F1Metric,
        LLMJudgeMetric,
        NumberCheckMetric,
        RemoteMetric,
        NeMoAgentToolkitRemoteMetric,
        RougeMetric,
        StringCheckMetric,
        ToolCallingMetric,
        TopicAdherenceMetric,
        ToolCallAccuracyMetric,
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
        SystemMetric,
    ],
    PropertyInfo(discriminator="type"),
]


class ExtendedBenchmark(BaseModel):
    """Extended benchmark response. Includes the metrics and dataset as entities."""

    id: str

    created_at: datetime

    created_by: Optional[str] = None

    dataset: Dataset
    """Dataset containing the test cases for this benchmark."""

    entity_id: str
    """Alias for id for backwards compatibility."""

    metrics: List[Metric]
    """The fully defined metrics of the benchmark."""

    name: str
    """Benchmark name"""

    parent: str
    """Parent entity ID for nested entities."""

    updated_at: datetime

    updated_by: Optional[str] = None

    workspace: str
    """Workspace identifier"""

    description: Optional[str] = None
    """Human-readable description of the benchmark."""

    field_mapping: Optional[FieldMapping] = None
    """
    Maps canonical evaluator fields to raw dataset column paths. Example: {'input':
    'question', 'output': 'answer', 'reference': 'gold', 'trajectory': 'steps'}
    """

    labels: Optional[Dict[str, str]] = None
    """Labels are key-value pairs that can be used for grouping and filtering."""

    project: Optional[str] = None
    """The name of the project associated with this entity."""
