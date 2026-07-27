# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare Platform-owned environment paths before Fabric runtime startup."""

from pathlib import Path

from nemo_agents_plugin.agent_config import AgentConfig


def ensure_local_workspace_dir(agent_config: AgentConfig, base_dir: Path) -> None:
    """Create the configured local workspace relative to the agent base directory."""
    if agent_config.environment.provider != "local":
        return

    workspace = Path(agent_config.environment.workspace)
    if not workspace.is_absolute():
        workspace = base_dir / workspace
    workspace.mkdir(parents=True, exist_ok=True)
