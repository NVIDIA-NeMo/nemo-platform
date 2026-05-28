# nemo-platform-plugin

`nemo-platform-plugin` is the only package NeMo Platform plugin authors install. It re-exports all base classes, schemas, and utilities needed to build fully-featured NeMo Platform plugins.

## Surfaces

| Surface | Base class | Entry-point group | Purpose |
|---|---|---|---|
| HTTP service | `NemoService` | `nemo.services` | Contributes FastAPI routers mounted at `/apis/<name>/...` |
| CLI | `NemoCLI` | `nemo.cli` | Contributes `nemo <name> <cmd>` subcommands |
| Job | `NemoJob` | `nemo.jobs` | Contributes schedulable, container-executable jobs. Auto-generates `run` / `submit` / `explain` CLI verbs. |
| Controller | `NemoController` | `nemo.controllers` | Contributes background reconcile-loop controllers |
| Configuration | `NemoConfig` | (none)¹ | Typed plugin configuration with env var / YAML loading |
| Entity | `NemoEntity` | (none)¹ | Entity definitions stored in the NeMo Platform entity store |

¹ Not discovered via entry-points — used directly by plugin code.

## Installation

```bash
uv add nemo-platform-plugin nemo-platform
```

`nemo-platform` is required for entity client injection at runtime.

## How plugins are discovered

Declare surfaces in `pyproject.toml` entry-point groups. Install the package and the platform picks them up at startup — no registration code needed. See [QUICKSTART.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/QUICKSTART.md) for the full template.

## The `name` rule

Every surface class requires a non-empty `name: ClassVar[str]`. Checked at class-definition time — missing raises `TypeError`. Must exactly match the entry-point key; mismatch logs a warning at startup.

## Next steps

- [QUICKSTART.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/QUICKSTART.md) — build your first plugin end-to-end
- [SERVICE.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/SERVICE.md) — HTTP routes, CRUD patterns, testing
- [JOB.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/JOB.md) — jobs, CLI commands, auto-generated job commands
- [CONTROLLER.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/CONTROLLER.md) — reconcile loops, state machines, service principal
- [CONFIG.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/CONFIG.md) — typed configuration, env vars, YAML, test overrides
- [ENTITY.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/ENTITY.md) — entity store, CRUD client, pagination, optimistic locking
- [INFERENCE_MIDDLEWARE.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/INFERENCE_MIDDLEWARE.md) — inference request/response middleware, typed bodies, and response annotations
- [ARCHITECTURE.md](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/packages/nemo_platform_plugin/src/nemo_platform_plugin/docs/ARCHITECTURE.md) — discovery, startup, all surfaces, SDK surface

> **Tip:** These guides also ship inside the installed package at `nemo_platform_plugin/docs/`.
