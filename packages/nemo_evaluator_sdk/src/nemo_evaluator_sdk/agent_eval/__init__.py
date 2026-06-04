# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone agent evaluation API."""

from nemo_evaluator_sdk.agent_eval.dashboard import render_dashboard, write_dashboard
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.persistence import persist_run
from nemo_evaluator_sdk.agent_eval.profbench import (
    PROFBENCH_DATASET_URL,
    PROFBENCH_METRIC_ID,
    PROFBENCH_METRIC_TYPE,
    PROFBENCH_WEIGHT_POINTS,
    ProfBenchBenchmark,
    ProfBenchCriterion,
    ProfBenchJudgeDecision,
    ProfBenchJudgeRequest,
    ProfBenchModelJudge,
    ProfBenchRubricMetric,
    criteria_from_task,
    load_profbench,
    summarize_results,
)
from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalAttempt,
    AgentEvalMetricSpec,
    AgentEvalRunConfig,
    AgentEvalRunResult,
    AgentEvalSummary,
    AgentEvalTarget,
    AgentEvalTask,
    AgentEvalTaskResult,
    AgentOutput,
    CriterionScore,
    EvidenceLocator,
    ScoreDeduction,
)
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

__all__ = [
    "AgentEvalAttempt",
    "AgentEvalMetricSpec",
    "AgentEvalRunConfig",
    "AgentEvalRunResult",
    "AgentEvalSummary",
    "AgentEvalTarget",
    "AgentEvalTask",
    "AgentEvalTaskResult",
    "AgentEvaluator",
    "AgentOutput",
    "CandidateEvidence",
    "CriterionScore",
    "EvidenceDescriptor",
    "EvidenceLocator",
    "PROFBENCH_DATASET_URL",
    "PROFBENCH_METRIC_ID",
    "PROFBENCH_METRIC_TYPE",
    "PROFBENCH_WEIGHT_POINTS",
    "ProfBenchBenchmark",
    "ProfBenchCriterion",
    "ProfBenchJudgeDecision",
    "ProfBenchJudgeRequest",
    "ProfBenchModelJudge",
    "ProfBenchRubricMetric",
    "ScoreDeduction",
    "criteria_from_task",
    "load_profbench",
    "persist_run",
    "render_dashboard",
    "summarize_results",
    "write_dashboard",
]
