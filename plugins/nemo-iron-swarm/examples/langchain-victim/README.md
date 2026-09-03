<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# The war-game victim, LangChain (BYO)

A bring-your-own agent built with LangChain's `create_agent`, served over
`/v1/chat/completions`. Two tools worth attacking — `bash_executor`, `python_executor` — that
really run what they're given.

```
agent.py         create_agent with NemoRelayMiddleware — the whole tool-path obligation
server.py        FastAPI serving loop — starts Relay, opens a scope per request
Dockerfile       your image; everything Iron Swarm derives, it derives from here
```

This is the simplest victim to instrument: `middleware=[NemoRelayMiddleware()]` on `create_agent`
is the one interception line — no ToolNode to wire by hand.

## Running it

```bash
export NMP_BASE_URL=http://localhost:8080

nemo iron-swarm init --project-dir plugins/nemo-iron-swarm/examples/langchain-victim \
    --name langchain-victim --harness langchain --relay-confirmed
nemo iron-swarm synth-benign --manifest-id langchain-victim --yes
nemo iron-swarm run --manifest-id langchain-victim
```
