# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared constants for the benchmark harness."""

from __future__ import annotations

WORKSPACE = "benchmark"
GUARDRAIL_CONFIG = "content-safety-local"
VM_NAME = "guardrails-vm"

# ModelProvider that proxies requests to the mock main model
APP_PROVIDER = "benchmark-app-llm"
APP_PROVIDER_URL = "http://localhost:8000"
APP_MODEL_NAME = "meta/llama-3.3-70b-instruct"

# ModelProvider that proxies requests to the mock content-safety model
CS_PROVIDER = "benchmark-content-safety-llm"
CS_PROVIDER_URL = "http://localhost:8001"
CS_MODEL_NAME = "nvidia/llama-3.1-nemoguard-8b-content-safety"

NMP_BASE_URL = "http://localhost:8080"
NMP_HEALTH_PATH = "/health/ready"
IGW_CHAT_PATH = f"/apis/inference-gateway/v2/workspaces/{WORKSPACE}/openai/-/v1/chat/completions"

# Local shim that satisfies AIPerf's pre-check and reverse-proxies chat
# completion requests through to NMP's IGW. See
# `nemo_guardrails_plugin.benchmarks.shim` for the implementation.
AIPERF_SHIM_HOST = "127.0.0.1"
AIPERF_SHIM_PORT = 8090
AIPERF_SHIM_BASE_URL = f"http://{AIPERF_SHIM_HOST}:{AIPERF_SHIM_PORT}"

GUARDRAILS_MIDDLEWARE_NAME = "nemo-guardrails"
GUARDRAILS_MIDDLEWARE_CONFIG_TYPE = "guardrail_config"
