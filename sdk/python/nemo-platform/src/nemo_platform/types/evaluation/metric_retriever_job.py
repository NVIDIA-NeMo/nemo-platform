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
from .fileset_ref import FilesetRef
from .dataset_rows import DatasetRows
from .field_mapping import FieldMapping
from .built_in_dataset import BuiltInDataset
from .run_config_online import RunConfigOnline
from .evaluation_fileset import EvaluationFileset
from .system_metric_param import SystemMetricParam
from .evaluation_metric_jobs_retriever_pipeline import EvaluationMetricJobsRetrieverPipeline

__all__ = ["MetricRetrieverJob", "Dataset", "Metric"]

Dataset: TypeAlias = Union[BuiltInDataset, DatasetRows, FilesetRef, EvaluationFileset]

Metric: TypeAlias = Union[MetricRef, SystemMetricParam]


class MetricRetrieverJob(BaseModel):
    """Evaluation with a retriever-based metric."""

    dataset: Dataset
    """The dataset to use for evaluation."""

    metric: Metric
    """The metric for evaluation."""

    retriever_pipeline: EvaluationMetricJobsRetrieverPipeline
    """Pipeline configuration for retriever-based evaluations."""

    field_mapping: Optional[FieldMapping] = None
    """
    Maps canonical evaluator fields to raw dataset column paths. Example: {'input':
    'question', 'output': 'answer', 'reference': 'gold', 'trajectory': 'steps'}
    """

    metric_params: Optional[Dict[str, object]] = None
    """Additional parameters for the metric.

    Required for system metrics, optional overrides for custom metrics.
    """

    params: Optional[RunConfigOnline] = None
    """Job parameters for online evaluation."""
