# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the vendored Claude Code adapter packaging."""

from importlib.metadata import entry_points
from pathlib import Path

import yaml
from nat_claude_code_agent_adapter.register import ClaudeCodeAgentWorkflowConfig

_NEMO_AGENTS_ROOT = Path(__file__).resolve().parents[2]


def test_claude_code_agent_workflow_type_registered() -> None:
    assert ClaudeCodeAgentWorkflowConfig.static_type() == "claude_code_agent"


def test_claude_code_adapter_nat_components_entry_point_registered() -> None:
    eps = entry_points(group="nat.components")
    ep = next(ep for ep in eps if ep.name == "nat_claude_code_agent_adapter")
    assert ep.value == "nat_claude_code_agent_adapter.register"


def test_claude_code_example_config_validates_without_warnings() -> None:
    from nemo_agents_plugin.container.validator import validate_agent_config

    example = _NEMO_AGENTS_ROOT / "examples" / "claude-code-agent" / "claude-code-agent.yml"

    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert data["workflow"]["_type"] == "claude_code_agent"
    assert data["general"]["telemetry"]["tracing"]["nemo_trace"]["_type"] == "nemo_files"

    result = validate_agent_config(example)
    assert result.valid
    assert result.errors == []
    assert result.warnings == []
