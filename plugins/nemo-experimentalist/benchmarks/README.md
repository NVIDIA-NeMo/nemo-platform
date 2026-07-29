# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Canonical Experimentalist benchmarks

These benchmarks measure M2 Experimentalist optimization on unmodified Harbor Hub
packages. They do not cover M1 Insight → Eval Author behavior.

Five suites ship today. All store only task IDs and download task definitions into
a local cache; no task content is vendored here.

| Suite | Package | Tasks | Agent under test |
| --- | --- | --- | --- |
| `suites/terminal-bench-2.1.yaml` (default) | `terminal-bench/terminal-bench-2-1@6` | 89 | `examples/terminal-bench-agent` |
| `suites/tau3-banking.yaml` | `sierra-research/tau3-bench@1`, banking scoped | 97 | `examples/tau3-nooa-agent` |
| `suites/tau3-airline.yaml` | `sierra-research/tau3-bench@1`, airline scoped | 50 | `examples/tau3-nooa-agent` |
| `suites/tau3-retail.yaml` | `sierra-research/tau3-bench@1`, retail scoped | 114 | `examples/tau3-nooa-agent` |
| `suites/tau3-telecom.yaml` | `sierra-research/tau3-bench@1`, telecom scoped | 114 | `examples/tau3-nooa-agent` |

The four tau3 suites share one agent: its `AGENT-SPEC.md` is domain-generic because
the domain policy arrives at runtime in the task instruction.

## Terminal-Bench provenance

The suite uses `terminal-bench/terminal-bench-2-1@6` from Harbor Hub:

- 89 canonical tasks
- dataset content hash
  `sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a`
- Harbor Hub record:
  <https://hub.harborframework.com/datasets/terminal-bench/terminal-bench-2-1/6>

The 38/25/26 quality partition and 35/12/12 fast partition came from Gaia's
`optimization-datasets` commit
`1b7688ad257dacd1a3267dddb88db6cefdc31376`. The manifest corrects
`install-windows-3-11` to the canonical ID `install-windows-3.11`. At startup,
the runner asks Harbor Hub for revision 6, verifies its content hash, and
asserts that the quality partition covers all 89 canonical IDs exactly once.

## tau3 provenance

Each tau3 suite scopes one domain of `sierra-research/tau3-bench@1` by task-ID prefix.
All four share the package's 375 tasks, its content hash
`sha256:a57304f682894ac061090769af771a3617664f3ff6e5417d4eadf8e30433e4d9`, and its
Harbor Hub record
<https://hub.harborframework.com/datasets/sierra-research/tau3-bench/1>:

| Suite | Task-ID prefix | Tasks | Quality split |
| --- | --- | --- | --- |
| `tau3-banking.yaml` | `tau3-bench__tau3-banking_knowledge-` | 97 | 41/28/28 |
| `tau3-airline.yaml` | `tau3-bench__tau3-airline-` | 50 | 20/10/20 |
| `tau3-retail.yaml` | `tau3-bench__tau3-retail-` | 114 | 50/24/40 |
| `tau3-telecom.yaml` | `tau3-bench__tau3-telecom-` | 114 | 50/24/40 |

Banking's partition came from `optimization-datasets` `feat/tau2-other-domains`
commit `025ecd2ef2b518ad81f6b22d3f3937af8906fb01`, whose
`tau2-banking-knowledge-NNN` names map onto the canonical
`tau3-bench__tau3-banking_knowledge-task-NNN` IDs. The other three take `test`
from the domain's upstream `split_tasks.json` test list and carve `validation` out
of its train list, every third entry in upstream order; that file's train and test
lists partition the domain exactly, so the quality split needs nothing invented
beyond the validation stride.

A canonical ID is `tau3-bench__` plus the name Harbor's `adapters/tau3-bench` gives
the task, `tau3-<domain>-<slugified upstream task ID>`. Re-deriving IDs from that
adapter against a `tau2-bench` checkout reproduces the banking manifest exactly,
which is how the other three manifests were built.

Every fast partition is 6/3/3. Banking picks its tasks from a filtered subset; the
other three sample each quality split at a fixed stride, so a smoke run spans the
split instead of clustering at its start — telecom's task IDs sort by issue type, and
the first twelve are all `mms_issue`.

A domain's `reward_basis` decides whether scoring needs an LLM judge. Banking's fast
partition draws only from its 87 pure-database-state tasks. Airline scores on
database state and a substring check of the agent's messages, and telecom on
environment assertions and expected actions, so both are judge-free in either
partition. 112 of retail's 114 tasks carry an `NL_ASSERTION`, so retail always
scores through the judge.

Each task also runs a `tau3-runtime` sidecar hosting the tau2 environment and user
simulator. Tau-style suites set `models.user_simulator`, which makes the runner
export `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `TAU2_USER_MODEL`, and
`TAU2_NL_ASSERTIONS_MODEL` for the sidecar and the verifier.

## Held-out evaluation

The runner:

1. evaluates the unchanged baseline agent on the test split;
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
to both the AUT and optimizer, using
`https://inference-api.nvidia.com/v1` unless an API base is explicitly set.

Validate provenance and task IDs without Docker or model calls:

```bash
uv run python benchmarks/run.py --validate-only
```

Run the bounded fast benchmark:

```bash
uv run python benchmarks/run.py \
  --config benchmarks/configs/terminal-bench-smoke.yaml
```

Run the reproducible quality benchmark:

```bash
uv run python benchmarks/run.py \
  --config benchmarks/configs/terminal-bench-quality.yaml
```

A non-default suite needs its own suite, config, and agent:

```bash
uv run python benchmarks/run.py \
  --suite benchmarks/suites/tau3-banking.yaml \
  --config benchmarks/configs/tau3-smoke.yaml \
  --agent examples/tau3-nooa-agent
```

The other tau3 domains change only `--suite`; the two tau3 configs and the agent are
domain-independent.

Both setup and agent execution require network access. Each AUT installs its own
dependencies from its committed `uv.lock` inside the task container and does not
need a Docker socket.

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
