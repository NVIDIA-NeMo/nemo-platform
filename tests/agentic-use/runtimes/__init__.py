# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend-specific AgentAttemptRuntime implementations for agentic-use evals."""

from nemo_evaluator_sdk.agent_eval.gating import (
    GateCheck,
    GateReport,
    GateThresholds,
    evaluate_gate,
    load_baseline_summary,
    summarize_run,
    write_gate_report,
)
from nemo_evaluator_sdk.agent_eval.runtimes.environment import (
    AgentEnvironmentHandle,
    AgentEnvironmentProvider,
    DockerEnvironmentHandle,
    EnvCommandResult,
    EnvRunSpec,
)
from nemo_evaluator_sdk.agent_eval.runtimes.environment_spec import (
    BuildPlan,
    EnvironmentSpec,
    execute_build_plan,
    load_environment_spec,
    plan_task_build,
    render_derived_dockerfile,
)
from nemo_evaluator_sdk.agent_eval.runtimes.verify import VerifierOutcome, apply_verify_to_metadata

from runtimes.aut.runtime import AutAgentAttemptRuntime
from runtimes.claude_code.runtime import ClaudeCodeAgentAttemptRuntime
from runtimes.codex.runtime import CodexAgentAttemptRuntime
from runtimes.cursor_agent.runtime import CursorAgentAttemptRuntime
from runtimes.orchestrator import AgenticEvalOrchestrator, AgenticOrchestratorConfig, runtime_for_backend
from runtimes.shared.platform import (
    AgentPhaseSuccessMetric,
    DockerEnvironmentProvider,
    VerifierRewardMetric,
    attempt_from_result,
    attempt_from_result_dir,
    build_verify_run_spec,
    maybe_run_verify,
    run_verify,
)
from runtimes.workflow.runtime import NatWorkflowAttemptRuntime

__all__ = [
    "AgentEnvironmentHandle",
    "AgentEnvironmentProvider",
    "AgentPhaseSuccessMetric",
    "AgenticEvalOrchestrator",
    "AgenticOrchestratorConfig",
    "AutAgentAttemptRuntime",
    "BuildPlan",
    "ClaudeCodeAgentAttemptRuntime",
    "CodexAgentAttemptRuntime",
    "CursorAgentAttemptRuntime",
    "DockerEnvironmentHandle",
    "DockerEnvironmentProvider",
    "EnvCommandResult",
    "EnvRunSpec",
    "EnvironmentSpec",
    "GateCheck",
    "GateReport",
    "GateThresholds",
    "NatWorkflowAttemptRuntime",
    "VerifierOutcome",
    "VerifierRewardMetric",
    "apply_verify_to_metadata",
    "attempt_from_result",
    "attempt_from_result_dir",
    "build_verify_run_spec",
    "evaluate_gate",
    "execute_build_plan",
    "load_baseline_summary",
    "load_environment_spec",
    "maybe_run_verify",
    "plan_task_build",
    "render_derived_dockerfile",
    "run_verify",
    "runtime_for_backend",
    "summarize_run",
    "write_gate_report",
]
