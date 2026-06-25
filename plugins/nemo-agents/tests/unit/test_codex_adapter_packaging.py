# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the vendored Codex adapter packaging."""

from importlib.metadata import entry_points

from nat_codex_agent_adapter.register import CodexAgentWorkflowConfig


def test_codex_agent_workflow_type_registered() -> None:
    assert CodexAgentWorkflowConfig._typed_model_name == "codex_agent"


def test_codex_adapter_nat_components_entry_point_registered() -> None:
    eps = entry_points(group="nat.components")
    ep = next(ep for ep in eps if ep.name == "nat_codex_agent_adapter")
    assert ep.value == "nat_codex_agent_adapter.register"
