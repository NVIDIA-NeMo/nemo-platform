#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic audit coverage from ATIF tool calls."""

from __future__ import annotations

from typing import Any

from _atif import AtifTraceFacts

METHOD_NAME = "tool_calls"
ITEM_KIND = "tool"
DETAILS_SCHEMA = "nemo.eval_author.audit_tool_calls_details.v1"


def measure(audit: dict[str, Any], trace: AtifTraceFacts) -> dict[str, Any]:
    """Measure audit tool items against the tool calls present in an ATIF trace."""
    audit_tools = [item["name"] for item in audit["items"] if item["kind"] == ITEM_KIND]
    covered = [tool for tool in audit_tools if trace.matches(tool)]
    missing = [tool for tool in audit_tools if tool not in covered]
    return {
        "item_kind": ITEM_KIND,
        "covered": covered,
        "details": {
            "schema": DETAILS_SCHEMA,
            "item_kind": ITEM_KIND,
            "audit_tools": audit_tools,
            "covered": covered,
            "missing": missing,
            "observed_tool_calls": [call.to_json() for call in trace.tool_calls],
            "tool_call_counts": trace.tool_call_counts,
            "matches": {tool: trace.matches(tool) for tool in audit_tools},
        },
    }
