# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Value types for the evaluator service.

This module re-exports all value types for backwards compatibility.
Import from here for a stable API, or import from submodules for
explicit dependencies.
"""

from nemo_evaluator_sdk.metrics.llm_judge import (
    default_judge_prompt_template_chat,
    default_judge_prompt_template_completions,
)
from nemo_evaluator_sdk.metrics.ragas.metrics import (
    AgentGoalAccuracyMetric,
    AnswerAccuracyMetric,
    BaseRAGASMetric,
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
from nemo_evaluator_sdk.values import (
    Agent,
    AggregatedMetricResult,
    AggregateFieldName,
    AggregateRangeScore,
    AggregateRubricScore,
    AggregateScore,
    AggregateScoreBase,
    DefaultAggregateFieldName,
    FieldMapping,
    Histogram,
    HistogramBin,
    InputSchema,
    JSONScoreParser,
    MetricResult,
    MetricScore,
    Model,
    Percentiles,
    RangeScore,
    ReasoningParams,
    RegexScoreParser,
    RemoteScore,
    RowScore,
    Rubric,
    RubricScore,
    RubricScoreStat,
    RubricScoreValue,
    SampleResult,
    Score,
    ScoreStats,
    SecretRef,
    SupportedJobTypes,
    score_discriminator,
)
from nemo_evaluator_sdk.values.metrics import (
    _RAGASEmbeddingsConfig as RAGASEmbeddingsConfig,
)
from nemo_evaluator_sdk.values.metrics import (
    _RAGASJudgeConfig as RAGASJudgeConfig,
)
from nmp.evaluator.app.values.benchmarks import Benchmark, BenchmarkMetric
from nmp.evaluator.app.values.benchmarks_job import (
    BenchmarkEvaluationResult,
    BenchmarkJob,
    BenchmarkJobAdapter,
    BenchmarkMetricResult,
    BenchmarkOfflineJob,
    BenchmarkOnlineAgentJob,
    BenchmarkOnlineJob,
)
from nmp.evaluator.app.values.common import (
    BenchmarkRef,
    Fileset,
    FilesetRef,
    MetricRef,
    ModelRef,
    StorageConfig,
    StorageConfigField,
)
from nmp.evaluator.app.values.datasets import (
    BuiltInDataset,
    BuiltInDatasetID,
    Dataset,
    DatasetRows,
    PipelineDataset,
)
from nmp.evaluator.app.values.jobs import (
    EvaluationStatusDetails,
)
from nmp.evaluator.app.values.metrics import (
    Metric,
    MetricAdapter,
    MetricBase,
)
from nmp.evaluator.app.values.metrics_job import (
    MetricJob,
    MetricJobAdapter,
    MetricOfflineJob,
    MetricOnlineAgentJob,
    MetricOnlineJob,
)
from nmp.evaluator.app.values.results import (
    DeprecatedMetricResult,
    DeprecatedScoreValue,
    EvaluationResult,
    GroupResult,
    TaskResult,
)

__all__ = [
    # Agent
    "Agent",
    # Common
    "BenchmarkRef",
    "FilesetRef",
    "Fileset",
    "MetricRef",
    "ModelRef",
    "SecretRef",
    "StorageConfig",
    "StorageConfigField",
    "SupportedJobTypes",
    "FieldMapping",
    "InputSchema",
    # Datasets
    "BuiltInDataset",
    "BuiltInDatasetID",
    "Dataset",
    "DatasetRows",
    "PipelineDataset",
    # Jobs
    "EvaluationStatusDetails",
    # Benchmarks
    "Benchmark",
    "BenchmarkMetric",
    # Benchmarks Job
    "BenchmarkEvaluationResult",
    "BenchmarkJob",
    "BenchmarkJobAdapter",
    "BenchmarkMetricResult",
    "BenchmarkOfflineJob",
    "BenchmarkOnlineAgentJob",
    "BenchmarkOnlineJob",
    # Metrics Job
    "MetricJob",
    "MetricJobAdapter",
    "MetricOfflineJob",
    "MetricOnlineAgentJob",
    "MetricOnlineJob",
    # Metrics
    "Metric",
    "MetricAdapter",
    "MetricBase",
    # Metrics LLM-Judge
    "default_judge_prompt_template_chat",
    "default_judge_prompt_template_completions",
    # Metrics (RAGAS)
    "BaseRAGASMetric",
    "AgentGoalAccuracyMetric",
    "AnswerAccuracyMetric",
    "ContextEntityRecallMetric",
    "ContextPrecisionMetric",
    "ContextRecallMetric",
    "ContextRelevanceMetric",
    "FaithfulnessMetric",
    "NoiseSensitivityMetric",
    "RAGASJudgeConfig",
    "RAGASEmbeddingsConfig",
    "ResponseGroundednessMetric",
    "ResponseRelevancyMetric",
    "ToolCallAccuracyMetric",
    "TopicAdherenceMetric",
    # Models
    "Model",
    "ReasoningParams",
    # Results
    "AggregateFieldName",
    "AggregatedMetricResult",
    "AggregateRangeScore",
    "AggregateRubricScore",
    "AggregateScore",
    "AggregateScoreBase",
    "DefaultAggregateFieldName",
    "DeprecatedMetricResult",
    "DeprecatedScoreValue",
    "EvaluationResult",
    "GroupResult",
    "Histogram",
    "HistogramBin",
    "RowScore",
    "MetricResult",
    "MetricScore",
    "Percentiles",
    "RubricScoreStat",
    "RubricScoreValue",
    "SampleResult",
    "ScoreStats",
    "TaskResult",
    # Scores
    "JSONScoreParser",
    "RangeScore",
    "RegexScoreParser",
    "RemoteScore",
    "Rubric",
    "RubricScore",
    "Score",
    "score_discriminator",
]
