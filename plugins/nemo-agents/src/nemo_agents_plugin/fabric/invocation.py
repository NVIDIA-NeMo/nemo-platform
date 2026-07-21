# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""One-shot invocation helpers for Platform-owned Fabric agent configs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.runtime import FabricRuntimeRequest, FabricRuntimeResult, run_fabric_agent_once
from nemo_agents_plugin.fabric.translator import translate_agent_config


async def invoke_agent_config_once(
    config: dict[str, Any],
    inputs: Sequence[Any],
    *,
    base_dir: Path,
) -> list[FabricRuntimeResult]:
    """Translate a Platform agent config and run each input through Fabric once."""
    agent_config = AgentConfig.model_validate(config)
    fabric_config = translate_agent_config(agent_config)

    results: list[FabricRuntimeResult] = []
    for item in inputs:
        results.append(
            await run_fabric_agent_once(
                FabricRuntimeRequest(
                    fabric_config=fabric_config,
                    base_dir=base_dir,
                    input=item,
                )
            )
        )
    return results
