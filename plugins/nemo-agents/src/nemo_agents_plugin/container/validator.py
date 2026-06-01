# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build-time content validation for NAT agent configs.

Performs structural checks on agent YAML before initiating a Docker build,
preventing packaging of invalid or non-agent content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_KNOWN_WORKFLOW_TYPES = frozenset(
    {
        "react_agent",
        "tool_calling_agent",
        "reasoning_agent",
        "rewoo_agent",
    }
)


@dataclass
class ValidationResult:
    """Outcome of agent config validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_agent_config(agent_config: Path) -> ValidationResult:
    """Structurally validate a NAT agent config YAML.

    Checks performed (errors are collected, not short-circuited):

    1. File is valid YAML.
    2. Top-level ``workflow`` key exists.
    3. ``workflow._type`` is present and is a recognised NAT workflow type.
    4. Every name in ``workflow.tool_names`` has a matching entry in
       top-level ``functions`` or ``function_groups``.
    5. ``workflow.llm_name`` (if present) references an entry in ``llms``.
    """
    errors: list[str] = []

    raw = agent_config.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return ValidationResult(valid=False, errors=[f"YAML parse error: {exc}"])

    if not isinstance(data, dict):
        return ValidationResult(valid=False, errors=["Config root must be a YAML mapping."])

    workflow = data.get("workflow")
    if workflow is None:
        errors.append("Missing required top-level key: 'workflow'.")
        return ValidationResult(valid=False, errors=errors)

    if not isinstance(workflow, dict):
        errors.append("'workflow' must be a mapping.")
        return ValidationResult(valid=False, errors=errors)

    wf_type = workflow.get("_type", "")
    if not wf_type:
        # A workflow without ``_type`` is unbuildable — ``nat serve`` cannot
        # construct it and the build would fail at runtime inside the
        # container.  Catch it here so the operator sees a structured
        # error from ``validate_agent_config`` instead of an opaque NAT
        # traceback after a successful image build.
        errors.append(f"Missing required workflow._type. Expected one of: {', '.join(sorted(_KNOWN_WORKFLOW_TYPES))}.")
    elif wf_type not in _KNOWN_WORKFLOW_TYPES:
        errors.append(
            f"Unknown workflow type '{wf_type}'. Expected one of: {', '.join(sorted(_KNOWN_WORKFLOW_TYPES))}."
        )

    functions = set(data.get("functions", {}).keys()) if isinstance(data.get("functions"), dict) else set()
    function_groups = (
        set(data.get("function_groups", {}).keys()) if isinstance(data.get("function_groups"), dict) else set()
    )
    available_tools = functions | function_groups

    # ``tool_names`` / ``llm_name`` / ``llms`` are validated for *type* first
    # so a typo like ``tool_names: my_tool`` (string instead of list) or
    # ``llms: [...]`` (list instead of mapping) surfaces here as a structured
    # error rather than being silently skipped — the previous behaviour would
    # build a broken image and fail opaquely at ``nat serve`` startup.
    tool_names = workflow.get("tool_names")
    if tool_names is not None:
        if not isinstance(tool_names, list):
            errors.append(f"workflow.tool_names must be a list, got {type(tool_names).__name__}.")
        else:
            for name in tool_names:
                if name not in available_tools:
                    errors.append(
                        f"Tool '{name}' in workflow.tool_names not found in 'functions' or 'function_groups'."
                    )

    llm_name = workflow.get("llm_name")
    if llm_name is not None:
        if not isinstance(llm_name, str):
            errors.append(f"workflow.llm_name must be a string, got {type(llm_name).__name__}.")
        else:
            llms = data.get("llms")
            if llms is None:
                errors.append(f"LLM '{llm_name}' in workflow.llm_name not found in 'llms'.")
            elif not isinstance(llms, dict):
                errors.append(f"'llms' must be a mapping, got {type(llms).__name__}.")
            elif llm_name not in llms:
                errors.append(f"LLM '{llm_name}' in workflow.llm_name not found in 'llms'.")

    return ValidationResult(valid=len(errors) == 0, errors=errors)
