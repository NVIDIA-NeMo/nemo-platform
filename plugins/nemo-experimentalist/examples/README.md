<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Experimentalist examples

These examples make Experimentalist behavior reviewable at three levels. They
show the complete agent-to-Harbor adapter contract without presenting sample
agents as production applications.

| Example | Why it exists | What it demonstrates | How to use it |
|---|---|---|---|
| [`hello-harbor-agent`](hello-harbor-agent/README.md) | Small onboarding and debugger fixture. | Fully local agent, train/validation tasks, deterministic traces, two metrics, and a deliberate arithmetic gap for one optimizer round to diagnose. | Start with its README. No model key is needed for the Docker-backed evaluator A/B pytest. |
| [`tau3-nooa-agent`](tau3-nooa-agent/README.md) | Realistic interactive-agent target. | NOOA CodeAct agent, Tau3 airline tasks, MCP runtime sidecar, prepared train/validation datasets, and inference-backed user simulation. | Follow the [getting-started guide](../../../docs/get-started/example-agent.mdx) to prepare datasets, record traces, and run one SDK-backed Experimentalist smoke round. |
| [`terminal-bench-agent`](terminal-bench-agent/README.md) | Canonical benchmark runtime fixture. | Locked LangChain agent installed inside unmodified Terminal-Bench task containers, with no sidecar or task-definition changes. | Use through the [canonical benchmark runner](../benchmarks/README.md), or invoke its module directly as documented in its agent spec. |

The examples expose the same agent-to-Harbor adapter shape:

```text
AGENT-SPEC.md        behavior contract supplied to optimizer components
agent.py / main.py   code under optimization and its entry point
harbor_wrapper.py    upload, install, execute, trace, and artifact bridge
dataset/             optional local tasks
optimizer.yaml       optional profile for self-contained fixtures
```

Recommended order:

1. Use `hello-harbor-agent` to inspect evaluator wiring and one optimizer round.
2. Use `tau3-nooa-agent` to inspect realistic MCP and inference-backed behavior.
3. Use `terminal-bench-agent` for reproducible benchmark runs.
