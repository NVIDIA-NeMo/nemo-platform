# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM clients for the Insights Analyst."""

import functools
import os

from nooa.unifiedllm import CompletionClient

_API_BASE = "https://inference-api.nvidia.com/v1"
# The leading ``openai/`` selects LiteLLM's OpenAI-compatible transport. The
# remaining value is the model alias sent unchanged to NVIDIA's gateway.
# Prefer a non-Bedrock smart model: Bedrock Opus via the gateway currently
# rejects Nooa's tool_choice=auto + parallel_tool_calls=false as a duplicate
# toolChoice / tool_choice field conflict.
_SMART_MODEL = "openai/openai/openai/gpt-5.5"
_FAST_MODEL = "openai/openai/openai/gpt-5-mini"


@functools.cache
def _completion_client(name: str, api_base: str, api_key: str) -> CompletionClient:
    """Reuse clients by their complete inference identity."""
    return CompletionClient(name, api_base=api_base, api_key=api_key)


@functools.cache
def get_smart_model() -> CompletionClient:
    """Return the cached high-capability model used for analysis."""
    return _completion_client(_SMART_MODEL, _API_BASE, os.environ["INFERENCE_API_KEY"])


@functools.cache
def get_fast_model() -> CompletionClient:
    """Return the cached low-latency model used for context summarization."""
    return _completion_client(_FAST_MODEL, _API_BASE, os.environ["INFERENCE_API_KEY"])
