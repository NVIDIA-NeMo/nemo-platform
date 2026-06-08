# Autopilot Workflow

The user has signaled they don't want to answer questions. Make defensible decisions and keep moving. Do **not** run the full `run` job autonomously — finalize with a one-line command the user can launch.

Source of truth for defaults: `docs/anonymizer/tutorials/index.md` and `docs/anonymizer/tutorials/{preview,run}.md`. If anything below conflicts with the docs, the docs win.

1. **Resolve CLI command** — Run `command -v nemo 2>/dev/null || (test -x .venv/bin/nemo && realpath .venv/bin/nemo) || echo CLI_NOT_FOUND`.
   - If the output is `CLI_NOT_FOUND`, STOP and follow the Troubleshooting section in SKILL.md.
2. **Decide defaults** without asking. Use these unless the user's prompt obviously requires otherwise:
   - **Strategy**: `Redact` with `format_template="[REDACTED_{label}]"`. Use `Substitute` only if the user explicitly says they want realistic synthetic replacements. Use `rewrite` only if the user explicitly mentions rewriting / a privacy goal / utility tradeoff.
   - **Detection config**: keep Anonymizer library defaults unless the user explicitly asks for detection tuning.
   - **`text_column`**: pick the column most plausibly holding free text — `text`, `biography`, `body`, `message`, `content`, `description`, in that order. If you genuinely can't tell, ask one short question.
   - **`id_column`**: include an obvious id column (`id`, `record_id`) if present; otherwise omit.
   - **`num_records`**: 5 for preview.
   - **Preview surface**: `nemo anonymizer preview run` (local) if the input is a local file path. Otherwise (HTTP(S) URL or fileset ref), `nemo anonymizer preview submit`.
   - **Run surface**: `nemo anonymizer run run` for local paths. Use `nemo anonymizer run submit` only when the user explicitly asks for platform/cluster execution or provides a non-local input and model configs.
   - **Model configs**: only set when using a plugin-service surface (`preview submit` / `run submit`) or when the strategy is `Substitute` / `rewrite`. When required, default to `nvidia-build` as the provider (or the provider the user named) with these aliases:
     - `gliner-pii-detector` → `nvidia/gliner-pii`
     - `gpt-oss-120b` → `openai/gpt-oss-120b`
     - `nemotron-30b-thinking` → `nvidia/nemotron-3-nano-30b-a3b`
3. **(If using a plugin-service surface) Confirm the service is mounted.** Run `curl -s http://localhost:8080/openapi.json | jq -r '.paths | keys[]' | grep '^/apis/anonymizer/'`. If nothing prints, tell the user to run `nemo services run` (no `--services` flag) — `nemo setup` does not mount this plugin — then continue. Skip this step entirely for `preview run` / `run run`.
4. **Build** — Write a YAML preview spec following the Output Template in SKILL.md. Default filename: `<text_column>_preview_spec.yaml` (e.g. `biography_preview_spec.yaml`).
5. **Preview** — Run the surface chosen in step 2:
   - Local: `nemo anonymizer preview run --spec-file <path> --workspace <ws>`
   - Plugin service: `nemo anonymizer preview submit --spec-file <path> --workspace <ws>`

   Briefly summarize the preview result — entities detected per label, any `failed_records`, and a one-record before/after example.
6. **Generate run spec** — Without re-prompting, also produce a run YAML named `<text_column>_run_spec.yaml`. It mirrors the preview spec but drops `num_records`. Run writes artifacts, not a dataset entity. Keep `model_configs` only if it was needed for the preview or remote run.
7. **Finalize** — Tell the user the preview ran, briefly summarize what happens to PII under the chosen strategy, and give them the launch command:

   ```bash
   nemo anonymizer run run --spec-file <run_spec>.yaml
   ```

   If the user asked for cluster execution, give `nemo anonymizer run submit --spec-file <run_spec>.yaml --workspace <ws>` instead. Mention that local artifacts are printed to stderr (`Saved result 'artifacts' to file://...`) and remote artifacts can be fetched with:

   ```bash
   nemo jobs get-status <job-name> --workspace <ws>
   nemo jobs results list <job-name> --workspace <ws>
   nemo jobs results download artifacts --job <job-name> --workspace <ws> --output-file artifacts.tar.gz
   ```
