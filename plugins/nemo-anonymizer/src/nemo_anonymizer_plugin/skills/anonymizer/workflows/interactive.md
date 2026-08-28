<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Interactive Workflow

This is an interactive, iterative anonymization design process. Do not disengage from the loop unless the user says they are satisfied.

Source of truth for this workflow: `docs/anonymizer/tutorials/index.mdx`, `docs/anonymizer/tutorials/preview.mdx`, and `docs/anonymizer/tutorials/run.mdx`. Defer to them if the CLI flags or capabilities here look out of date.

1. **Make sure `nemo` is on PATH** — Run `command -v nemo`. If it is missing but `.venv/bin/nemo` exists, run `export PATH="$(pwd)/.venv/bin:$PATH"` and verify with `command -v nemo`. If `nemo` still cannot be found, follow the Troubleshooting section in SKILL.md, use the SDK/API preview path only, and do not suggest CLI-only commands until `nemo` is available.
2. **Confirm the plugin service is mounted before service-backed execution.** Run `curl -s http://localhost:8080/openapi.json | jq -r '.paths | keys[]' | grep '^/apis/anonymizer/'` before `nemo anonymizer preview`, SDK/API preview, or `nemo anonymizer run`. If nothing prints, the plugin service isn't loaded; if `nemo` is available, tell the user to run `nemo services run` (no `--services` flag) and rerun the check. If `nemo` is unavailable, tell the user the plugin service must be mounted before SDK/API preview can run. `nemo anonymizer validate` does not need the plugin service.
3. **Confirm input source** — Decide whether you're working with a local CSV/Parquet file, an `http(s)://` URL, or a NeMo Platform fileset reference. If the user named a local file and the CLI is available, choose or ask for the `--fileset` name the CLI should use for upload and outputs (see `references/inputs.md`).
4. **Clarify** — Ask the user clarifying questions to narrow down precisely what they want. Prefer a structured question tool if one is available, batch related questions together, keep the set short, and offer concrete options/defaults. Common things to make precise:
   - **Text column** to scan and (optional) **id column**.
   - **What to do with detected entities**: redact, annotate (tag inline), hash (deterministic token), substitute with realistic LLM-generated values, or fully rewrite the text under a privacy goal. See `references/replace-strategies.md` and `references/rewrite-mode.md`.
   - **Detection tuning** — keep Anonymizer library defaults unless the user explicitly asks for label/threshold changes; refer to the [Anonymizer library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs) or library skills for those details.
   - **Preview surface** — `nemo anonymizer preview` if the CLI is available, otherwise `sdk.anonymizer.preview(...)` or the preview HTTP API.
   - **Run surface** — if the CLI is available, full runs use `nemo anonymizer run` for Jobs-worker execution. If the input is local, pass `--fileset <name>` so the CLI uploads it and stores artifacts there.
5. **Resolve model providers** — Ask which provider(s) and model aliases to use. Preview and run require `model_configs` so model calls route through the Inference Gateway. For provider discovery or creation, refer to the platform inference/model-provider docs or the relevant inference/model skill. See `references/model-configs.md`.
6. **Plan** — Summarize the planned config (replace vs rewrite strategy, detection tuning, model_configs, input source, num_records, preview surface) and ask the user to confirm before writing the request.
7. **Build** — Write a preview spec following the Output Template in SKILL.md. Use YAML for CLI preview, JSON for direct HTTP preview, or a `PreviewRequest` object for SDK preview.
8. **Validate (optional, CLI only)** — If `nemo` is available and you've also produced a stand-alone `AnonymizerConfig` YAML (e.g., the user wants `nemo anonymizer validate` to gate the run), invoke it now and address any errors before previewing.
9. **Preview** — Use `nemo anonymizer preview --spec-file <preview_spec>.yaml --workspace <ws> --fileset <fileset> --output-file preview.ndjson` when the CLI is available and `data.source` is local; otherwise use the same command without `--fileset` for HTTP/fileset inputs, or `sdk.anonymizer.preview(...)` / `POST /apis/anonymizer/v2/workspaces/{workspace}/preview`. Inspect the resulting `AnonymizerPreviewResult` or NDJSON frames: `log` lines, the `preview_dataset`, the `trace_dataset`, and any `failed_records`. Surface anything in `failed_records` to the user.
10. **Iterate**
    - Ask the user for feedback on the preview output. Offer to review the records yourself and suggest plugin-surface fixes (input source, model configs, selected model aliases) or refer to Anonymizer library docs/skills for library-level tuning. See `references/preview-review.md`.
    - Apply changes, re-preview. Repeat until the user is satisfied.
11. **Finalize** — Once the user is happy with the preview, only continue to full-run guidance if `nemo` is available. If it is unavailable, tell the user to make `nemo` available on PATH before a full run and do not show CLI run or jobs commands. If it is available:
    - Generate a run spec by dropping `num_records` from the preview request. Run writes artifacts, not a dataset entity.
    - Tell the user they can submit the full job with:

      ```bash
      nemo anonymizer run --spec-file <run_spec>.yaml --workspace <ws> --fileset <fileset> --watch --output-dir ./anonymizer-artifacts
      ```

    - If they want to inspect the submit request first, tell them to use:

      ```bash
      nemo anonymizer run --spec-file <run_spec>.yaml --workspace <ws> --fileset <fileset> --verbose
      ```

      Use `--dry-run` instead of `--verbose` to print the schema and request without creating a job. Full runs require `model_configs`; local CLI input requires `--fileset`.
    - For jobs, show the CLI follow-up commands:

      ```bash
      nemo jobs get-status <job-name> --workspace <ws>
      nemo jobs get-logs <job-name> --workspace <ws> --all-pages
      nemo jobs results list <job-name> --workspace <ws>
      nemo jobs results download artifacts --job <job-name> --workspace <ws> --output-file artifacts.tar.gz
      ```
    - Caution that runtime depends on dataset size and the chosen strategy (LLM-backed strategies are slower).
    - Do not run the full job yourself — let the user decide when to launch it.
