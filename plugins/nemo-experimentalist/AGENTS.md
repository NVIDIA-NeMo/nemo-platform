<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

## Conventions

Inherited from the NeMo Platform monorepo that now hosts this plugin:

- Use `uv` exclusively (`uv add`, `uv sync`, `uv run`). No pip/poetry/conda.
- No `__init__.py` files — use implicit namespace packages.
- Concrete type hints, not string-based. Don't hide imports under `TYPE_CHECKING`.
- Lint/format with `uv run ruff check` and `uv run ruff format`.
- All files need the SPDX header (`Copyright (c) ... NVIDIA CORPORATION & AFFILIATES`, `Apache-2.0`).

## Active migrations

### 2026-07-24: Optimizer renamed to Experimentalist

Ahead of the move into the `nemo-platform` monorepo, the plugin was renamed from
Optimizer to Experimentalist. Like the Eval Author rename below, this is a
breaking rename with no compatibility aliases:

- distribution `nemo-optimizer-plugin` → `nemo-experimentalist-plugin`, source
  path `src/nemo_optimizer_plugin` → `src/nemo_experimentalist_plugin`
- `OptimizerCLI` → `ExperimentalistCLI`, and both the `nemo.cli` and
  `nemo.skills` entry-point keys are now `experimentalist`, so the command is
  `nemo experimentalist ...`
- the `experiment` verb is now `run`: `nemo experimentalist run`
- `OPTIMIZER_API_BASE`, `OPTIMIZER_API_KEY`, `OPTIMIZER_{SMART,MID,FAST}_MODEL_NAME`,
  `OPTIMIZER_MODEL`, `NEMO_OPTIMIZER_E2E`, and `NEMO_OPTIMIZER_RUNTIME_CACHE` are
  now `EXPERIMENTALIST_*` / `NEMO_EXPERIMENTALIST_*`
- the dataset cache moved from `~/.cache/nemo-optimizer/` to
  `~/.cache/nemo-experimentalist/`, so cached datasets re-download once

Two names deliberately did **not** change. `optimizer.yaml` and the
`.nemo-optimizer/` state directory are a shared contract with
`nemo-insights-plugin`: `PROFILE_FILENAME` and `discover_profile()` live in
`nemo_insights_plugin.contracts.profile`, and `nemo insights analyze` writes
`<profile-dir>/.nemo-optimizer/insights.yaml`, which this plugin reads as the
default insight. Rename them only in lockstep with a Platform change to that
contract. `EvolutionaryOptimizer` and `EvolutionaryOptimizerConfig` also keep
their names — they describe the optimization algorithm, not the product.

The command group is top-level (`nemo experimentalist`) rather than the
eventual `nemo agents experimentalist`. The platform's `nemo.cli` entry-point
group is flat — only `nemo.jobs` and `nemo.functions` are dot-scoped — so
nesting under `nemo agents` needs a Platform-side change first.

### 2026-07-21: Curator renamed to Eval Author

The Curator agent was renamed directly to Eval Author in ASE-643. This is a
breaking rename with no compatibility aliases or migration layer:

- `nemo_experimentalist_plugin.curator` → `nemo_experimentalist_plugin.eval_author`
- `Curator`, `CuratorConfig`, and `CuratorResult` → `EvalAuthor`,
  `EvalAuthorConfig`, and `EvalAuthorResult`
- `run_curator(...)` and `build_curator_agent(...)` →
  `run_eval_author(...)` and `build_eval_author_agent(...)`
- the `curator` optimizer configuration block → `eval_author`
- Curator-specific artifact paths, cache keys, helpers, tests, and documentation
  now use `eval_author` / Eval Author terminology

Agents working on in-flight branches that touch these surfaces should rebase
before resolving conflicts, keep the Eval Author names, and update their code
instead of restoring Curator imports, configuration, or aliases. The obsolete
`curator` configuration key is intentionally rejected with a validation error.

## Development environment

- The root `.venv` is the only Experimentalist environment; use the README for the
  standard `uv` lint, test, and run commands.
- NeMo Experimentalist consumes Insights produced by the Platform Insights plugin.
  Configure Platform services, trace storage, and Insights analysis according
  to the Platform documentation; this repository does not own a service,
  scheduler, or testbed setup.
- `nooa` is pinned to a tagged public GitHub release in `pyproject.toml`.
  Update the tag and lock file together. Keep the Platform-supplied Insights
  plugin separate.
- This branch uses merged Platform PR 718 contracts only. After the Platform
  handoff lands, rebase and repin before adopting any new Platform testbed or
  installer interfaces.
