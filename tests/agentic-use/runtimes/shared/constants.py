# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared constants for agentic-use AgentAttemptRuntime implementations."""

from __future__ import annotations

from pathlib import Path

AGENTIC_USE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = AGENTIC_USE_DIR.parents[1]
SHARED_DIR = AGENTIC_USE_DIR / "shared"
EVALUATOR_SDK_SRC = REPO_ROOT / "packages" / "nemo_evaluator_sdk" / "src"

NAT_TRACE_EXPORT_SCRIPT_CONTAINER_PATH = "/app/tests/agentic-use/scripts/nat_trace_export.py"
DEFAULT_LOCAL_NMP_BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT_SEC = 600
FILES_STORAGE_CONFIG = '{"type":"local","path":"/data/files_storage"}'
PLATFORM_CONFIG_PATH = "/app/packages/nmp_platform/config/local.yaml"
DOCKER_SOCKET_HOST_PATH = Path("/var/run/docker.sock")
DOCKER_SOCKET_CONTAINER_PATH = "/var/run/docker.sock"

INSTRUCTION_CONTAINER_PATH = "/tmp/nat_instruction.md"
WORKFLOW_CONTAINER_PATH = "/tmp/nat_workflow.yml"
