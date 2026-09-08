# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build the built-in ``nemo_guardrails`` Relay component that does the judging.

The same component config is exposed two ways:
  * ``nemo_guardrails_component_spec()`` -> a ``plugin.ComponentSpec`` for direct
    activation via ``plugin.plugin(...)`` (used by demos/run_spike.py).
  * ``guardrails_component_config()`` -> the raw config dict for Fabric's
    ``RelayComponentConfig(kind="nemo_guardrails", config=...)`` (used by
    demos/fabric_demo.py).

Only the ``tool_input`` boundary is enabled, so every check runs pre-tool-call
through a single gate. The worker interpreter (nemoguardrails==0.22.0) is resolved
from ``IRON_SWARM_WORKER_PYTHON``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from nemo_relay import plugin

_CONFIG_DIR = str(Path(__file__).resolve().parent.parent / "guardrails_config")


def guardrails_component_config(config_dir: str | None = None) -> dict[str, Any]:
    """Return the ``nemo_guardrails`` component config dict."""
    config: dict[str, Any] = {
        "version": 1,
        "mode": "local",
        "config_path": config_dir or _CONFIG_DIR,
        "codec": "openai_chat",
        "input": False,
        "output": False,
        "tool_input": True,
        "tool_output": False,
        "local": {},
    }
    worker_python = os.environ.get("IRON_SWARM_WORKER_PYTHON")
    if worker_python:
        config["local"]["python_executable"] = worker_python
    return config


def nemo_guardrails_component_spec(config_dir: str | None = None) -> plugin.ComponentSpec:
    """Return a ComponentSpec for direct ``plugin.plugin(...)`` activation."""
    return plugin.ComponentSpec(kind="nemo_guardrails", config=guardrails_component_config(config_dir))
