# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Canonical Experimentalist benchmark

This benchmark measures M2 Experimentalist optimization on Harbor's unmodified
Terminal-Bench 2.1 package. It does not cover M1 Insight → Eval Author behavior
or Tau2's interactive domains.

## Provenance

The suite uses `terminal-bench/terminal-bench-2-1@6` from Harbor Hub:

- 89 canonical tasks
- dataset content hash
  `sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a`
- Harbor Hub record:
  <https://hub.harborframework.com/datasets/terminal-bench/terminal-bench-2-1/6>

The repository stores only task IDs. Task definitions are downloaded into a
local cache and are never vendored here.

The 38/25/26 quality partition and 35/12/12 fast partition came from Gaia's
`optimization-datasets` commit
`1b7688ad257dacd1a3267dddb88db6cefdc31376`. The manifest corrects
`install-windows-3-11` to the canonical ID `install-windows-3.11`. At startup,
the runner asks Harbor Hub for revision 6, verifies its content hash, and
asserts that the quality partition covers all 89 canonical IDs exactly once.

## Held-out evaluation

The runner:

1. evaluates the unchanged LangChain baseline on the test split;
2. gives only train and validation IDs to `run_experimentalist`;
3. resolves the validation-selected winner from the Experimentalist run;
4. evaluates that winner on the same test IDs and number of attempts.

Test tasks are not supplied to the optimizer. Failed and missing trials count as
zero reward in the benchmark summary. Harness errors are reported separately.

`optimizer.evaluator.n_attempts` controls candidate evaluation attempts during
optimization. Top-level `test_attempts` controls final baseline and winner
attempts. These settings intentionally remain separate.

## Run

Required credentials:

```bash
export INFERENCE_API_KEY=...
```

`EXPERIMENTALIST_API_KEY` may be provided instead. The runner maps either credential
to both the LangChain AUT and optimizer, using
`https://inference-api.nvidia.com/v1` unless an API base is explicitly set.

Validate provenance and task IDs without Docker or model calls:

```bash
uv run python benchmarks/experimentalist/run.py --validate-only
```

Run the bounded fast benchmark:

```bash
uv run python benchmarks/experimentalist/run.py \
  --config benchmarks/experimentalist/configs/smoke.yaml
```

Run the reproducible quality benchmark:

```bash
uv run python benchmarks/experimentalist/run.py \
  --config benchmarks/experimentalist/configs/quality.yaml
```

Both setup and agent execution require network access. The AUT installs a
checksum-pinned static `uv`, uv-managed Python 3.12, and dependencies from its
committed `uv.lock` directly in each canonical task container. It does not need
the image's system Python, package manager, a sidecar, or a Docker socket.

Pass the same `--output` directory to resume interrupted Harbor jobs. Use a new
output directory for an intentionally fresh run.

## Artifacts

By default, each run writes under
`artifacts/experimentalist-benchmarks/<UTC timestamp>/`:

- `summary.json`: dataset and partition revisions, agent digest, model names,
  complete config, task counts, expected/observed trials, rewards, harness
  errors, tokens, reported cost, and elapsed time;
- `heldout-results/heldout-baseline/`: baseline Harbor results;
- `heldout-results/heldout-winner/`: winner Harbor results;
- `optimizer/eval-and-optimize/`: Experimentalist candidates, analyses, and
  train/validation Harbor results.

Harbor result files remain the source of truth. `summary.json` aggregates over
the full expected test trial count. `cost_usd` is `null` when the selected model
endpoint does not report monetary cost.
