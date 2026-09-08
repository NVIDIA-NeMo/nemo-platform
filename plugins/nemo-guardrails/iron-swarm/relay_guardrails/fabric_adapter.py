# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Custom Fabric adapter: the stock deepagents runtime plus the context intercepts,
registered inside the adapter subprocess.

Fabric runs the deepagents adapter as a separate subprocess (``python -m
<runner.module>``), so intercepts registered in the driver process never reach the
agent. This thin adapter is the ``runner.module`` named in
``../adapters/quill-relay/fabric-adapter.json``: when Fabric launches it,
``register_context_workaround()`` runs here, in the subprocess, installing the
capture/inject/strip intercepts where the agent's real model and tool calls happen.
It then serves the stock ``DeepAgentsRuntime`` unchanged, preserving all of Fabric's
behavior (model, MCP, tools, checkpointer, observability).

This is a workaround; it is removed once Relay carries conversation context across
the tool boundary natively.
"""

from __future__ import annotations

from nemo_fabric_adapters.common import lifecycle
from nemo_fabric_adapters.deepagents.adapter import DeepAgentsRuntime

from relay_guardrails.context import register_context_workaround

# Runs at import, i.e. inside the adapter subprocess before the agent starts --
# the placement that lets the intercepts reach the agent's real calls.
register_context_workaround()


def main() -> None:
    lifecycle.serve(DeepAgentsRuntime)


if __name__ == "__main__":
    main()
