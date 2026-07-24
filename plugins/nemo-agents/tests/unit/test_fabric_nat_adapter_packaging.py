# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Packaging assertions for the Platform-owned NAT Fabric adapter."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_DESCRIPTOR = _PLUGIN_ROOT / "src" / "nemo_agents_plugin" / "fabric" / "adapters" / "nat" / "fabric-adapter.json"


def test_nat_adapter_descriptor_is_narrow_and_platform_owned() -> None:
    descriptor = json.loads(_DESCRIPTOR.read_text(encoding="utf-8"))

    assert descriptor == {
        "contract_version": "fabric.adapter/v1alpha1",
        "adapter_id": "nvidia.nemo.platform.nat",
        "harness": "nat",
        "adapter_kind": "python",
        "runner": {
            "module": "nemo_agents_plugin.fabric.adapters.nat.adapter",
        },
        "config": {
            "accepts": ["mcp", "tools", "tools.blocked"],
        },
        "capabilities": {
            "cancellation": False,
            "service": False,
            "streaming": False,
            "updates": False,
        },
    }


def test_nat_adapter_descriptor_is_installed_as_shared_data() -> None:
    pyproject = tomllib.loads((_PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    shared_data = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["shared-data"]

    assert shared_data == {
        "src/nemo_agents_plugin/fabric/adapters/nat/fabric-adapter.json": (
            "share/nemo-fabric/adapters/nemo-platform-nat/fabric-adapter.json"
        )
    }
