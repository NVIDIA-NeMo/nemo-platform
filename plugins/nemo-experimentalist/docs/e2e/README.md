<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Experimentalist example configs

These configs provide small, repeatable entry points into different parts of an
Experimentalist run. They are developer fixtures, not production
defaults. Each removes unrelated work so one behavior can be inspected without
running a full optimization run.

## What each config covers

| Config | What it runs | Use it for |
|---|---|---|
| [`experiment-eval-only.yaml`](experiment-eval-only.yaml) | Baseline setup and one validation evaluation through plain Harbor; no optimization round. | Debugging the original evaluator path. |
| [`experiment-eval-only-sdk.yaml`](experiment-eval-only-sdk.yaml) | The same slice through the NeMo Evaluator SDK's `HarborAgentTaskRunner`. | Comparing SDK orchestration with plain Harbor while keeping tasks and expected scores identical. |
| [`experiment-debug-round.yaml`](experiment-debug-round.yaml) | One minimal local round: analyze, propose one candidate, implement, and re-evaluate. Candidate publishing is disabled. | Stepping through the optimizer loop with the bundled hello example. |
| [`experiment-fast.yaml`](experiment-fast.yaml) | One reduced-cost round with one candidate, one survivor, and bounded analysis. Git candidate archival and winner publication are enabled when the agent source is a Git URL. | Fast integration testing with a realistic agent or remote dataset. |

[`run-eval-only.py`](run-eval-only.py) bypasses optimizer components and runs the
bundled hello validation split directly through either evaluator. It needs
Docker but no model key. Use it for the fastest A/B check:

```bash
uv run plugins/nemo-experimentalist/docs/e2e/run-eval-only.py \
  --evaluator-type harbor \
  --experiment-dir tmp/eval-only-plain

uv run plugins/nemo-experimentalist/docs/e2e/run-eval-only.py \
  --evaluator-type harbor_agent_task_runner \
  --experiment-dir tmp/eval-only-sdk
```

Both runs should report:

```text
{"format_ok": 1.0, "reward": 0.5}
```

Use separate experiment directories for the two evaluator arms. Pass
`--force-rerun` after changing agent or dataset inputs.

## How to run the configs

Run commands from the platform repository root:

```bash
uv sync --group experimentalist
uv run nemo experimentalist doctor \
  --profile plugins/nemo-experimentalist/examples/hello-harbor-agent/optimizer.yaml
```

Docker must be running. CLI-driven configs also require the model credential
used by Experimentalist's LLM components.

Smallest CLI path:

```bash
uv run nemo experimentalist run \
  --profile plugins/nemo-experimentalist/examples/hello-harbor-agent/optimizer.yaml \
  --no-insight \
  --config plugins/nemo-experimentalist/docs/e2e/experiment-eval-only-sdk.yaml \
  --experiment-dir tmp/exp-hello-eval-sdk
```

One complete debug round:

```bash
uv run nemo experimentalist run \
  --profile plugins/nemo-experimentalist/examples/hello-harbor-agent/optimizer.yaml \
  --no-insight \
  --config plugins/nemo-experimentalist/docs/e2e/experiment-debug-round.yaml \
  --experiment-dir tmp/exp-hello-round
```

Realistic Tau2 round:

```bash
uv run nemo experimentalist run \
  --profile plugins/nemo-experimentalist/examples/tau2-nemo-oo-agent/optimizer.yaml \
  --no-insight \
  --config plugins/nemo-experimentalist/docs/e2e/experiment-fast.yaml \
  --experiment-dir tmp/exp-tau2
```

Start with the hello paths. Tau2 needs dataset-registry access, an inference key
inside task containers, and longer-running trials.

See the [example overview](../../examples/README.md) and
[architecture guide](../architecture.md) for component boundaries and output
layout.
