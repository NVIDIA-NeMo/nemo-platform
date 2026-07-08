# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fabric-native optimize payload helpers."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

FABRIC_AGENT_SCHEMA_VERSION = "fabric.agent/v1alpha1"

_NAT_TOP_LEVEL_KEYS = frozenset(
    {
        "workflow",
        "llms",
        "functions",
        "function_groups",
        "embedders",
        "general",
    }
)


class FabricOptimizeError(ValueError):
    """Raised when optimize input is not Fabric-native."""


def is_fabric_agent_config(config: Mapping[str, Any]) -> bool:
    return config.get("schema_version") == FABRIC_AGENT_SCHEMA_VERSION


def looks_like_nat_config(config: Mapping[str, Any]) -> bool:
    if is_fabric_agent_config(config):
        return False
    return any(key in config for key in _NAT_TOP_LEVEL_KEYS)


def require_fabric_agent_config(config: Mapping[str, Any], *, label: str = "agent config") -> dict[str, Any]:
    if is_fabric_agent_config(config):
        return copy.deepcopy(dict(config))
    if looks_like_nat_config(config):
        raise FabricOptimizeError(
            f"{label} appears to be legacy NAT workflow YAML. "
            "Optimize now requires Fabric-native input "
            f"(schema_version: {FABRIC_AGENT_SCHEMA_VERSION}). "
            "Convert legacy configs with scripts/nat_to_fabric.py before submitting."
        )
    raise FabricOptimizeError(
        f"{label} must declare schema_version {FABRIC_AGENT_SCHEMA_VERSION!r}. "
        "Inline Fabric agent packages and platform agent entities must use the Fabric agent schema."
    )


def build_optimize_payload(
    *,
    agent_config: dict[str, Any] | None,
    optimize_config: dict[str, Any],
) -> dict[str, Any]:
    """Compose a Fabric agent package dict with optimizer/eval overlays."""
    if agent_config is None:
        payload = require_fabric_agent_config(optimize_config, label="optimize config")
    else:
        payload = require_fabric_agent_config(agent_config, label="agent config")
        for key in ("optimizer", "eval"):
            if key in optimize_config:
                payload[key] = copy.deepcopy(optimize_config[key])

    if "optimizer" not in payload:
        raise FabricOptimizeError("optimize config must declare an 'optimizer' section.")
    return payload

