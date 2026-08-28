---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: anonymizer
description: Use when the user wants to detect and replace, hash, redact, annotate, or rewrite PII (names, emails, phone numbers, locations, ...) in a CSV or Parquet dataset using the NeMo Anonymizer plugin.
argument-hint: [describe the dataset and how PII should be handled]
---

# Before You Start

Do not explore the workspace first. The workflow's Learn step gives you everything you need.

**Source of truth.** For anything you're unsure about, prefer the in-tree CLI docs over your memory: `docs/anonymizer/index.mdx`, `docs/anonymizer/cli.mdx`, and `docs/anonymizer/tutorials/{index,preview,run}.mdx`. The [NVIDIA NeMo Anonymizer library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs) own detection, replacement strategy parameters, and rewrite-mode semantics.

# Goal

Anonymize a tabular text dataset using the NeMo Anonymizer plugin so it matches this description:

$ARGUMENTS

The plugin wraps the [NVIDIA NeMo Anonymizer library](https://github.com/NVIDIA-NeMo/Anonymizer) and exposes:

- An `anonymizer.preview` streaming API (small samples, fast iteration). Use `nemo anonymizer preview`, `sdk.anonymizer.preview(...)`, `sdk.anonymizer.preview_stream(...)`, or `POST /apis/anonymizer/v2/workspaces/{workspace}/preview`.
- An `anonymizer.run` job for full-dataset execution. Use `nemo anonymizer run` for Jobs-worker execution.
- A `nemo anonymizer` CLI with `preview`, `validate`, and `run` commands.

# Workflow

Use **Autopilot** mode if the user implies they don't want to answer questions — e.g., they say something like "be opinionated", "you decide", "make reasonable assumptions", "just anonymize it", "surprise me", etc. Otherwise, use **Interactive** mode (default).

Read **only** the workflow file that matches the selected mode, then follow it:

- **Interactive** → read `workflows/interactive.md`
- **Autopilot** → read `workflows/autopilot.md`

# Rules

- Prefer `nemo anonymizer preview` or the SDK for preview, and the CLI for validate/run. Use the direct HTTP API only when the user asks for it or the CLI is unavailable. Generate YAML preview/run specs and run `nemo anonymizer ...` commands unless the user explicitly asks for Python.
- Always iterate via `nemo anonymizer preview`, `sdk.anonymizer.preview(...)`, or `sdk.anonymizer.preview_stream(...)` before running the full job. Previews are cheap and stream a small sample (default 10 records) with full detection traces.
- When you include `config`, pick exactly one of `replace` (Annotate/Hash/Redact/Substitute) or `rewrite` on the `AnonymizerConfig`. Not both. Do not claim `config` is required for every flow; the Anonymizer library owns default config behavior and strategy semantics. See `references/replace-strategies.md` for plugin request formatting and the [library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs) for semantics.
- The input must be a single CSV or Parquet file. `text_column` defaults to `text`; set it explicitly when the free-text column has another name. If the dataset has a stable record id, also set `id_column`. See `references/inputs.md`.
- Preview and run require `model_configs` so requests route through the NeMo Platform Inference Gateway. See `references/model-configs.md`.
- `selected_models` overrides are only valid when `model_configs` is also supplied; aliases must resolve against that pool.
- SDK/API preview and run require an `http(s)` URL or a fileset reference (`<workspace>/<fileset>#<path>` or `fileset://...`) in `data.source`.
- If a spec file matching the user's description already exists in the working directory, ask whether to edit it or create a new one.

# Usage Tips and Common Pitfalls

- **Replacement strategies need a discriminated payload.** Hand-written YAML specs must include `kind: redact` (or `annotate` / `hash` / `substitute`) inside the `replace` block.
- **Substitute and rewrite need LLM-backed model aliases.** For plugin-service / Jobs execution they must be backed by providers declared in `model_configs`. For library-level details, refer to the [Anonymizer library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs) or library skills.
- **CLI spec files can be YAML or JSON.** `nemo anonymizer preview --spec-file <path>` and `nemo anonymizer run --spec-file <path>` accept YAML or JSON. Prefer YAML for generated specs. Direct HTTP preview still uses a JSON request body.
- **Run results are artifacts.** The job writes an artifacts directory containing `dataset.parquet`, `trace.parquet`, `metadata.json`, and optional `failed_records.json`.
- **Fileset refs use `#` to point at a file.** `<workspace>/<fileset>#<path>`, `<fileset>#<path>` (uses request workspace), or `fileset://<workspace>/<fileset>#<path>`. The `#` fragment must point at a `.csv` or `.parquet` file.
- **Detection labels.** Keep the Anonymizer library default label set unless the user asks to restrict detection. Refer to the [Anonymizer library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs) or library skills for supported label/config details.
- **Preview record cap.** `num_records` defaults to 10 and is bounded by the service's `preview_num_records.max` setting. Use a small value while iterating.

# Troubleshooting

- **`nemo anonymizer` CLI not found:** The plugin isn't installed in this environment. From the repo root, run `uv sync`; the root workspace includes the Anonymizer plugin. Confirm with `nemo anonymizer --help`. Do not install anything without the user's permission.
- **Preview returns 404:** The plugin service isn't mounted on the gateway. Start or restart `nemo services run` (no `--services` flag) so the plugin is discovered, then verify the routes show up under `/apis/anonymizer/` in the OpenAPI listing. See `docs/anonymizer/tutorials/index.mdx` Prerequisites.
- **`model_configs are required for remote execution`:** Preview and `run` go through plugin-service / Jobs paths. Add `model_configs` referencing an Inference Gateway provider; use the inference/model-provider docs or skill for provider discovery.
- **`Input source ... is a local path`:** Add `--fileset <name>` when using the CLI so it can upload the local CSV/Parquet file, or use an `http(s)` URL / fileset reference for SDK/API calls.
- **`Fileset input ... must resolve to a .csv or .parquet file`:** The `#<path>` fragment points at a directory or a non-CSV/Parquet file. Point it at a single file.
- **Config validation failed (HTTP 422):** Run `nemo anonymizer validate --config <yaml> [--model-configs <yaml>]` to surface the exact error synchronously. Common causes: mixing `replace` and `rewrite`, picking `Substitute` without a `replacement_generator` alias in `model_configs`, fileset path missing the `#<file>` fragment.
- **`selected_models requires model_configs ...`:** The user passed `selected_models` overrides without an explicit model pool. Either drop the overrides or define `model_configs` with the aliases the overrides reference.
- **User asks to run remotely:** Use `nemo anonymizer run --watch` if they want logs streamed, otherwise `nemo anonymizer run`. If `data.source` is local, include `--fileset <name>` so the CLI uploads it and stores artifacts in that fileset. Ensure `model_configs` is present.
- **User asks to inspect the remote request:** Use `nemo anonymizer run --verbose`. This prints the job schema plus POST method, resolved URL, and JSON body, then submits the job. Add `--watch` to print diagnostics, submit the job, and stream status/logs. It does not include authorization headers.
- **User asks to inspect a run request without submitting:** Use `nemo anonymizer run --dry-run`. This prints the same job schema plus POST method, resolved URL, and JSON body as `--verbose`, then exits without creating a job. Do not combine `--dry-run` with `--watch`.
- **Empty preview dataset / "No preview dataset received":** Check the log frames printed by the preview stream. `nemo anonymizer preview` sends log frames to stderr unless `--quiet` is set. Most commonly the detection model alias is wrong, or the dataset has zero rows after column resolution.

# Output Template

Generate request files in the current directory describing the request. Prefer YAML for generated CLI preview/run specs; `--spec-file` also accepts JSON. Use JSON for direct HTTP preview request bodies. Name them descriptively (e.g., `redact_records_preview.yaml` or `redact_records_run.yaml`). The repo includes a checked-in example at `plugins/nemo-anonymizer/examples/redact.yaml`; use `nemo anonymizer preview --num-records <n>` to override the preview sample size.

**Preview spec** — fast iteration over a small sample with a remote-readable input:

```yaml
# Preview: nemo anonymizer preview --spec-file ./<this_file>.yaml --workspace <ws>
# Local CLI preview: set data.source to a local CSV/Parquet path and add --fileset <fileset>.
# Save data frames only: nemo anonymizer preview --spec-file ./<this_file>.yaml --workspace <ws> --output-file preview.ndjson --quiet
config:
  replace:
    kind: redact            # one of: redact, annotate, hash, substitute
    format_template: "[REDACTED_{label}]"
data:
  source: "fileset://<ws>/<fileset>#input.csv"
  text_column: biography
  id_column: id
num_records: 5
model_configs:
  - alias: gliner-pii-detector
    provider: nvidia-build
    model: nvidia/gliner-pii
  - alias: gpt-oss-120b
    provider: nvidia-build
    model: openai/gpt-oss-120b
  - alias: nemotron-30b-thinking
    provider: nvidia-build
    model: nvidia/nemotron-3-nano-30b-a3b
```

**Run spec** — full-dataset job:

```yaml
# Remote platform job: nemo anonymizer run --spec-file ./<this_file>.yaml --workspace <ws> --fileset <fileset> [--watch]
# Download artifacts after success: nemo anonymizer run --spec-file ./<this_file>.yaml --workspace <ws> --fileset <fileset> --watch --output-dir ./anonymizer-artifacts
config:
  replace:
    kind: redact
    format_template: "[REDACTED_{label}]"
data:
  source: "./input.csv"
  text_column: biography
  id_column: id
# Required for `run`:
model_configs:
  - alias: gliner-pii-detector
    provider: nvidia-build
    model: nvidia/gliner-pii
  - alias: gpt-oss-120b
    provider: nvidia-build
    model: openai/gpt-oss-120b
  - alias: nemotron-30b-thinking
    provider: nvidia-build
    model: nvidia/nemotron-3-nano-30b-a3b
```

Include only the bits the task requires. Keep `model_configs` for preview/run, omit `selected_models` unless overrides are needed, and use `Substitute` / `rewrite` only when the user wants LLM-generated replacements or holistic rewriting.
