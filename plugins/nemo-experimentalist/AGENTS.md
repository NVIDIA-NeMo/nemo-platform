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

### 2026-07-31: Command group nested under `nemo agents`

The only path is `nemo agents experimentalist <verb>`. `ExperimentalistCLI` is
registered under the `nemo.cli.agents` entry-point group, which the `nemo-agents`
plugin's `AgentsCLI` discovers and mounts. There is no top-level
`nemo experimentalist` alias.

Analyst and Eval Author follow the same rule: `nemo agents analyst run` (was
`nemo insights analyze`) and `nemo agents eval-author <verb>`. Prefer
`ctx.command_path` over a hardcoded path when a message quotes the command back
to the user.

### 2026-07-28: Eval Author extracted to its own plugin, heading for standalone

`plugins/nemo-eval-author/` (`nemo-eval-author-plugin`) owns the Eval Author agent package
(`eval_author/`) plus its own `AUTHOR_*` `model_config`.

**The target is one arrow: Experimentalist → Eval Author.** Eval Author is meant to stop
depending on Experimentalist entirely, even where that means duplicating code. Today the
arrow points both ways:

- Experimentalist → Eval Author is permanent. Insight mode imports `EvalAuthor` in
  `components/loop.py` and `EvalAuthorConfig` in `resolve.py`, both at module scope, so
  the dependency is declared in `pyproject.toml`.
- Eval Author → Experimentalist is temporary. It still borrows the evaluator/Harbor
  abstractions, dataset staging, trace analyzer/explorer, `GuardedShellTools`, the cache,
  and the backend factory.

`plugins/nemo-eval-author/tests/test_plugin_boundary.py` pins that second list so it can
only shrink. **When you are tempted to share a helper between the two plugins, duplicate it
into Eval Author instead.** Sharing reads like a cleanup and is a regression here; the
boundary test will reject it, which is the intended answer, not an obstacle to route
around. `uv` resolves the current cycle fine — install both with
`uv sync --group experimentalist`.

Two transitional mechanisms exist only because of the second arrow. Both should be deleted
with the last `nemo_experimentalist_plugin` import, and both are tagged
`TODO(eval-author-standalone)` — `rg 'eval-author-standalone'` lists every site:

- `EvalAuthor.__init__` calls `bridge_author_env_to_experimentalist()`, copying `AUTHOR_*`
  into unset `NEMO_EXPERIMENTALIST_*` slots so the Experimentalist agents Eval Author borrows
  resolve their models. This was a `_env_bridge.py` side-effect import until agents stopped
  binding their LLM in the class body; an ordinary call in `__init__` now suffices because
  those agents resolve when constructed, not when imported.
- `AUTHOR_*` falls back to `NEMO_EXPERIMENTALIST_*` in `model_config`. `AUTHOR_*` is the real
  contract; the fallback only keeps one credential set working in insight mode.

### 2026-07-24: Optimizer renamed to Experimentalist

Ahead of the move into the `nemo-platform` monorepo, the plugin was renamed from
Optimizer to Experimentalist. Like the Eval Author rename below, this is a
breaking rename with no compatibility aliases:

- distribution `nemo-optimizer-plugin` → `nemo-experimentalist-plugin`, source
  path `src/nemo_optimizer_plugin` → `src/nemo_experimentalist_plugin`
- `OptimizerCLI` → `ExperimentalistCLI`, and the `nemo.cli.agents` and
  `nemo.skills` entry-point keys are now `experimentalist`, so the command is
  `nemo agents experimentalist ...` (historically also briefly exposed as a
  top-level `nemo experimentalist` alias; that alias is gone)
- the `experiment` verb is now `run`: `nemo agents experimentalist run`
- `OPTIMIZER_API_BASE`, `OPTIMIZER_API_KEY`, `OPTIMIZER_{SMART,MID,FAST}_MODEL_NAME`,
  `OPTIMIZER_MODEL`, `NEMO_OPTIMIZER_E2E`, and `NEMO_OPTIMIZER_RUNTIME_CACHE` are
  now `NEMO_EXPERIMENTALIST_*`
- the dataset cache moved from `~/.cache/nemo-optimizer/` to
  `~/.cache/nemo-experimentalist/`, so cached datasets re-download once

Two names deliberately did **not** change. `optimizer.yaml` and the
`.nemo-optimizer/` state directory are a shared contract with
`nemo-insights-plugin`: `PROFILE_FILENAME` and `discover_profile()` live in
`nemo_insights_plugin.contracts.profile`, and `nemo agents analyst run` can
mirror the Platform rows it wrote into `<profile-dir>/.nemo-optimizer/insights.yaml`
via `--insights-file-output`, which this plugin reads as the default insight when
the file exists. Rename them only in lockstep with a Platform change to that
contract. `EvolutionaryOptimizer` and `EvolutionaryOptimizerConfig` also keep
their names — they describe the optimization algorithm, not the product.

At the time of this rename the command group was top-level (`nemo
experimentalist`), because the platform's `nemo.cli` entry-point group was flat
and nesting under `nemo agents` needed a Platform-side change first. That change
has since landed — see the `nemo agents` entry above for the current path.

### 2026-07-21: Curator renamed to Eval Author

The Curator agent was renamed directly to Eval Author in ASE-643. This is a
breaking rename with no compatibility aliases or migration layer:

- `nemo_experimentalist_plugin.curator` → `nemo_eval_author_plugin.eval_author` (was `nemo_experimentalist_plugin.eval_author` before extraction)
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
- `nooa` is pinned to an immutable public GitHub revision in the workspace root
  `pyproject.toml` under `[tool.uv.sources]`; this plugin's `pyproject.toml` only
  declares the dependency. It is a commit rather than a tag because the callable
  `@strategy(llm=...)` support this plugin depends on landed after `v0.0.8`.
  Update the root pin, the matching pin in
  `examples/tau3-nooa-agent/pyproject.toml`, the revision quoted in
  `framework-skills/nooa/SKILL.md`, and both lock files together. Keep the
  Platform-supplied Insights plugin separate.
- This branch uses merged Platform PR 718 contracts only. After the Platform
  handoff lands, rebase and repin before adopting any new Platform testbed or
  installer interfaces.
