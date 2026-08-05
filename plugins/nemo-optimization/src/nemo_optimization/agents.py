# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Platform agent resolution for optimize studies."""

from __future__ import annotations

import logging
from typing import Any

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.run_dependencies import LocalRunError

logger = logging.getLogger(__name__)


def resolve_agent_config(
    agent: str | None,
    *,
    workspace: str,
    sdk: NeMoPlatform | None,
) -> dict[str, Any] | None:
    """Fetch a platform-managed agent's stored Fabric config, if *agent* is set."""
    if agent is None:
        return None

    if "://" in agent:
        raise LocalRunError(
            "Endpoint URL / URI optimize mode has been removed. Pass a platform-managed "
            "Fabric agent name (e.g. --agent hermes-optimize-chatonly or "
            "--agent default/hermes-optimize-chatonly), not an http(s):// or file:// URL. "
            "Or include an inline Fabric agent package in optimize_config."
        )

    if "/" in agent:
        ws, name = agent.split("/", 1)
    else:
        ws, name = workspace, agent

    if sdk is None:
        raise LocalRunError(
            f"An optimize study with --agent {agent!r} requires a platform SDK to fetch the "
            "stored agent config. Set NEMO_BASE_URL or pass sdk via NemoJobScheduler.run_local(sdk=...)."
        )

    agent_dict = sdk.agents.get(name=name, workspace=ws)
    agent_config = agent_dict["config"] if isinstance(agent_dict, dict) else getattr(agent_dict, "config", {})
    if not isinstance(agent_config, dict) or not agent_config:
        raise RuntimeError(f"Agent '{ws}/{name}' has an empty or invalid stored config; cannot optimize it.")
    logger.info("Resolved agent %r to platform Fabric agent %s/%s", agent, ws, name)
    return agent_config
