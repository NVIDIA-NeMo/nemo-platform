# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the vendored Cursor adapter packaging."""

from importlib.metadata import entry_points
from pathlib import Path

import yaml
from nat_cursor_agent_adapter.register import CursorAgentWorkflowConfig

_NEMO_AGENTS_ROOT = Path(__file__).resolve().parents[2]


def test_cursor_agent_workflow_type_registered() -> None:
    assert CursorAgentWorkflowConfig.static_type() == "cursor_agent"


def test_cursor_adapter_nat_components_entry_point_registered() -> None:
    eps = entry_points(group="nat.components")
    ep = next(ep for ep in eps if ep.name == "nat_cursor_agent_adapter")
    assert ep.value == "nat_cursor_agent_adapter.register"


def test_cursor_example_config_validates_without_warnings() -> None:
    from nemo_agents_plugin.container.validator import validate_agent_config

    example = _NEMO_AGENTS_ROOT / "examples" / "cursor-agent" / "cursor-agent.yml"

    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert data["workflow"]["_type"] == "cursor_agent"
    assert data["general"]["telemetry"]["tracing"]["nemo_trace"]["_type"] == "nemo_files"

    result = validate_agent_config(example)
    assert result.valid
    assert result.errors == []
    assert result.warnings == []
