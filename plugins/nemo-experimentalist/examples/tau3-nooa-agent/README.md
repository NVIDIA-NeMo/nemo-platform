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

The agent raises nooa's `tool_call_timeout` to 300 seconds, overridable with
`TAU3_MCP_TOOL_TIMEOUT_SECONDS`, because the sidecar runs a user-simulator LLM inside
`start_conversation` and `send_message_to_user`. The default of 60 seconds would be
enough today, but leaves no room for a slower model.

Run this agent through the benchmark harness rather than invoking it directly:

```bash
uv run python benchmarks/run.py \
  --suite benchmarks/suites/tau3-banking.yaml \
  --config benchmarks/configs/tau3-smoke.yaml \
  --agent examples/tau3-nooa-agent
```
