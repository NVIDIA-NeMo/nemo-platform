---
name: refresh-data-designer-skill
description: Refresh the vendored data-designer skill bundle in this plugin from the upstream NVIDIA-NeMo/DataDesigner repo at the pinned library version, adapting CLI commands and platform-specific guidance to the NeMo plugin context. Use when bumping the `data-designer` library pin in pyproject.toml, when upstream ships skill changes that need to land here, or when auditing drift. Trigger keywords - refresh data designer skill, update data designer skill, vendor data designer skill, sync data designer skill, bump data-designer version.
---

# Refresh Data Designer Skill

The user-facing data-designer skill at `plugins/nemo-data-designer/src/nemo_data_designer_plugin/skills/data-designer/` is a vendored adaptation of the upstream skill bundle at `https://github.com/NVIDIA-NeMo/DataDesigner` (path `skills/data-designer/`). Upstream is the source of truth; this plugin's copy adds the `nemo` CLI prefix and a small amount of NeMo Platform-specific guidance.

This skill is for plugin contributors. End users do not run it — they get the already-vendored output.

## When to use

- After bumping the `data-designer==X.Y.Z` pin in `plugins/nemo-data-designer/pyproject.toml`.
- When upstream ships skill changes that should land here.
- When auditing drift between the vendored copy and upstream.

## Inputs

- **Source**: `https://github.com/NVIDIA-NeMo/DataDesigner` at tag `v$VERSION` (where `$VERSION` is the value pinned in `pyproject.toml`).
- **Output dir**: `plugins/nemo-data-designer/src/nemo_data_designer_plugin/skills/data-designer/`.

## Procedure

### Step 1 — Determine the pinned version

Extract the version from `plugins/nemo-data-designer/pyproject.toml`:

```bash
grep -E '"data-designer==' plugins/nemo-data-designer/pyproject.toml | head -1
```

Capture the version string (e.g., `0.6.0`) — this is `$VERSION` for the rest of the procedure.

### Step 2 — Enumerate and fetch the upstream bundle

List every file under `skills/data-designer/` at the pinned tag:

```bash
gh api "repos/NVIDIA-NeMo/DataDesigner/git/trees/v$VERSION?recursive=1" \
  | jq -r '.tree[] | select(.path | startswith("skills/data-designer/")) | select(.type=="blob") | .path'
```

For each returned path, fetch raw content from:

```
https://raw.githubusercontent.com/NVIDIA-NeMo/DataDesigner/v$VERSION/<path>
```

Stage the fetched files in a temp directory before adapting.

### Step 3 — Adapt content

Apply the translation rules below to every fetched markdown file. Leave non-markdown files (e.g., `scripts/get_person_object_schema.py`) byte-identical to upstream.

**Single core rule:** prepend `nemo ` to every CLI invocation of the `data-designer` binary. For most subcommands (`agent`, `config`, `validate`), `nemo data-designer …` accepts the same arguments as the upstream library's CLI, so subcommand names, flags, and positional arguments stay identical.

**Exception — `preview` and `create` require a mode subcommand.** The plugin makes `preview` and `create` into command groups with two execution modes: `run` (local, in-process) and `submit` (cluster, over HTTP). Default to `run` for skill instructions — local execution fits the iterative agent workflow. Insert `run` after the subcommand name and before any positional args / flags. So:

- `data-designer preview <path> --save-results` → `nemo data-designer preview run <path> --save-results`
- `data-designer create <path> --num-records <N>` → `nemo data-designer create run <path> --num-records <N>`
- Even prose references like ``the `data-designer preview` command`` should become ``the `nemo data-designer preview run` command`` for consistency with the actual invocation.

**`create` does not accept `--dataset-name` or `--artifact-path`.** Upstream's `create` exposes these flags to name and locate the local artifact folder. The plugin's `create` (both `run` and `submit`) stores artifacts at a Jobs-service-managed path, so there's no local folder to name or relocate. Strip `--dataset-name` and `--artifact-path` (and any related flag values) from upstream `create` invocations during refresh; preserve other flags like `--num-records` as-is.

This applies to every shell-prompt and backticked invocation of:

- `data-designer agent context` (and other `agent …` subcommands) → just prepend `nemo `
- `data-designer config providers|models|…` → just prepend `nemo `
- `data-designer validate <path>` → just prepend `nemo `
- `data-designer preview <path>` (and any flags after) → prepend `nemo ` AND insert `run`
- `data-designer create <path>` (and any flags after) → prepend `nemo ` AND insert `run`

Do **not** rewrite prose mentions of the project name (e.g., "the Data Designer library", "Data Designer columns"). Only shell-shaped invocations.

**Resolve-CLI-command step replacement:**

Upstream's workflow files (`workflows/interactive.md`, `workflows/autopilot.md`) start with a "Resolve CLI command" step that detects the standalone `data-designer` binary. Replace that step with one that detects the `nemo` binary instead:

```
1. **Resolve CLI command** — Run `command -v nemo 2>/dev/null || (test -x .venv/bin/nemo && realpath .venv/bin/nemo) || echo CLI_NOT_FOUND`.
  - If the output is a path, use `<path> data-designer` as the command prefix for all `nemo data-designer …` invocations in this workflow.
  - If the output is `CLI_NOT_FOUND`, STOP and follow the Troubleshooting section in SKILL.md. Do not continue to the next step.
```

**Model-configs-source step replacement:**

Upstream's workflow "Learn" step instructs the agent to stop if `agent context` reports no usable model aliases. In this plugin that's wrong — model configs can be declared programmatically and routed through IGW providers, neither of which `agent context` sees. Replace the "no aliases = stop" line with plugin-aware wording that points at `references/nemo-platform-plugin-additions.md` and explicitly says "do not stop." Also update the workflow's Clarify / Infer step (if present) so it asks about IGW provider choice when no local aliases exist. Both `workflows/interactive.md` and `workflows/autopilot.md` need this adaptation.

**Output Template `model_configs` skeleton:**

The plugin's `SKILL.md` Output Template includes an inline `model_configs=[dd.ModelConfig(...)]` skeleton inside the `DataDesignerConfigBuilder(...)` constructor, with a comment pointing at `nemo inference providers list` for provider discovery and at `references/nemo-platform-plugin-additions.md` for guidance. Preserve this on refresh — agents follow the template closely, and stripping it back to upstream's empty `DataDesignerConfigBuilder()` re-introduces the model-configs blindness this skill is supposed to compensate for.

### Step 4 — Add the plugin-additions reference file

The `nemo data-designer` CLI accepts the same arguments as the upstream `data-designer` CLI for `agent`, `config`, `validate`, `preview`, and `create`. The plugin adds a `personas` subcommand group that has no upstream counterpart, plus optional NeMo Platform-side affordances. Capture those additions in a single file: `references/nemo-platform-plugin-additions.md`.

Recommended sections:

- **Model configs**: Explain that `DataDesignerConfigBuilder` accepts `model_configs=[dd.ModelConfig(...)]` programmatically and that `ModelConfig.provider` can reference an IGW-managed provider (bare name or `<workspace>/<provider>`), with `nemo inference providers list` as the discovery command. Emphasize that `agent context` does **not** see these sources, so an empty alias list is not a blocker. This section is the anchor that the workflow's plugin-aware "no aliases ≠ stop" wording points at.
- **Personas**: `nemo data-designer personas download` (install Nemotron Personas locales locally) and `nemo data-designer personas make-fileset` (publish a fileset to the NeMo Platform files service for cluster-side use). Cross-reference upstream's `references/person-sampling.md` for general persona-column usage; only document the plugin-specific install / publish steps here.
- **NeMo Platform-side resources** (only if relevant to the workflow): pointers to `nemo inference providers list`, `nemo files`, `nemo secrets`, etc. — i.e., NeMo Platform-managed alternatives to local config that the user may already have set up.

Keep this file additive. Do not duplicate or contradict upstream content; if upstream covers a topic, defer to it.

When describing the upstream-vs-plugin difference for `preview` / `create`, avoid reproducing literal upstream-shaped shell invocations like `` `data-designer preview <path>` `` — those will trip the verification grep in Step 6 even though they're descriptive, not prescriptive. Phrase the difference in prose ("upstream's `preview` is a flat command that takes the config path directly") rather than in shell-shaped form.

After writing this file, add a single bullet to the **Rules** section of the top-level `SKILL.md` pointing agents at it. Example: `- For commands and context specific to this NeMo Platform plugin (e.g., sourcing model configs from IGW providers or in-script \`ModelConfig\`s, installing or publishing Nemotron Personas locales, platform-side resource pointers), read \`references/nemo-platform-plugin-additions.md\`.` Without this pointer, agents will never read the additions file.

### Step 5 — Write the bundle

Write the adapted bundle to `plugins/nemo-data-designer/src/nemo_data_designer_plugin/skills/data-designer/`. Mirror the upstream tree exactly — same subdirectory names (`workflows/`, `references/`, `scripts/`), same filenames. Add the new `references/nemo-platform-plugin-additions.md` you produced in Step 4.

If a previous vendored bundle exists, remove the old files first (so deletions upstream are reflected).

### Step 6 — Verify

Run these checks and resolve any failures before considering the refresh complete:

**No untranslated CLI invocations remain.** This greps for `data-designer` not preceded by `nemo `, in shell-command contexts (backtick-fenced or shell prompts):

```bash
SKILLS=plugins/nemo-data-designer/src/nemo_data_designer_plugin/skills/data-designer
grep -RnE '(\s|`)data-designer\s' "$SKILLS" | grep -v 'nemo data-designer'
```

A clean run produces no output. False positives in prose ("the Data Designer library") are fine; CLI-shaped invocations are not.

**Every referenced subcommand resolves.** Extract the unique `nemo data-designer …` invocations and confirm each has a help page:

```bash
grep -RhoE 'nemo data-designer [a-z][a-z -]*' "$SKILLS" \
  | sort -u \
  | while read -r cmd; do
      eval "$cmd --help" > /dev/null 2>&1 && echo "OK: $cmd" || echo "MISSING: $cmd"
    done
```

Any `MISSING:` line indicates upstream changed the command surface or `nemo data-designer` has drifted from upstream's CLI shape — investigate before merging.

**Every `preview` / `create` invocation has a mode subcommand.** The plugin requires `run` or `submit` after `preview` and `create`. This grep catches missed insertions:

```bash
grep -RnE 'nemo data-designer (preview|create) ' "$SKILLS" \
  | grep -vE '(preview|create) (run|submit)[^a-z]'
```

A clean run produces no output. The trailing `[^a-z]` allows backtick-bounded references like ``the `nemo data-designer preview run` command`` to pass without a trailing space.

## Notes

- Upstream may add new files under `skills/data-designer/` (e.g., new references). Pick them up automatically via the tree enumeration in Step 2 — don't rely on a static file list.
- Upstream may rename or remove files. The Step 5 "remove old files first" pass handles deletions; renames surface as a removed-old + added-new pair, which is the expected outcome.
- Don't edit the bundled non-markdown files (e.g., `scripts/*.py`). They're upstream's responsibility.
- The single core rule (`data-designer ` → `nemo data-designer `) holds because `nemo data-designer` accepts the same arguments as upstream's CLI. If that ever stops being true (a flag diverges, a subcommand is renamed in only one of the two), call it out explicitly here and adapt the affected workflow step rather than silently hand-editing vendored output.
