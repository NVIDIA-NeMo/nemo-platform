# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml
from nemo_optimization.backends.optuna.search_space import parse_search_space
from nemo_optimization.fabric import is_fabric_agent_config, require_fabric_agent_config

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "nat_to_fabric.py"
_SPEC = importlib.util.spec_from_file_location("nat_to_fabric_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
nat_to_fabric = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(nat_to_fabric)

convert_nat_to_fabric = nat_to_fabric.convert_nat_to_fabric
NatToFabricError = nat_to_fabric.NatToFabricError

_EXAMPLES = Path(__file__).resolve().parents[2] / "nemo-agents" / "examples"
_REACT_AGENT = _EXAMPLES / "react-agent" / "react-agent.yml"
_REACT_OPTIMIZE = _EXAMPLES / "react-agent" / "react-optimize.yml"
_CALC_AGENT = _EXAMPLES / "calculator-agent" / "src" / "calculator_agent" / "calculator-agent.yml"
_CALC_OPTIMIZE = _EXAMPLES / "calculator-agent" / "src" / "calculator_agent" / "calculator-optimize.yml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_convert_react_agent_workflow() -> None:
    converted = convert_nat_to_fabric(_load(_REACT_AGENT), agent_name="react-agent")

    require_fabric_agent_config(converted)
    assert converted["harness"]["adapter_id"] == "nvidia.fabric.langchain.react"
    assert converted["harness"]["settings"]["workflow"]["tool_names"] == ["wiki", "clock"]
    assert converted["harness"]["settings"]["workflow"]["llm_name"] == "default"
    assert converted["models"]["default"]["model"] == "${NEMO_DEFAULT_MODEL}"
    assert converted["harness"]["settings"]["tools"]["wiki"]["kind"] == "wiki_search"


def test_convert_calculator_agent_workflow() -> None:
    converted = convert_nat_to_fabric(_load(_CALC_AGENT), agent_name="calculator-agent")

    tools = converted["harness"]["settings"]["tools"]
    assert tools["calculator"]["kind"] == "function_group"
    assert tools["calculator"]["include"] == ["add", "subtract", "multiply", "divide", "compare"]
    assert converted["harness"]["settings"]["workflow"]["use_native_tool_calling"] is True


def test_convert_react_optimize_overlay() -> None:
    converted = convert_nat_to_fabric(
        _load(_REACT_OPTIMIZE),
        agent_name="react-optimize",
        fabric_base_dir="/tmp/fabric-example",
        capture_trajectory=True,
    )

    require_fabric_agent_config(converted)
    assert converted["models"]["default"]["temperature"] == 0.0
    assert converted["models"]["judge"]["model"] == "nvidia-nemotron-3-super-120b-a12b"
    assert converted["eval"]["evaluators"]["accuracy"]["llm_name"] == "judge"
    assert converted["eval"]["fabric"]["base_dir"] == "/tmp/fabric-example"
    assert converted["eval"]["fabric"]["capture_trajectory"] is True

    search_space = parse_search_space(converted["optimizer"])
    assert "models.default.temperature" in search_space
    assert "models.default.top_p" in search_space
    assert converted["optimizer"]["eval_metrics"]["accuracy"]["evaluator_name"] == "average_score"


def test_convert_calculator_optimize_overlay() -> None:
    converted = convert_nat_to_fabric(_load(_CALC_OPTIMIZE), agent_name="calculator-optimize")

    search_space = parse_search_space(converted["optimizer"])
    assert set(search_space) == {"models.default.temperature", "models.default.top_p"}
    assert converted["eval"]["evaluators"]["accuracy"]["llm_name"] == "judge"


def test_convert_merged_agent_and_optimize_configs() -> None:
    merged = {**_load(_REACT_AGENT), **_load(_REACT_OPTIMIZE)}
    converted = convert_nat_to_fabric(merged, agent_name="react-merged")

    assert converted["harness"]["settings"]["workflow"]["tool_names"] == ["wiki", "clock"]
    assert "models.default.temperature" in parse_search_space(converted["optimizer"])
    assert converted["eval"]["general"]["max_concurrency"] == 4


def test_convert_rejects_unsupported_workflow_type() -> None:
    config = {
        "workflow": {"_type": "tool_calling_agent"},
        "llms": {"llm": {"_type": "openai", "model_name": "test"}},
        "optimizer": {"numeric": {"enabled": True}, "search_space": {"models.default.temperature": {"values": [0.0]}}},
    }
    try:
        convert_nat_to_fabric(config)
    except NatToFabricError as exc:
        assert "tool_calling_agent" in str(exc)
    else:
        raise AssertionError("expected NatToFabricError")


def test_convert_file_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "nat.yml"
    dest = tmp_path / "fabric.yml"
    source.write_text(_REACT_OPTIMIZE.read_text(encoding="utf-8"), encoding="utf-8")

    converted = convert_nat_to_fabric(yaml.safe_load(source.read_text(encoding="utf-8")))
    dest.write_text(yaml.safe_dump(converted, sort_keys=False), encoding="utf-8")

    loaded = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert is_fabric_agent_config(loaded)
