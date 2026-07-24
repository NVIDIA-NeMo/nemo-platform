# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Fabric-backed calculator example."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from nemo_agents_plugin.agent_config import load_agent_config
from nemo_agents_plugin.fabric.translator import translate_agent_config
from nemo_fabric import Fabric

EXAMPLE_DIR = Path(__file__).parents[2] / "examples/calculator-agent/fabric"
CALCULATOR = EXAMPLE_DIR / "workspace/calculator.py"


def test_example_translates_to_codex_fabric_config() -> None:
    config = load_agent_config(EXAMPLE_DIR / "agent.yaml")

    fabric_config = translate_agent_config(config)

    assert config.name == "fabric-calculator-agent"
    assert fabric_config.harness.adapter_id == "nvidia.fabric.codex"
    assert fabric_config.environment is not None
    assert fabric_config.environment.workspace == "./workspace"
    assert fabric_config.environment.artifacts == "./artifacts"
    assert "python calculator.py" in fabric_config.harness.settings["developer_instructions"]

    plan = Fabric().plan(fabric_config, base_dir=EXAMPLE_DIR)
    assert plan.adapter.adapter_id == "nvidia.fabric.codex"


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["add", "15.5", "20", "4.5"], "40"),
        (["subtract", "10", "3.25"], "6.75"),
        (["multiply", "12", "8"], "96"),
        (["divide", "7.5", "2.5"], "3"),
        (["compare", "42", "17"], "42 is greater than 17"),
    ],
)
def test_calculator_cli(arguments: list[str], expected: str) -> None:
    result = subprocess.run(
        [sys.executable, str(CALCULATOR), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == expected


def test_calculator_cli_rejects_division_by_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(CALCULATOR), "divide", "10", "0"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "cannot divide by zero" in result.stderr
