<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# The war-game victim, framework-free (BYO, `--harness other`)

An agent with no framework at all — a plain OpenAI tool-calling loop — for the case Relay has no
ready-made integration (CrewAI, AutoGen, a homegrown loop, …). Two tools worth attacking
(`bash_executor`, `python_executor`) that really run what they're given.

```
agent.py         the loop; each tool call goes through nemo_relay.typed.tool_execute by hand
server.py        FastAPI serving loop — starts Relay, opens a scope per request
Dockerfile       your image; base nemo-relay, no integration extra
```

There is no middleware and no ToolNode to lean on: `tool_execute` **is** the interception point,
and the loop calls it for every tool. That is exactly what a `--harness other` victim must prove
it does — the run's tool-path preflight fails if any tool call skips it.

## Running it

```bash
export NMP_BASE_URL=http://localhost:8080

nemo iron-swarm init --project-dir plugins/nemo-iron-swarm/examples/other-victim \
    --name other-victim --harness other --relay-confirmed
nemo iron-swarm synth-benign --manifest-id other-victim --yes
nemo iron-swarm run --manifest-id other-victim
```
