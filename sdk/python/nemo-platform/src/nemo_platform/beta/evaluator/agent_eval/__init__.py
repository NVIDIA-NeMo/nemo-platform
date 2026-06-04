# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standalone agent evaluation API."""

from nemo_platform.beta.evaluator.agent_eval.dashboard import render_dashboard, write_dashboard
from nemo_platform.beta.evaluator.agent_eval.evaluator import AgentEvaluator
from nemo_platform.beta.evaluator.agent_eval.persistence import persist_run
from nemo_platform.beta.evaluator.agent_eval.types import (
    AgentAttemptRuntime,
    AgentEvalAttempt,
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
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence, EvidenceDescriptor

__all__ = [
    "AgentEvalAttempt",
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
    "SemanticView",
    "ViewSignal",
    "persist_run",
    "render_dashboard",
    "write_dashboard",
]
