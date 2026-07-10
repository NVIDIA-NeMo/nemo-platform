# harbor — run a Harbor job through the agent-eval SDK

Two examples over a Harbor **local dataset directory**,
[`hello_world_dataset/`](hello_world_dataset), which holds Harbor's `hello-world`
task. Both score with Harbor's deterministic **oracle** agent, so they need no
model or API key — only `harbor` installed and a working Docker daemon.

## The dataset directory (how Harbor tasks are found)

A Harbor local dataset is just a directory whose immediate subdirectories are
task folders:

```
hello_world_dataset/
  hello-world/          # [task] name = "harbor/hello-world"
    task.toml
    instruction.md
    environment/Dockerfile
    tests/test.sh
    solution/solve.sh
```

Pointing `DatasetConfig(path=hello_world_dataset)` at this directory is exactly
how user Harbor task collections are discovered: Harbor scans the subdirs, treats
each folder with a `task.toml` as a task, and runs them all. Drop another task
folder in here and both Harbor and this example pick it up with no code changes —
`discover_tasks()` mirrors the same scan to produce one scoring task per folder
(reading the AgentEvalTask id from each `[task] name`).

They exercise the SDK's dependency-light Harbor runtime,
[`harbor_runtime.py`](../../src/nemo_evaluator_sdk/agent_eval/runtimes/harbor_runtime.py),
whose design is the point of these examples:

- The SDK never imports `harbor`. Job *execution* is injected as a `run_job`
  callback (the caller owns the `JobConfig` build and Docker), while
  `HarborAgentTaskRunner` only *reads* Harbor's on-disk
  `<job>/<trial>/result.json` files and adapts them into `AgentEvalTrial`s.
- `HarborRewardMetric` scores the verifier reward stamped on each trial.
- `reward_payload_from_result` collapses a scored `AgentEvalResult` back into the
  legacy `{reward, reward_details, exceptions}` shape older NeMo Optimizer
  consumers expect.

## Run it

From the repository root:

```bash
# Native path: build a Harbor JobConfig, run it, score through AgentEvaluator.
python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode native

# Optimizer path: run, then rebuild NeMo Optimizer's legacy reward payload.
python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode optimizer
```

Both modes call the same `build_hello_world_job_runner` helper. The only
difference is what they do with the result: `native` prints the SDK summary,
`optimizer` prints the `{reward, reward_details, exceptions}` payload.

## How NeMo Optimizer uses this

`NeMo-Optimizer`'s `HarborEvaluator` builds a `JobConfig` with a custom agent
(`AgentConfig(import_path="harbor_wrapper:WrappedAgent")`), runs the job, and
adapts the results. The `optimizer` mode mirrors that flow with the oracle agent
so it stays runnable offline; pass `agent_import_path=...` to
`build_hello_world_job_runner` to swap in a real wrapped agent instead.

## End-to-end test

[`tests/agent_eval/test_harbor_runtime_e2e.py`](../../tests/agent_eval/test_harbor_runtime_e2e.py)
imports `build_hello_world_job_runner`, runs the hello-world job natively, and
asserts the SDK scores it as `reward == 1.0`. It is marked `e2e`/`slow` and skips
automatically when `harbor` or Docker is unavailable:

```bash
uv run --frozen pytest packages/nemo_evaluator_sdk/tests/agent_eval/test_harbor_runtime_e2e.py -v
```

Harbor bind-mounts the container's `/logs` back to the job directory to collect
the verifier reward. Some macOS Docker backends (e.g. colima) only reflect
bind-mount writes for paths they share — often `$HOME` but not `/tmp`. If the
run reports `RewardFileNotFoundError`, point the job/temp directory at a shared
path, e.g. `pytest --basetemp="$HOME/.cache/harbor-e2e-tmp" ...` or
`--jobs-dir "$HOME/.cache/harbor-example"` for the scripts. Linux Docker shares
all paths, so this is only a local-macOS caveat.

The no-Docker unit coverage of the adapter itself lives in
[`test_harbor_runtime.py`](../../tests/agent_eval/test_harbor_runtime.py).

## Files

- `run_harbor_example.py` — both examples plus the shared `build_hello_world_job_runner` helper and `discover_tasks()`.
- `hello_world_dataset/` — a Harbor local dataset directory; each subfolder is a task (`hello-world/` holds `task.toml`, `instruction.md`, `environment/`, `tests/`, `solution/`).
