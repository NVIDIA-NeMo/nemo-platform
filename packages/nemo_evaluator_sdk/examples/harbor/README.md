# harbor — run a Harbor job through the agent-eval SDK

Run a Harbor **local dataset directory**,
[`hello_world_dataset/`](hello_world_dataset), natively through the SDK. The
example scores with Harbor's deterministic **oracle** agent, so it needs no model
or API key — only the `harbor` extra installed and a working Docker daemon.

## Minimal plumbing

The SDK owns the Harbor plumbing. Apart from imports, running a whole dataset is
two lines — build a config, make one call:

```python
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import (
    HarborRuntimeConfig, run_harbor_eval,
)

config = HarborRuntimeConfig(jobs_dir=jobs_dir, agent_name="oracle")
result = await run_harbor_eval(config, "hello_world_dataset")  # loads tasks, runs, scores
```

`run_harbor_eval` discovers the tasks, builds and runs Harbor's `JobConfig`, and
scores each task with `HarborRewardMetric` — the caller never imports `harbor` or
assembles a job. `harbor` is imported lazily inside the runtime, so importing the
SDK never requires it.

## Install

Harbor is imported lazily and is **not** in the SDK's locked dependencies (it
requires Python ≥ 3.12 while the workspace supports ≥ 3.11, like `nemo_fabric`).
Install it separately into the environment that runs the example:

```bash
uv pip install "harbor>=0.16.1"
```

## The dataset directory (how Harbor tasks are found)

A Harbor local dataset is a directory whose immediate subdirectories are task
folders:

```
hello_world_dataset/
  hello-world/          # [task] name = "harbor/hello-world"
    task.toml
    instruction.md
    environment/Dockerfile
    tests/test.sh
    solution/solve.sh
```

Pointing the runtime at this directory is exactly how user Harbor task
collections are discovered: Harbor scans the subdirs, treats each folder with a
`task.toml` as a task, and runs them all. Drop another task folder in here and it
is picked up with no code changes — the SDK's `discover_harbor_tasks()` mirrors
the same scan to produce one scoring task per folder (reading the task id from
each `[task] name`).

## Under the hood

The runtime is [`harbor_runtime.py`](../../src/nemo_evaluator_sdk/agent_eval/runtimes/harbor_runtime.py):

- `HarborRuntimeConfig` — declarative config (agent, attempts, concurrency,
  timeouts, artifacts) mapped onto Harbor's `JobConfig` lazily.
- `HarborAgentTaskRunner` — runs the job (native mode) or adapts an existing job
  dir (offline mode), then reads Harbor's on-disk `result.json` files into
  `AgentEvalTrial`s.
- `HarborTasksetLoader` / `discover_harbor_tasks` — turn a dataset dir into tasks.
- `HarborRewardMetric` — scores the verifier reward stamped on each trial.
- `reward_payload_from_result` — collapses a scored `AgentEvalResult` back into
  the legacy `{reward, reward_details, exceptions}` shape older NeMo Optimizer
  consumers expect.

### Re-running and caching

In native mode the `job_dir` doubles as a cache: if every requested task already
has `n_attempts` completed (non-errored) results there, the Harbor run is skipped
and the results are re-adapted instead. This only engages when you **pin a stable
`job_name`** on the config — the default `job_name` is a timestamp, so each run
writes a fresh dir and never hits the cache. Set `force_rerun=True` to delete the
job dir and re-run unconditionally.

```python
config = HarborRuntimeConfig(jobs_dir=jobs_dir, job_name="hello-world", agent_name="oracle")
await run_harbor_eval(config, "hello_world_dataset")  # first call runs Harbor
await run_harbor_eval(config, "hello_world_dataset")  # second call re-adapts the cached job dir
```

## Run it

From the repository root:

```bash
# Native path: run and print the SDK summary.
python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode native

# Optimizer path: run, then rebuild NeMo Optimizer's legacy reward payload.
python -m packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example --mode optimizer
```

Both modes call `run_harbor_eval`; the only difference is what they print.

## Custom (wrapped) agents

To run a real agent instead of the oracle, set `agent_import_path`. Two packaging
shapes are supported, and the SDK imposes neither:

```python
# Loose wrapper file: point agent_dir at the directory that holds harbor_wrapper.py.
config = HarborRuntimeConfig(
    jobs_dir=jobs_dir,
    agent_dir="path/to/agent",            # directory containing harbor_wrapper.py
    agent_import_path="harbor_wrapper:WrappedAgent",
)

# Already-importable module (installed package): omit agent_dir entirely.
config = HarborRuntimeConfig(
    jobs_dir=jobs_dir,
    agent_import_path="mypkg.agent:WrappedAgent",
)

result = await run_harbor_eval(config, "hello_world_dataset")
```

When `agent_dir` is set, the SDK makes the wrapper importable by injecting that
directory into `sys.modules` under a unique synthetic package for the duration of
the run and removing it afterwards — so the caller never mutates global import
state (the mutation is lock-guarded, and each run gets its own package name so
concurrent runs don't collide). This is `scoped_harbor_agent_import`. When
`agent_dir` is omitted, the import path is handed to Harbor's own importer
unchanged (Harbor resolves it with a plain `importlib.import_module`).

Only `agent_dir` itself is made importable (not `sys.path`), so a loose wrapper
must be **self-contained**: a single module, or one that reaches sibling files
via relative imports (`from .helper import ...`). A wrapper that does an absolute
`import helper` of a sibling won't resolve — package and install it, then use the
`agent_dir`-less form above.

## End-to-end test

[`tests/agent_eval/test_harbor_runtime_e2e.py`](../../tests/agent_eval/test_harbor_runtime_e2e.py)
calls `run_harbor_eval` over the hello-world dataset and asserts the SDK scores it
as `reward == 1.0`. It is marked `e2e`/`slow` and skips automatically when
`harbor` or Docker is unavailable:

```bash
uv run --frozen pytest packages/nemo_evaluator_sdk/tests/agent_eval/test_harbor_runtime_e2e.py -v
```

Harbor bind-mounts the container's `/logs` back to the job directory to collect
the verifier reward. Some macOS Docker backends (e.g. colima) only reflect
bind-mount writes for paths they share — often `$HOME` but not `/tmp`. If the
run reports `RewardFileNotFoundError`, point the job/temp directory at a shared
path, e.g. `pytest --basetemp="$HOME/.cache/harbor-e2e-tmp" ...` or
`--jobs-dir "$HOME/.cache/harbor-example"` for the script. Linux Docker shares
all paths, so this is only a local-macOS caveat.

The no-Docker unit coverage of the adapter and task discovery lives in
[`test_harbor_runtime.py`](../../tests/agent_eval/test_harbor_runtime.py).

## Files

- `run_harbor_example.py` — the two-line native/optimizer example.
- `hello_world_dataset/` — a Harbor local dataset directory; each subfolder is a task.
