# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration models for agentic-use runtimes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from runtimes.shared.constants import AGENTIC_USE_DIR, DEFAULT_LOCAL_NMP_BASE_URL, DEFAULT_TIMEOUT_SEC, REPO_ROOT

AgenticRuntimeName = Literal["aut", "workflow", "claude-code", "codex", "cursor-agent"]


@dataclass(frozen=True)
class AgenticSharedConfig:
    """Settings common to every agentic-use runtime."""

    tasks_dir: Path = AGENTIC_USE_DIR
    jobs_dir: Path | None = None
    repo_root: Path = REPO_ROOT
    nmp_base_url: str = DEFAULT_LOCAL_NMP_BASE_URL
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    nvidia_api_key: str | None = None
    docker_extra_args: list[str] = field(default_factory=list)
    run_verify: bool = False
    smoke_workspace: str | None = None


@dataclass(frozen=True)
class WorkflowRuntimeConfig:
    """Configuration for :class:`NatWorkflowAttemptRuntime`."""

    shared: AgenticSharedConfig = field(default_factory=AgenticSharedConfig)
    agent_model: str | None = None


@dataclass(frozen=True)
class AutRuntimeConfig:
    """Configuration for :class:`AutAgentAttemptRuntime`."""

    shared: AgenticSharedConfig = field(default_factory=AgenticSharedConfig)
    aut_agent_name: str = ""
    aut_agent_config: Path | None = None
    aut_seed_providers: bool = True
    agent_model: str | None = None
    anthropic_api_key: str | None = None
    inference_nvidia_api_key: str | None = None
    aut_health_wait_seconds: int = int(os.environ.get("NAT_AUT_HEALTH_WAIT_SECONDS", "60"))


@dataclass(frozen=True)
class ClaudeCodeRuntimeConfig:
    """Configuration for :class:`ClaudeCodeAgentAttemptRuntime`."""

    shared: AgenticSharedConfig = field(default_factory=AgenticSharedConfig)
    agent_model: str | None = None
    agent_params: dict[str, Any] = field(default_factory=dict)
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://inference-api.nvidia.com"


@dataclass(frozen=True)
class CodexRuntimeConfig:
    """Configuration for :class:`CodexAgentAttemptRuntime`."""

    shared: AgenticSharedConfig = field(default_factory=AgenticSharedConfig)
    agent_model: str | None = None
    agent_params: dict[str, Any] = field(default_factory=dict)
    codex_auth_json: Path | None = None


@dataclass(frozen=True)
class CursorAgentRuntimeConfig:
    """Configuration for :class:`CursorAgentAttemptRuntime`."""

    shared: AgenticSharedConfig = field(default_factory=AgenticSharedConfig)
    agent_model: str | None = None
    agent_params: dict[str, Any] = field(default_factory=dict)
