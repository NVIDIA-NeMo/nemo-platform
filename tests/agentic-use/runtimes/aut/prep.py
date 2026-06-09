# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare AUT agent configs for container execution."""

from __future__ import annotations

from pathlib import Path

import yaml

from runtimes.shared.constants import DEFAULT_LOCAL_NMP_BASE_URL


def prepare_aut_config_for_runtime(
    config_path: Path,
    output_dir: Path,
    *,
    nat_model: str | None = None,
    nmp_base_url: str = DEFAULT_LOCAL_NMP_BASE_URL,
    workspace: str = "default",
) -> Path:
    """Prepare AUT config for IGW-routed container runtime."""
    from nemo_agents_plugin.utils import inject_gateway_url

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    if nat_model:
        for llm_cfg in config.get("llms", {}).values():
            if isinstance(llm_cfg, dict) and llm_cfg.get("_type") in ("openai", "nim"):
                llm_cfg["model_name"] = nat_model
                break

    config = inject_gateway_url(config, workspace, base_url=nmp_base_url)

    rewritten = output_dir / "aut.runtime.yml"
    with rewritten.open("w", encoding="utf-8") as handle:
        yaml.dump(config, handle, default_flow_style=False, sort_keys=False)
    return rewritten
