<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# The war-game victim, bring-your-own

The other intake path: no platform registration, no Fabric spec — just the image your own
Dockerfile builds. A hand-built LangGraph `StateGraph` with two tools worth attacking
(`bash_executor`, `python_executor`), served over `/v1/chat/completions`.

```
agent.py         the graph — Relay's wrapper on the ToolNode is THE interception line
server.py        FastAPI serving loop — starts Relay, opens a scope per request
Dockerfile       your image; everything Iron Swarm derives, it derives from here
iron-swarm.yaml  only for running standalone; `init --project-dir` derives this
```

Unlike the Fabric example, the Relay wiring here is the author's job — both obligations are marked
in the source, and the skill's `relay-attachment.md` reference explains each.

## Running it

```bash
export NMP_BASE_URL=http://localhost:8080

nemo iron-swarm init --project-dir plugins/nemo-iron-swarm/examples/langgraph-victim \
    --name langgraph-victim --harness langgraph --relay-confirmed
nemo iron-swarm synth-benign --manifest-id langgraph-victim --yes
nemo iron-swarm run --manifest-id langgraph-victim
```

`--relay-confirmed` is honest here because `agent.py` and `server.py` really do attach Relay; on
your own project, verify before you promise — the preflight will catch a false claim, but only
after a container build.
