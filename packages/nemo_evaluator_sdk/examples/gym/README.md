# Run a NeMo Gym environment through NeMo Evaluator

`run_gym_eval.py` runs an **existing** NeMo Gym environment (the `mcqa` benchmark by default) through the Evaluator's `GymAgentTaskRunner` and scores it with `AgentEvaluator`. Use it when you already have a Gym environment and want to run and score it through NeMo Evaluator without migrating it. Gym owns execution *and* scoring; the runner shells out to the `gym` CLI and adapts the rollout bundle into trials, and `GymRewardMetric` surfaces Gym's per-attempt reward.

Mapping: one Gym dataset → one run; each distinct row → one `AgentEvalTask` (id = content hash of the row); each attempt (`--num-repeats`) → one `AgentEvalTrial`. So `--num-repeats 2` over a 5-row dataset yields 5 tasks × 2 = 10 trials.

## Prerequisites

A working **NeMo Gym checkout** is required — Gym resolves its environments from the repo, not from a package install. From the Gym checkout:

```bash
# 1. Gym venv + framework (Gym pins uv >= 0.9.30; the workspace floor must satisfy that)
uv venv --python 3.12 .venv
uv pip install --no-config --python .venv/bin/python -e ".[dev]" "ray[default]>=2.55.1"

# 2. The target env's own deps (each resources_server ships a requirements.txt)
uv pip install --no-config --python .venv/bin/python tiktoken        # mcqa needs tiktoken

# 3. Model credentials for the collector — a gitignored env.yaml at the Gym repo root:
cat > env.yaml <<'YAML'
policy_base_url: https://<your-openai-compatible-endpoint>/v1
policy_api_key: <key>
policy_model_name: <model, e.g. nvidia/meta/llama-3.3-70b-instruct>
YAML
```

> `env.yaml` is gitignored by the Gym repo — the credentials stay local.

## Run

From the nemo-platform repo root (any Python with `nemo_evaluator_sdk` importable — the runner shells out to Gym's own venv):

```bash
uv run python -m packages.nemo_evaluator_sdk.examples.gym.run_gym_eval --gym-root /path/to/Gym
```

Useful flags: `--resources-server`, `--agent`, `--model-type` (`inference_provider` for OpenAI-compatible **chat** endpoints; `openai_model` uses the OpenAI **Responses API** and 500s against chat-only endpoints), `--num-repeats`, `--output-dir`.

For the full set of knobs the underlying `gym env start` / `gym eval run` commands accept, see the [NeMo Gym documentation](https://github.com/NVIDIA-NeMo/Gym). Anything `GymRuntimeConfig` does not expose as a field can be passed through with its `env_overrides` escape hatch (Hydra `+key=value` overrides applied to `gym env start`).

Each run writes its bundle to a fresh temporary directory by default. Pass `--output-dir` to choose one, but give every run its own: the runner refuses to reuse a directory that already holds Gym rollout output (Gym appends to its failures sidecar, so reusing one would mix runs) and raises rather than clearing a prior run's results.

Expected output:

```text
discovered 5 tasks from .../resources_servers/mcqa/data/example.jsonl
=== RESULT ===
tasks: 5  trials: 10
aggregate scores:
  gym_reward.reward: mean=0.6

Run bundle (run.json, trials.jsonl, scores.jsonl, report.html): /var/folders/.../gym-eval-ab12cd34
```

## Read the results

`inspect_results.py` is the companion to the above: it reads a bundle and shows how to reach each kind of result — headline aggregates, `pass@k`, per-task outcomes, and the runner's own imported numbers. Its accessors (`aggregate`, `per_task_outcomes`) are written to be lifted into your own code, and everything it shows also works on the in-memory `AgentEvalResult` that `AgentEvaluator().run(...)` returns — reading a bundle just makes it runnable without a live run.

No bundle is checked in; the run above produces one. Give it a stable `--output-dir` and point the reader at the same path:

```bash
uv run python -m packages.nemo_evaluator_sdk.examples.gym.run_gym_eval \
    --gym-root /path/to/Gym --output-dir /tmp/gym-eval
uv run python -m packages.nemo_evaluator_sdk.examples.gym.inspect_results --bundle /tmp/gym-eval
```

Aggregates named `runner.gym.*` are Gym's own figures, imported into `summary.scores` so they are addressable exactly like the SDK's — the prefix is what tells you which side computed them. The script cross-checks Gym's `pass@1` against the SDK's natively-computed one (Gym reports accuracy on a 0-100 scale where the SDK uses 0-1). It works on any agent-eval bundle: pass `--metric-type`/`--output-name` for a run scored with a different metric.

## How it runs Gym

The runner uses Gym's **two-step** flow, which reads a dataset file directly (no split-driven data-prep, no HuggingFace downloads):

1. `gym env start …` — brings up the resources-server + agent + model servers.
2. `gym eval run --no-serve --input <dataset> …` — collects rollouts against them.

It does **not** import `nemo_gym` and does **not** handle secrets — it invokes the `gym` executable in your checkout, and Gym reads credentials from that checkout's `env.yaml`.

The dataset handed to step 2 is not your source file. The runner **materializes** a normalized one into the run's work directory: one row per requested task, with `_ng_task_index` stamped explicitly. Gym honors a caller-supplied `_ng_task_index` (it only assigns one when a row lacks it) and echoes it back on every rollout record, so rollouts join back to tasks through a map the runner owns rather than a guess about Gym's internal row ordering. It also means running a *subset* of tasks only rolls out that subset.

### Logs

Gym's subprocess output is streamed to files in the run's work directory — `gym_env.log` for `gym env start`, and `gym_eval.stdout.log` / `gym_eval.stderr.log` for the collection — and mirrored to the `nemo_evaluator_sdk.agent_eval.runtimes.gym_runtime` logger at `DEBUG`. Startup and collection failures name the relevant files and inline the last lines. To watch Gym's output in your own terminal, turn that logger up:

```python
logging.getLogger("nemo_evaluator_sdk.agent_eval.runtimes.gym_runtime").setLevel(logging.DEBUG)
```

## Notes & caveats

- **One distinct row is one task.** Task identity is the row's content hash, so duplicate rows collapse into a single task and the runner warns. Repeating a row is *not* how you ask for repeated attempts — `num_repeats` is, since attempts are a run-level concern. Duplicates usually mean a data problem.
- **Per-env deps are heterogeneous.** mcqa needs only `tiktoken`; other Gym envs pull `torch`/COMET/GPU or docker. The caller is responsible for a Gym runtime whose deps are installed.
- **`--no-serve --input` bypasses Gym's data-prep** (prompt templating / dataset materialization). This example's `example.jsonl` rows are already complete, so it's faithful; an env whose rows need templating would need that step first.
- Service-side execution (docker/k8s, Ray provisioning) is out of scope for this SDK path — that's the evaluator plugin's job.

## Next steps

- [`../harbor/`](../harbor/) — the same `AgentEvaluator` seam driven by the Harbor runtime.
- [`../fabric_harness_runtimes.py`](../fabric_harness_runtimes.py) — the Fabric runtime equivalent.
- [`gym_runtime.py`](../../src/nemo_evaluator_sdk/agent_eval/runtimes/gym_runtime.py) — `GymRuntimeConfig` field reference plus the attribution and teardown rationale.
- [NeMo Gym documentation](https://github.com/NVIDIA-NeMo/Gym) — authoring environments, agents, and datasets.
