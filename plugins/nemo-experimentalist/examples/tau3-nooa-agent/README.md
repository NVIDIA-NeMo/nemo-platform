<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# tau3 NOOA agent

Agent under test for the tau3-bench suites. Uses [NOOA](https://github.com/NVIDIA-NeMo/labs-OO-Agents)
with a CodeAct strategy and reaches domain tools over MCP from the task's
`tau3-runtime` sidecar.

`AGENT-SPEC.md` is deliberately domain-generic — the domain policy arrives at runtime
in the task instruction. It is also what the Experimentalist mutates during
optimization.

A task's `[environment].env` only interpolates its docker-compose file, and upstream
wires those variables into the `tau3-runtime` sidecar rather than into the container
the agent runs in. `harbor_wrapper` therefore passes `OPENAI_API_KEY` and
`OPENAI_BASE_URL` through at exec time; `INFERENCE_API_KEY` / `INFERENCE_API_BASE` are
honored as a fallback when running `main.py` outside the wrapper.

`mcp_timeout.py` exists because nooa 0.0.6 gives its MCP transport no HTTP timeout, so
httpx's 5 second default silently strands any tool call that takes longer — which the
sidecar's user-simulator calls always do. See that module for the details and for when
it can be deleted. `TAU3_MCP_TOOL_TIMEOUT_SECONDS` overrides the 300 second default.

Run this agent through the benchmark harness rather than invoking it directly:

```bash
uv run python benchmarks/run.py \
  --suite benchmarks/suites/tau3-banking.yaml \
  --config benchmarks/configs/tau3-smoke.yaml \
  --agent examples/tau3-nooa-agent
```
