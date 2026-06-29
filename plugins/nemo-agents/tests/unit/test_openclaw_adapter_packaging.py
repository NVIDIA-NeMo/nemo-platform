# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the vendored OpenClaw adapter packaging."""

from importlib.metadata import distribution
from pathlib import Path

import yaml
from nat_openclaw_agent_adapter.register import OpenClawAgentWorkflowConfig

_NEMO_AGENTS_ROOT = Path(__file__).resolve().parents[2]


def test_openclaw_agent_workflow_type_registered() -> None:
    assert OpenClawAgentWorkflowConfig.static_type() == "openclaw_agent"


def test_openclaw_adapter_nat_components_entry_point_registered() -> None:
    eps = distribution("nemo-agents-plugin").entry_points
    ep = next(ep for ep in eps if ep.group == "nat.components" and ep.name == "nat_openclaw_agent_adapter")
    assert ep.value == "nat_openclaw_agent_adapter.register"


def test_openclaw_example_config_validates_without_warnings() -> None:
    from nemo_agents_plugin.container.validator import validate_agent_config

    example = _NEMO_AGENTS_ROOT / "examples" / "openclaw-agent" / "openclaw-agent.yml"

    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert data["workflow"]["_type"] == "openclaw_agent"
    assert data["general"]["telemetry"]["tracing"]["nemo_trace"]["_type"] == "nemo_files"

    result = validate_agent_config(example)
    assert result.valid
    assert result.errors == []
    assert result.warnings == []
