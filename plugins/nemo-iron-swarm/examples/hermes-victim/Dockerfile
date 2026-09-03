# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# The image for a Hermes-harness Fabric agent, owned by its author rather than rendered.
#
# It is a normal Fabric image plus the war-game requirements, plus TWO Hermes-only lines that do
# what a `telemetry:` block does for the DeepAgents victim — because Hermes reaches Relay through
# an opt-in plugin, not through the adapter's telemetry wiring.
FROM python:3.12-slim

# iproute2 and a `sandbox` user: the OpenShell sandbox needs both.  [war-game]
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system sandbox \
 && useradd --system --gid sandbox --create-home --home-dir /home/sandbox --shell /bin/bash sandbox

WORKDIR /workspace

# The Fabric entrypoint, its Hermes adapter, and the MCP SDK the tool server uses.
# nemo-relay is pinned <0.8 because the Fabric adapters cap it there (same reason the uploaded
# plugins.toml uses observability schema 3).
RUN python -m venv /workspace/.venv \
 && /workspace/.venv/bin/pip install --no-cache-dir \
      "nemo-platform[nemo-agents-plugin]" \
      "nemo-fabric" \
      "nemo-fabric-adapters-hermes" \
      "nemo-relay>=0.7.2,<0.8" \
      "mcp[cli]"

COPY agent.yaml /workspace/agent.yaml
COPY ledger_mcp.py /app/ledger_mcp.py

# Relay reads system-layer plugin config from here, and Iron Swarm uploads each round's guardrails
# into it before the victim starts.  [war-game]
RUN mkdir -p /etc/nemo-relay /home/sandbox/.iron-swarm/relay \
 && chown -R sandbox:sandbox /etc/nemo-relay /home/sandbox/.iron-swarm /workspace /app

# --- The two Hermes-only lines. [hermes] ---
#
# Hermes reads Relay's plugin config ONLY from this env var — not from /etc/nemo-relay, which Relay
# discovers on its own for every other integration. Point it at the file Iron Swarm uploads into.
ENV HERMES_NEMO_RELAY_PLUGINS_TOML=/etc/nemo-relay/plugins.toml
# Relay is an opt-in Hermes plugin. Without enabling it, its middleware never registers and the env
# var above is read by nobody — the victim runs, emits nothing, and the run's preflight fails it.
RUN /workspace/.venv/bin/hermes plugins enable observability/nemo_relay

ENV AGENT_CONFIG_PATH=/workspace/agent.yaml
ENV PORT=8000
ENV PATH="/workspace/.venv/bin:$PATH"
ENV VIRTUAL_ENV=/workspace/.venv

USER sandbox
EXPOSE 8000

# The Fabric contract: serve the agent on $PORT. Run explicitly rather than via ENTRYPOINT metadata,
# because `openshell sandbox exec` does not propagate image ENV (neither PATH nor AGENT_CONFIG_PATH).
ENTRYPOINT ["sh", "-c", "exec python -m nemo_agents_plugin.fabric.server --agent-config \"$AGENT_CONFIG_PATH\" --host 0.0.0.0 --port \"$PORT\""]
