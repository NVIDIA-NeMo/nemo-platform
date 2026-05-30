# Autopilot Workflow

In this mode, make reasonable design decisions autonomously based on the dataset description. Do not ask clarifying questions — infer sensible defaults and move straight through to a working preview.

1. **Resolve CLI command** — Run `command -v nemo 2>/dev/null || (test -x .venv/bin/nemo && realpath .venv/bin/nemo) || echo CLI_NOT_FOUND`.
  - If the output is a path, use `<path> data-designer` as the command prefix for all `nemo data-designer …` invocations in this workflow.
  - If the output is `CLI_NOT_FOUND`, continue in script-only mode: build the Python file, but skip `agent context`, validate, preview, and create. In the final response, state that those steps are blocked because `nemo data-designer` is unavailable.
2. **Learn** — Run `nemo data-designer agent context`.
  - In script-only mode, skip this command and rely on SKILL.md, the relevant references, and the Output Template.
  - `agent context` only inspects the local `~/.data-designer/` registry; it does not see IGW-managed providers or in-script `ModelConfig`s. Whether or not it lists usable aliases, read `references/nemo-platform-plugin-additions.md` for the model-config options before proceeding. Default to declaring `model_configs` programmatically with an IGW provider — that path is portable across local `run` and cluster `submit`. Note your provider choice as one of the key decisions in step 3.
  - If the dataset requires person data such as names, demographics, addresses, or emails, read `references/person-sampling.md`. Run `python scripts/get_person_object_schema.py <locale>` when possible; if Python or dependencies are unavailable, cite the script path and proceed with the documented fallback.
  - Inspect schemas for every column, sampler type, validator, and processor you plan to use.
  - Never guess types or parameters — read the relevant config files first.
  - Always read `base.py` for inherited fields shared by all config objects.
3. **Infer** — Based on the dataset description, make reasonable decisions for:
  - Axes of diversity and what should be well represented.
  - Which variables to randomize.
  - The schema of the final dataset.
  - The structure of any structured output columns.
  - Briefly state the key decisions you made so the user can course-correct if needed.
4. **Plan** — Determine columns, samplers, processors, validators, and other dataset features needed.
5. **Build** — Write the Python script with `load_config_builder()` returning a `DataDesignerConfigBuilder` (see Output Template in SKILL.md).
  - Before any final response, confirm the script satisfies the Generated Script Acceptance Checklist in SKILL.md.
6. **Validate** — Run `nemo data-designer validate <path>`. Address any warnings or errors and re-validate until it passes. In script-only mode, skip this step and report the CLI blocker.
7. **Preview** — Run `nemo data-designer preview run <path> --save-results` to generate sample records as HTML files.
  - Note the sample records directory printed by the `nemo data-designer preview run` command
  - Give the user a clickable link: `file://<sample-records-dir>/sample_records_browser.html`
  - In script-only mode, skip this step and report the CLI blocker.
8. **Create** — If the user specified a record count:
  - Run `nemo data-designer create run <path> --num-records <N>`.
  - Generation speed depends heavily on the dataset configuration and the user's inference setup. For larger datasets, warn the user and ask for confirmation before running.
  - If no record count was specified, skip this step.
  - In script-only mode, skip this step and report the CLI blocker.
9. **Present** — Summarize what was built: columns, samplers used, key design choices. If the create command was run, share the results. Ask the user if they want any changes. If so, edit the script, re-validate, re-preview, and iterate.
