# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

GUARDRAILS_PLUGIN_CONFIG_TYPE = "guardrail_config"
# Rail types to execute in the process_request middleware.
PROCESS_REQUEST_RAIL_TYPES = ["input"]
# Rail types to execute in the process_response middleware.
PROCESS_RESPONSE_RAIL_TYPES = ["output"]
# Rail types for tool call and tool result rails.
PROCESS_TOOL_OUTPUT_RAIL_TYPES = ["tool_output"]
PROCESS_TOOL_INPUT_RAIL_TYPES = ["tool_input"]
# Role to use in the message if the user requests guardrails_data
# to be injected as a response choice.
GUARDRAILS_DATA_MESSAGE_ROLE = "guardrails_data"


DEFAULT_MAIN_ENGINE = "nim"
"""Fallback engine for configs without a ``main`` entry; matches the NIM-default IGW deployment."""


W3C_TRACE_CONTEXT_HEADERS = frozenset({"traceparent", "tracestate", "baggage"})
"""W3C Trace Context headers forwarded alongside the ``x-*`` allowlist (they have no ``x-`` prefix)."""
