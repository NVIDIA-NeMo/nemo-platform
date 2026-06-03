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

from .metric_ref import MetricRef
from .fileset_ref import FilesetRef
from .built_in_dataset import BuiltInDataset
from .dataset_rows_param import DatasetRowsParam
from .field_mapping_param import FieldMappingParam
from .run_config_online_param import RunConfigOnlineParam
from .evaluation_fileset_param import EvaluationFilesetParam
from .system_metric_param_param import SystemMetricParamParam
from .evaluation_metric_jobs_retriever_pipeline_param import EvaluationMetricJobsRetrieverPipelineParam

__all__ = ["MetricRetrieverJobParam", "Dataset", "Metric"]

Dataset: TypeAlias = Union[BuiltInDataset, DatasetRowsParam, FilesetRef, EvaluationFilesetParam]

Metric: TypeAlias = Union[MetricRef, SystemMetricParamParam]


class MetricRetrieverJobParam(TypedDict, total=False):
    """Evaluation with a retriever-based metric."""

    dataset: Required[Dataset]
    """The dataset to use for evaluation."""

    metric: Required[Metric]
    """The metric for evaluation."""

    retriever_pipeline: Required[EvaluationMetricJobsRetrieverPipelineParam]
    """Pipeline configuration for retriever-based evaluations."""

    field_mapping: FieldMappingParam
    """
    Maps canonical evaluator fields to raw dataset column paths. Example: {'input':
    'question', 'output': 'answer', 'reference': 'gold', 'trajectory': 'steps'}
    """

    metric_params: Dict[str, object]
    """Additional parameters for the metric.

    Required for system metrics, optional overrides for custom metrics.
    """

    params: RunConfigOnlineParam
    """Job parameters for online evaluation."""
