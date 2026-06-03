---
name: safe-synthesizer
description: "Use NeMo Safe Synthesizer from the NMP plugin through task-specific routing: host-local GPU runs, platform job submission, configuration, troubleshooting, artifacts, privacy settings, PII replacement, and evaluation reports. Use when the user asks about safe-synthesizer, NeMo Safe Synthesizer, synthetic tabular data, DP settings, generation failures, plugin-local runs, filesets, model filesets, or `nemo safe-synthesizer` CLI commands."
license: Apache-2.0
---

# Safe Synthesizer

Task router for agents helping a person use the NeMo Safe Synthesizer NMP plugin. Read the task file that matches the user request before giving user-facing instructions.

## Prerequisites

- The NeMo Safe Synthesizer plugin is installed in the active NeMo Platform environment.
- The `nemo safe-synthesizer` CLI is available, or repo development can use `uv run nemo safe-synthesizer`.
- Host-local generation requires a Linux host with a CUDA-capable NVIDIA GPU, compatible drivers, and a runtime created by `nemo safe-synthesizer runtime setup`.
- Platform jobs require workspace access to the input fileset and any `hf_token_secret` or PII classification provider.
- Fileset references use `<workspace>/<fileset>#<path>` unless a workflow states otherwise.

## Route

- Run the plugin locally or submit platform jobs: read `workflows/run.md`.
- Set or override job parameters: read `workflows/config.md`.
- Diagnose runtime, install, generation, OOM, validation, or fileset failures: read `workflows/diagnose.md`.
- Retrieve job result artifacts: read `workflows/results.md`.
- Interpret outputs, logs, synthetic data, reports, summaries, or adapters: read `workflows/artifacts.md`.

## Plugin-Specific Rules

- Prefer the plugin CLI surface over upstream-only commands.
- Use `nemo safe-synthesizer run-local` for host-local CUDA/GPU development.
- Use `nemo safe-synthesizer runtime setup` to install engine/CUDA dependencies into the separate runtime venv.
- Use the Jobs API or SDK for platform jobs. The `nemo safe-synthesizer` CLI exposes `run-local` and `runtime` only.
- Treat `data_source` as a fileset URL for platform jobs, usually `<workspace>/<fileset>#<path>`.
- For local runs, prefer `--data-source <local-file-or-dir>` when the input is already on disk.
- If the job uses PII classification, `config.replace_pii.globals.classify.classify_model_provider` must be `<workspace>/<provider_name>`.
- Keep usage guidance separate from plugin source development internals unless the user asks to change the plugin.

## Answer Contract

- Start with the direct command, diagnosis, or file path.
- Cite relevant repo docs paths when useful, especially `plugins/nemo-safe-synthesizer/README.md` and `docs/safe-synthesizer/getting-started.md`.
- Include one concrete next action unless the user asks for a full walkthrough.
- If the user asks to change CLI, config, job compilation, or task source code, inspect the plugin code before answering.

## Next Steps

- Start local usage from `plugins/nemo-safe-synthesizer/README.md`.
- For product docs, use `docs/safe-synthesizer/getting-started.md`.
- For commands, read `workflows/run.md`.
- For configuration, read `workflows/config.md`, then `workflows/config-runs.md` for examples.
- For failures, read `workflows/diagnose.md`.
- For outputs, read `workflows/results.md` and `workflows/artifacts.md`.
