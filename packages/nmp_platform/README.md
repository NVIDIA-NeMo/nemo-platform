# nmp-platform (legacy task entrypoint)

> **Status: legacy.** This package is kept for backwards compatibility with
> existing task container images and is on track to be dropped. New code
> should not depend on it.

## What this is

A thin shim that exposes a single console script, `nemo-platform`, with one
supported subcommand:

```bash
nemo-platform run task --task <python.module>
```

It executes the named Python module via `runpy` with optional `--env` and
`--config` (the latter is forwarded as the `NEMO_JOB_STEP_CONFIG` environment
variable). Anything else (`run --services …`, `run --config …`,
`run --quickstart`, etc.) is intentionally rejected with a non-zero exit code
that points callers at `nemo services run`.

## Why it still exists

A handful of task container images and seed jobs invoke `nemo-platform run task`
as their entrypoint:

- `nmp-automodel-tasks` — used by the automodel file_io task
  (`services/automodel/src/nmp/automodel/tasks/docker/docker-compose.yaml`
  runs `nmp.automodel.tasks.file_io`).
- `services/platform-seed` — recommended invocation in its README is
  `nemo-platform run task --task nmp.platform_seed`.

The package is wired into container builds via the `nmp-task-runtime`
dependency group in the root `pyproject.toml`.

## What replaced it

All actual platform/service startup has moved to `nemo services run`,
implemented by `packages/nmp_platform_runner/`. See `CONTRIBUTING.md` for the
current local-dev workflow.

## When to delete this package

Once nothing invokes `nemo-platform run task` anymore — i.e. once the task
images and `platform-seed` switch to invoking the target module directly
(`python -m nmp.platform_seed`, etc.) or move to a different launcher — this
whole directory can be removed along with:

- the `nmp-task-runtime` dependency group in the root `pyproject.toml`,
- the `"packages/nmp_platform"` entry in `[tool.uv.workspace] members`,
- the `[tool.hatch.build.targets.wheel] packages = ["packages/nmp_platform/"]`
  line at the bottom of the root `pyproject.toml`.

## Layout

```text
config/         # local-dev platform config (NMP_CONFIG_FILE_PATH default)
src/nmp/platform/main.py
tests/test_main.py
```

The `config/` files (`local.yaml`, `local.env`) are not Python — they are the
default config consumed by `nemo services run` during local development and
referenced from several Makefiles and run scripts in the repo.

`local.env` sets SQLite for the entity store (`~/.local/share/nemo/nmp-platform.db`)
so no PostgreSQL is required. Source it before starting services:

```bash
set -a && source packages/nmp_platform/config/local.env && set +a
uv run nemo services run --host 127.0.0.1 --port 8080
```
