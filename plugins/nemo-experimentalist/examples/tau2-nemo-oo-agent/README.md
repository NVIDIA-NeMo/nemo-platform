<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tau2 NOOA airline agent

This example is the realistic Experimentalist target. It complements the tiny
[`hello-harbor-agent`](../hello-harbor-agent/README.md) fixture with an
interactive airline workflow, external datasets, model calls, and a task
runtime sidecar.

## What it contains

| Path | Role |
|---|---|
| `optimizer.yaml` | Profile for the local agent, remote Tau2 train/validation datasets, task template, and workspace. |
| `AGENT-SPEC.md` | Airline policy supplied to optimizer components. |
| `agent.py` | NOOA CodeAct agent under optimization. |
| `harbor_wrapper.py` | Uploads the candidate, installs dependencies, passes MCP configuration, runs the agent, and collects traces. |
| `dataset/template/task_template/` | Harbor task shape used for authored tasks, including the Tau2 runtime MCP sidecar. It is not the train or validation dataset. |
| `.env.example` | Required inference credential and optional endpoint/model overrides. |

The profile resolves `agent_source: .` by default. Actual train and validation
tasks come from the registry references in `optimizer.yaml`.

## Run

From the platform repository root:

```bash
uv sync --group experimentalist
cp -n plugins/nemo-experimentalist/examples/tau2-nemo-oo-agent/.env.example \
  plugins/nemo-experimentalist/examples/tau2-nemo-oo-agent/.env
```

Replace the placeholder inference key, then verify prerequisites:

```bash
uv run nemo experimentalist doctor \
  --profile plugins/nemo-experimentalist/examples/tau2-nemo-oo-agent/optimizer.yaml
```

Run one reduced-cost round:

```bash
uv run nemo experimentalist run \
  --profile plugins/nemo-experimentalist/examples/tau2-nemo-oo-agent/optimizer.yaml \
  --no-insight \
  --config plugins/nemo-experimentalist/docs/e2e/experiment-fast.yaml \
  --experiment-dir tmp/exp-tau2
```

Requirements: Docker, dataset-registry access, network access from task
containers, and a valid `INFERENCE_API_KEY`. Trials take minutes; use the hello
example first when debugging evaluator or loop control flow.

See the [E2E config guide](../../docs/e2e/README.md) and
[architecture guide](../../docs/architecture.md).
