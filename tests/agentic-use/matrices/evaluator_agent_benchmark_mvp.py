# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Default MVP matrix for Evaluator agent benchmark runs."""

from __future__ import annotations

from agent_matrix_benchmark import (
    AgentMatrixConfig,
    CandidateConfig,
    ClaudeCodeParams,
    CodexParams,
    CursorAgentParams,
    MatrixDefaults,
)

MATRIX = AgentMatrixConfig(
    manifest="manifests/evaluator_agent_benchmark_mvp.txt",
    defaults=MatrixDefaults(
        timeout=600,
        skip_build=True,
        allow_dirty=True,
    ),
    candidates=[
        CandidateConfig(
            id="codex-gpt-5.5-high-standard",
            backend="codex",
            model="gpt-5.5",
            params=CodexParams(intelligence="high", speed="standard"),
        ),
        CandidateConfig(
            id="codex-gpt-5.5-high-fast",
            backend="codex",
            model="gpt-5.5",
            params=CodexParams(intelligence="high", speed="fast"),
        ),
        CandidateConfig(
            id="claude-code-sonnet-4-6",
            backend="claude-code",
            model="aws/anthropic/bedrock-claude-sonnet-4-6",
            params=ClaudeCodeParams(permission_mode="bypassPermissions"),
        ),
        CandidateConfig(
            id="cursor-agent-gpt-5.5-high",
            backend="cursor-agent",
            model="gpt-5.5-high",
            params=CursorAgentParams(sandbox="disabled"),
        ),
        CandidateConfig(
            id="cursor-agent-sonnet-4",
            backend="cursor-agent",
            model="sonnet-4",
            params=CursorAgentParams(sandbox="disabled"),
        ),
    ],
)
