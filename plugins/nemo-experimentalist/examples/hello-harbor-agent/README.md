<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# hello-harbor-agent

The smallest complete Experimentalist setup: a baseline agent, a Harbor
benchmark, and a profile. It exists to be **read and stepped through**, not to
measure anything useful.

Everything is local — no dataset registry, no NeMo Platform, no LLM or network
inside the task container. A full validation evaluation takes about 8 seconds
once the image is cached. Only the Experimentalist's own components (Coder,
Analyzer, Proposer, Terminator) call an LLM.

See [`docs/architecture.md`](../../docs/architecture.md) for what the run
actually does.

## Layout

```text
optimizer.yaml        profile: agent name, source, datasets, task template
AGENT-SPEC.md         what the agent is supposed to do (fed to the LLM components)
agent.py              the code under optimization
main.py               container entry point
tracing.py            hand-rolled OTLP JSONL trace writer (stdlib only)
harbor_wrapper.py     the Harbor adapter — WrappedAgent.setup() / .run()
dataset/train/        greet-world, sum-two
dataset/validation/   greet-universe, sum-three
dataset/task-template/  the shape the Eval Author clones in Mode 1
```

Each task directory is a standard Harbor task:

```text
task.toml         config + `artifacts = [...]` collection declaration
instruction.md    the prompt handed to the agent
environment/      Dockerfile — a bare python:3.12-slim
tests/test.sh     the verifier: writes /logs/verifier/reward.json
tests/expected.txt  the exact line the agent should have produced
```

## The deliberate capability gap

`HelloAgent.solve` dispatches to a list of handlers, and the only handler today
is `handle_greeting`. So:

| Task | Split | Baseline result |
|---|---|---|
| `greet-world` | train | reward 1.0 |
| `sum-two` | train | reward 0.0 — falls through to the fallback string |
| `greet-universe` | validation | reward 1.0 |
| `sum-three` | validation | reward 0.0 |

Baseline validation reward is `{"reward": 0.5, "format_ok": 1.0}`. The missing
arithmetic handler is a real root cause for the Analyzer to find, the Proposer
to describe, and the Coder to fix — which is what the one-round debug config
exercises.

Two metric keys (`reward` and `format_ok`) rather than one is also deliberate:
candidates are then compared in 2-D, so the Pareto ranking does something
visible.

## What a one-round run actually does

Observed with a one-round Experimentalist run against this profile:

1. The Analyzer reads the failing trial's trace and diagnoses it correctly —
   *"the baseline agent lacks a routing or handler capability for two-integer sum
   requests … falls through to fallback"*.
2. The Proposer emits an `add_concrete_method` improvement: add a `handle_sum`
   node ahead of `handle_greeting`.
3. The Coder implements it, and `agent-1` now passes `sum-two`.
4. **Validation still scores 0.5.** With `max_train_batch_tasks: 1` the loop only
   saw the two-operand `sum-two`, so the Coder wrote a deliberately two-integer
   handler — and the held-out `sum-three` ("sum of 8, 13 and 4") is three-operand.
5. `agent-1` ties `agent-0` on validation, so the baseline stays the winner.

That is the held-out split doing its job: a change that fixes the training
failure is caught not generalizing. It is the most useful thing to watch on a
first run, so the example is tuned to produce it.

## Running it

```bash
export INFERENCE_API_KEY=sk-...
bash tmp/run.sh
```

Or from VS Code, the `Experimentalist: hello — eval only` launch configuration.
Check prerequisites first:

```bash
uv run nemo experimentalist doctor --profile plugins/nemo-experimentalist/examples/hello-harbor-agent/optimizer.yaml
```

## Running the evaluation through the NeMo Evaluator SDK

The example ships two ways to run the exact same Harbor evaluation:

| `evaluator_type` | Who owns the orchestration |
|---|---|
| `harbor_native` (default) | The plugin builds Harbor's `JobConfig` and drives `Job` itself. |
| `harbor_evaluator` | The NeMo Evaluator SDK's `HarborAgentTaskRunner` owns the `JobConfig`, the job-directory cache, and the scoped agent import. |

**The SDK runner still uses Harbor underneath.** Same containers, same verifiers,
same `result.json` tree. Only orchestration ownership moves, and results are read
back off the job directory by the same adapter either way — so the two produce
equivalent trials and identical metrics. Nothing here talks to NeMo Platform, so
no service needs to be running and the platform port is irrelevant.

### Prerequisites

- Python 3.12 and a synced workspace: `uv sync --group experimentalist`
- A running Docker daemon (`docker info` must succeed)
- **No model API key** for the commands in this section — the evaluator seam
  makes no LLM calls. A key is only needed for the full optimizer loop below,
  whose Coder, Analyzer, and Proposer do call a model.

### A/B the two evaluators (no model key)

The live A/B is a pytest module. It needs Docker and `harbor`, and is skipped
otherwise. Every command below runs from the **platform root**, not this example
directory:

```bash
uv run pytest plugins/nemo-experimentalist/tests/experimentalist/test_evaluator_harbor_ab_e2e.py -v
```

Both evaluator arms should report the same aggregate (about 10 s each once the
image is cached):

```text
{"format_ok": 1.0, "reward": 0.5}
```

That is the deliberate capability gap from the table above: `greet-universe`
passes, `sum-three` does not, and both emit `format_ok`.

Artifacts land under the test's temporary experiment directory, one directory
per trial:

```text
agent-0-validation/
  result.json                 aggregate job result
  greet-universe__<id>/
    result.json               task_name, verifier rewards, exception info, timings
    trial.log                 Harbor's orchestration log
    verifier/reward.json      what tests/test.sh wrote
    artifacts/traces/*.jsonl  OTLP traces the Analyzer reads
```

### Caching

`harbor_evaluator` treats the job directory as a **success-aware cache**.
Re-running the same evaluation finishes quickly without touching Docker when
every requested task already has `n_attempts` completed, non-errored trials. A
run that errored, was interrupted, or is under-sampled is re-run rather than
served from a partial cache.

The cache only engages because the loop pins a deterministic job name
(`<candidate>-<dataset>`). Setting a custom `job_name` per run defeats it.

### The full optimizer loop

These commands **do** need a model key, because the loop's Coder writes
`architecture.md` and the Terminator writes `OPTIMIZATION.md`:

```bash
export INFERENCE_API_KEY=sk-...
```

```bash
uv run nemo experimentalist run \
  --profile plugins/nemo-experimentalist/examples/hello-harbor-agent/optimizer.yaml \
  --no-insight \
  --experiment-dir tmp/exp-hello
```

Pass a local `--config` YAML when you want to pin `evaluator_type`, round
limits, or other loop knobs. The only difference that matters for the Harbor A/B
is `evaluator_type`; the validation aggregate is `{"reward": 0.5, "format_ok": 1.0}`
either way.

### Configuring the SDK evaluator

Keys under `evaluator:` map 1:1 onto the SDK's `HarborRuntimeConfig`, and unknown
keys are **rejected rather than ignored**:

```yaml
evaluator_type: harbor_evaluator
evaluator:
  n_attempts: 1
  n_concurrent_trials: 4
  max_retries: 0            # NOT `retry:` — the plain evaluator's RetryConfig has no SDK equivalent
  quiet: false
  trace_dir: /app/traces
  agent_timeout_multiplier: 1.0
```

`agent_dir` is not configurable: it is always the candidate being evaluated, so a
config cannot point the run at different code.
