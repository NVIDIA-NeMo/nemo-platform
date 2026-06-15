# Interactive Workflow

This is an interactive, iterative anonymization design process. Do not disengage from the loop unless the user says they are satisfied.

Source of truth for this workflow: `docs/anonymizer/tutorials/index.md`, `docs/anonymizer/tutorials/preview.md`, and `docs/anonymizer/tutorials/run.md`. Defer to them if the CLI flags or capabilities here look out of date.

1. **Resolve CLI command** — Run `command -v nemo 2>/dev/null || (test -x .venv/bin/nemo && realpath .venv/bin/nemo) || echo CLI_NOT_FOUND`.
   - If the output is a path, use `<path> anonymizer` as the command prefix for all `nemo anonymizer …` invocations in this workflow.
   - If the output is `CLI_NOT_FOUND`, STOP and follow the Troubleshooting section in SKILL.md. Do not continue.
2. **Confirm the plugin service is mounted (only if the user wants `preview submit` or `run submit`).** Run `curl -s http://localhost:8080/openapi.json | jq -r '.paths | keys[]' | grep '^/apis/anonymizer/'`. If nothing prints, the plugin service isn't loaded — `nemo setup` does not auto-mount it. Tell the user to run `nemo services run` (no `--services` flag) and rerun the check. Local previews (`preview run`) and local runs (`run run`) do **not** need the plugin service mounted.
3. **Confirm input source** — Decide which kind of input you're working with: a local CSV/Parquet file, an `http(s)://` URL, or a NeMo Platform fileset reference. If the user named a file but it's not yet on the platform and they want to use `preview submit`, ask whether to upload it to a fileset first (see `references/inputs.md`).
4. **Clarify** — Ask the user clarifying questions to narrow down precisely what they want. Prefer a structured question tool if one is available, batch related questions together, keep the set short, and offer concrete options/defaults. Common things to make precise:
   - **Text column** to scan and (optional) **id column**.
   - **What to do with detected entities**: redact, annotate (tag inline), hash (deterministic token), substitute with realistic LLM-generated values, or fully rewrite the text under a privacy goal. See `references/replace-strategies.md` and `references/rewrite-mode.md`.
   - **Detection tuning** — keep Anonymizer library defaults unless the user explicitly asks for label/threshold changes; refer to the [Anonymizer library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs) or library skills for those details.
   - **Preview surface** — `preview run` (local, allows local paths) or `preview submit` (plugin service via CLI).
   - **Run surface** — `nemo anonymizer run run` for local in-process execution or `nemo anonymizer run submit` for Jobs-worker execution. This is the Anonymizer equivalent of Data Designer's `create run` / `create submit` pattern.
5. **Resolve model providers (only if needed)** — If the preview is going through the plugin service (`preview submit`), or the chosen replacement strategy is `Substitute` or `Rewrite`, ask which provider(s) and model aliases to use. For provider discovery or creation, refer to the platform inference/model-provider docs or the relevant inference/model skill. See `references/model-configs.md`.
6. **Plan** — Summarize the planned config (replace vs rewrite strategy, detection tuning, model_configs, input source, num_records, preview surface) and ask the user to confirm before writing the spec.
7. **Build** — Write a YAML spec file following the Output Template in SKILL.md. Use the **Preview** shape first.
8. **Validate (optional)** — If you've also produced a stand-alone `AnonymizerConfig` YAML (e.g., the user wants `nemo anonymizer validate` to gate the run), invoke it now and address any errors before previewing.
9. **Preview** — Pick the surface you agreed on in step 4:
   - Local CLI: `nemo anonymizer preview run --spec-file <path> --workspace <ws>`
   - Plugin service via CLI: `nemo anonymizer preview submit --spec-file <path> --workspace <ws>`

   Inspect the resulting NDJSON frames: `log` lines, the `preview_dataset`, the `trace_dataset`, and any `failed_records`. Surface anything in `failed_records` to the user.
10. **Iterate**
    - Ask the user for feedback on the preview output. Offer to review the records yourself and suggest plugin-surface fixes (input source, model configs, selected model aliases) or refer to Anonymizer library docs/skills for library-level tuning. See `references/preview-review.md`.
    - Apply changes, re-preview. Repeat until the user is satisfied.
11. **Finalize** — Once the user is happy with the preview:
    - Generate a run spec by dropping `num_records` from the preview request. Run writes artifacts, not a dataset entity.
    - Tell the user they can run the full job locally with:

      ```bash
      nemo anonymizer run run --spec-file <run_spec>.yaml
      ```

    - If they want platform execution, tell them to use:

      ```bash
      nemo anonymizer run submit --spec-file <run_spec>.yaml --workspace <ws>
      ```

      The remote path requires `model_configs` and rejects local file paths.
    - For remote jobs, show the CLI follow-up commands:

      ```bash
      nemo jobs get-status <job-name> --workspace <ws>
      nemo jobs get-logs <job-name> --workspace <ws> --all-pages
      nemo jobs results list <job-name> --workspace <ws>
      nemo jobs results download artifacts --job <job-name> --workspace <ws> --output-file artifacts.tar.gz
      ```
    - Note that local `run run` prints `{"exit_code": 0}` on success and logs the artifact directory to **stderr** in the form `Saved result 'artifacts' to file:///.../persistent/results/artifacts`. Walk through `references/inputs.md` if the user wants help loading those artifacts.
    - Caution that runtime depends on dataset size and the chosen strategy (LLM-backed strategies are slower).
    - Do not run the full job yourself — let the user decide when to launch it.
