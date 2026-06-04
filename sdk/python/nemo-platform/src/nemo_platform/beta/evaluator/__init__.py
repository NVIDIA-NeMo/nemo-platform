# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Evaluator SDK."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

from nemo_platform.beta.evaluator.datasets import DatasetLoadError, load_dataset, load_dataset_as_dicts
from nemo_platform.beta.evaluator.execution.backends.local.backend import LocalBackend
from nemo_platform.beta.evaluator.execution.evaluator import Evaluator
from nemo_platform.beta.evaluator.execution.values import (
    EvaluationError,
    EvaluationPhase,
)
from nemo_platform.beta.evaluator.metrics.bleu import BLEUMetric
from nemo_platform.beta.evaluator.metrics.exact_match import ExactMatchMetric
from nemo_platform.beta.evaluator.metrics.f1 import F1Metric
from nemo_platform.beta.evaluator.metrics.llm_judge import LLMJudgeMetric
from nemo_platform.beta.evaluator.metrics.number_check import NumberCheckMetric
from nemo_platform.beta.evaluator.metrics.protocol import (
    Metric,
    MetricTypeName,
    validate_metric_result,
)
from nemo_platform.beta.evaluator.metrics.remote import NemoAgentToolkitRemoteMetric, RemoteMetric
from nemo_platform.beta.evaluator.metrics.rouge import ROUGEMetric
from nemo_platform.beta.evaluator.metrics.string_check import StringCheckMetric
from nemo_platform.beta.evaluator.metrics.tool_calling import ToolCallingMetric
from nemo_platform.beta.evaluator.resolver_protocols import ModelResolver, SecretResolver
from nemo_platform.beta.evaluator.resolvers import LocalModelResolver, LocalSecretResolver
from nemo_platform.beta.evaluator.structured_output import (
    InferenceFn,
    InferenceStructuredOutput,
    StructuredOutput,
    StructuredOutputMode,
    default_structured_output_mode,
    detect_structured_output_mode,
)
from nemo_platform.beta.evaluator.values import (
    Agent,
    BooleanValue,
    CandidateOutput,
    ContinuousScore,
    DatasetRow,
    DatasetRows,
    DiscreteScore,
    EvaluationResult,
    FieldMapping,
    InferenceParams,
    JSONScoreParser,
    Label,
    MetricDescriptor,
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
    Model,
    ModelRef,
    RangeScore,
    ReasoningParams,
    RemoteScore,
    RubricScore,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
    SecretRef,
)

try:
    version = _package_version("nemo-evaluator-sdk")
except PackageNotFoundError:
    version = "0.0.1"

__all__ = [
    "BLEUMetric",
    "Agent",
    "EvaluationError",
    "EvaluationPhase",
    "DatasetLoadError",
    "DatasetRows",
    "RunConfig",
    "RunConfigOnline",
    "RunConfigOnlineModel",
    "EvaluationResult",
    "Evaluator",
    "ExactMatchMetric",
    "F1Metric",
    "FieldMapping",
    "InferenceParams",
    "InferenceFn",
    "InferenceStructuredOutput",
    "JSONScoreParser",
    "Metric",
    "MetricTypeName",
    "MetricDescriptor",
    "MetricInput",
    "MetricOutput",
    "MetricOutputSpec",
    "MetricResult",
    "LLMJudgeMetric",
    "BooleanValue",
    "CandidateOutput",
    "ContinuousScore",
    "DatasetRow",
    "DiscreteScore",
    "Label",
    "LocalBackend",
    "LocalModelResolver",
    "LocalSecretResolver",
    "Model",
    "ModelRef",
    "ModelResolver",
    "NemoAgentToolkitRemoteMetric",
    "NumberCheckMetric",
    "RangeScore",
    "ReasoningParams",
    "RemoteMetric",
    "RemoteScore",
    "ROUGEMetric",
    "RubricScore",
    "SecretRef",
    "SecretResolver",
    "StringCheckMetric",
    "StructuredOutput",
    "StructuredOutputMode",
    "ToolCallingMetric",
    "default_structured_output_mode",
    "detect_structured_output_mode",
    "load_dataset",
    "load_dataset_as_dicts",
    "validate_metric_result",
    "version",
]
