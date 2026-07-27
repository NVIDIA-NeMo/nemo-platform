# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Custom Fabric adapter: deepagents + the context workaround, registered IN the
adapter subprocess.

Fabric runs the deepagents adapter as a separate subprocess (``python -m
<runner.module>``), so intercepts registered in the driver never reach it -- which
is why the user-turn guardrails saw an empty conversation. This thin adapter is
our ``runner.module`` (see ``../adapters/quill-relay/fabric-adapter.json``). When
Fabric launches it, ``register_context_workaround()`` runs **here, in the adapter
subprocess**, installing the capture/inject/strip intercepts where the agent's
real model/tool calls happen. Then it serves the STOCK ``DeepAgentsRuntime``
unchanged, so we keep all of Fabric's behavior (model/MCP/tools/checkpointer/
observability).

This whole file is scaffolding: it disappears when Relay carries conversation
context across the tool boundary natively (the feature request).
"""

from __future__ import annotations

from nemo_fabric_adapters.common import lifecycle
from nemo_fabric_adapters.deepagents.adapter import DeepAgentsRuntime

from relay_guardrails.context import register_context_workaround

# Runs at import -- i.e. in the adapter subprocess, before the agent starts. This
# placement (not the driver) is the entire point of this adapter.
register_context_workaround()


def main() -> None:
    lifecycle.serve(DeepAgentsRuntime)


if __name__ == "__main__":
    main()
