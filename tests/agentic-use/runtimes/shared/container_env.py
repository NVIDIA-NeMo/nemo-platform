# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared container environment helpers."""

from __future__ import annotations

import json
from typing import Any

from runtimes.shared.config import AgenticSharedConfig
from runtimes.shared.constants import (
    DOCKER_SOCKET_CONTAINER_PATH,
    DOCKER_SOCKET_HOST_PATH,
    FILES_STORAGE_CONFIG,
    PLATFORM_CONFIG_PATH,
)


def base_container_env(shared: AgenticSharedConfig, *, timeout_sec: int) -> dict[str, str]:
    """Environment variables shared by all agentic-use container runs."""
    env: dict[str, str] = {
        "NMP_BASE_URL": shared.nmp_base_url,
        "AGENTIC_USE_WORKSPACE_DIR": "/app/workspace",
        "DATABASE_DIALECT": "sqlite",
        "DATABASE_PATH": "/data/nmp-platform.db",
        "NMP_FILES_DEFAULT_STORAGE_CONFIG": FILES_STORAGE_CONFIG,
        "NMP_CONFIG_FILE_PATH": PLATFORM_CONFIG_PATH,
        "NEMO_AGENTS_GATEWAY_READ_TIMEOUT": str(timeout_sec),
        "NEMO_AGENTS_INVOKE_TIMEOUT": str(timeout_sec),
        "AUT_INVOKE_HTTP_TIMEOUT": str(timeout_sec),
    }
    if DOCKER_SOCKET_HOST_PATH.exists():
        env["DOCKER_HOST"] = f"unix://{DOCKER_SOCKET_CONTAINER_PATH}"
    return env


def with_candidate_params(env: dict[str, str], agent_params: dict[str, Any]) -> dict[str, str]:
    if agent_params:
        env = dict(env)
        env["NAT_CANDIDATE_PARAMS"] = json.dumps(agent_params, sort_keys=True)
    return env
