# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_optimization.fabric import (
    FabricOptimizeError,
    build_optimize_payload,
    is_fabric_agent_config,
    looks_like_nat_config,
    require_fabric_agent_config,
)

FABRIC_AGENT = {
    "schema_version": "fabric.agent/v1alpha1",
    "metadata": {"name": "react-optimize-agent"},
    "harness": {"adapter_id": "nvidia.fabric.langchain.react"},
}

NAT_AGENT = {
    "workflow": {"_type": "react_agent"},
    "llms": {"llm": {"_type": "openai", "model_name": "test"}},
}


def test_is_fabric_agent_config() -> None:
    assert is_fabric_agent_config(FABRIC_AGENT)
    assert not is_fabric_agent_config(NAT_AGENT)


def test_looks_like_nat_config() -> None:
    assert looks_like_nat_config(NAT_AGENT)
    assert not looks_like_nat_config(FABRIC_AGENT)


def test_require_fabric_agent_rejects_nat() -> None:
    with pytest.raises(FabricOptimizeError, match="legacy NAT"):
        require_fabric_agent_config(NAT_AGENT)


def test_build_optimize_payload_merges_sections() -> None:
    payload = build_optimize_payload(
        agent_config=FABRIC_AGENT,
        optimize_config={
            "optimizer": {"numeric": {"enabled": True, "n_trials": 3}},
            "eval": {"general": {"dataset": "rows.json"}},
        },
    )
    assert payload["schema_version"] == "fabric.agent/v1alpha1"
    assert payload["optimizer"]["numeric"]["enabled"] is True
    assert payload["eval"]["general"]["dataset"] == "rows.json"
