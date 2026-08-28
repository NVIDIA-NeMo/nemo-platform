<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Autopilot Workflow

The user has signaled they don't want to answer questions. Make defensible decisions and keep moving. Do **not** run the full `run` job autonomously — finalize with a one-line command the user can launch.

Source of truth for defaults: `docs/anonymizer/tutorials/index.mdx` and `docs/anonymizer/tutorials/{preview,run}.mdx`. If anything below conflicts with the docs, the docs win.

1. **Make sure `nemo` is on PATH** — Run `command -v nemo`. If it is missing but `.venv/bin/nemo` exists, run `export PATH="$(pwd)/.venv/bin:$PATH"` and verify with `command -v nemo`. If `nemo` still cannot be found, follow the Troubleshooting section in SKILL.md, use the SDK/API preview path only, and do not suggest CLI-only commands until `nemo` is available.
2. **Decide defaults** without asking. Use these unless the user's prompt obviously requires otherwise:
   - **Strategy**: `Redact` with `format_template="[REDACTED_{label}]"`. Use `Substitute` only if the user explicitly says they want realistic synthetic replacements. Use `rewrite` only if the user explicitly mentions rewriting / a privacy goal / utility tradeoff.
   - **Detection config**: keep Anonymizer library defaults unless the user explicitly asks for detection tuning.
   - **`text_column`**: pick the column most plausibly holding free text — `text`, `biography`, `body`, `message`, `content`, `description`, in that order. If you genuinely can't tell, ask one short question.
   - **`id_column`**: include an obvious id column (`id`, `record_id`) if present; otherwise omit.
   - **`num_records`**: 5 for preview.
   - **Preview surface**: `nemo anonymizer preview` if the CLI is available, otherwise `sdk.anonymizer.preview(...)` or the preview HTTP API. If the input is a local file path and the CLI is available, pass `--fileset <name>` so the CLI uploads it; otherwise ask the user to upload it to a fileset or provide an HTTP(S) URL.
   - **Run surface**: if the CLI is available, full runs use `nemo anonymizer run` on the Jobs worker. If the input is a local path, pass the same `--fileset <name>` so the CLI uploads it and stores artifacts there.
   - **Model configs**: required for preview and `run`. Default to `nvidia-build` as the provider (or the provider the user named) with these aliases:
     - `gliner-pii-detector` → `nvidia/gliner-pii`
     - `gpt-oss-120b` → `openai/gpt-oss-120b`
     - `nemotron-30b-thinking` → `nvidia/nemotron-3-nano-30b-a3b`
3. **Confirm the plugin service is mounted before service-backed execution.** Run `curl -s http://localhost:8080/openapi.json | jq -r '.paths | keys[]' | grep '^/apis/anonymizer/'` before `nemo anonymizer preview`, SDK/API preview, or a full `nemo anonymizer run`. If nothing prints and `nemo` is available, tell the user to run `nemo services run` (no `--services` flag) and rerun the check before attempting preview or run. If `nemo` is unavailable, tell the user the plugin service must be mounted before SDK/API preview can run. `nemo anonymizer validate` does not need the plugin service.
4. **Build** — Write a preview spec following the Output Template in SKILL.md. Default filename for CLI preview is `<text_column>_preview.yaml` (e.g. `biography_preview.yaml`).
5. **Preview** — Use `nemo anonymizer preview --spec-file <preview_spec>.yaml --workspace <ws> --fileset <fileset> --output-file preview.ndjson` when the CLI is available and `data.source` is local; otherwise use the same command without `--fileset` for HTTP/fileset inputs, or `sdk.anonymizer.preview(...)` / `POST /apis/anonymizer/v2/workspaces/{workspace}/preview`. Briefly summarize the preview result — entities detected per label, any `failed_records`, and a one-record before/after example.
6. **Generate run spec** — If `nemo` is available, produce a run YAML named `<text_column>_run_spec.yaml`. It mirrors the preview request but drops `num_records`. Run writes artifacts, not a dataset entity. If `nemo` is unavailable, skip this step.
7. **Finalize** — Tell the user the preview ran and briefly summarize what happens to PII under the chosen strategy. If `nemo` is unavailable, tell the user to make `nemo` available on PATH before a full run and do not show CLI run or jobs commands. If `nemo` is available, give them the launch command:

   ```bash
   nemo anonymizer run --spec-file <run_spec>.yaml --workspace <ws> --fileset <fileset> --watch --output-dir ./anonymizer-artifacts
   ```

   Mention that the command creates a NeMo Platform job and artifacts can be fetched with:

   ```bash
   nemo jobs get-status <job-name> --workspace <ws>
   nemo jobs results list <job-name> --workspace <ws>
   nemo jobs results download artifacts --job <job-name> --workspace <ws> --output-file artifacts.tar.gz
   ```
