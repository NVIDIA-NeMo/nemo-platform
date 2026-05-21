# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task-local verifier trampoline for the shared Evaluator benchmark verifier."""

from evaluator_agent_eval.pytest_verifier import verify_agent_attempt_scores_with_evaluator_sdk
from task_metrics import AgentTargetConfigurationMetric


def test_agent_attempt_scores_with_evaluator_sdk():
    verify_agent_attempt_scores_with_evaluator_sdk(task_specific_metrics=[AgentTargetConfigurationMetric()])
