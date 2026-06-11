# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone agent evaluation API."""

from nemo_evaluator_sdk.agent_eval.benchmarks import (
    AgentEvalBenchmark,
    AgentEvalBenchmarkBundle,
    AgentEvalBenchmarkLoadConfig,
    AgentEvalBenchmarkReports,
    AgentEvalBenchmarkReportWriter,
    resolve_agent_eval_benchmark,
)
from nemo_evaluator_sdk.agent_eval.dashboard import render_dashboard, write_dashboard
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.persistence import persist_run
from nemo_evaluator_sdk.agent_eval.types import (
    AgentAttemptRuntime,
    AgentEvalAttempt,
    AgentEvalDiagnostic,
    AgentEvalMetricOutputCoverage,
    AgentEvalRunConfig,
    AgentEvalRunResult,
    AgentEvalSummary,
    AgentEvalTarget,
    AgentEvalTask,
    AgentEvalTaskResult,
    AgentOutput,
    SemanticView,
    ViewSignal,
)
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor, LocalFilesystemEvidence

__all__ = [
    "AgentEvalAttempt",
    "AgentEvalBenchmark",
    "AgentEvalBenchmarkBundle",
    "AgentEvalBenchmarkLoadConfig",
    "AgentEvalBenchmarkReportWriter",
    "AgentEvalBenchmarkReports",
    "AgentEvalDiagnostic",
    "AgentEvalMetricOutputCoverage",
    "AgentEvalRunConfig",
    "AgentEvalRunResult",
    "AgentEvalSummary",
    "AgentEvalTarget",
    "AgentEvalTask",
    "AgentEvalTaskResult",
    "AgentEvaluator",
    "AgentAttemptRuntime",
    "AgentOutput",
    "CandidateEvidence",
    "EvidenceDescriptor",
    "LocalFilesystemEvidence",
    "SemanticView",
    "ViewSignal",
    "persist_run",
    "resolve_agent_eval_benchmark",
    "render_dashboard",
    "write_dashboard",
]
