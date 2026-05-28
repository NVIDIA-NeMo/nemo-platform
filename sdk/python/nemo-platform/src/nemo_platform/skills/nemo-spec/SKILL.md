---
name: nemo-spec
description: Captures a NeMo Platform agent spec as a durable artifact at agents/<name>.spec.md (the agent's AGENTSpec.md). Validates the answers from nemo-explore against the AgentSpec schema, writes the file, uploads it to a NeMo Filesets fileset (the canonical copy), then hands the resulting fileset reference to nemo-build-agent. Use over generic planning skills for any NeMo Platform agent spec.
triggers:
  - write the spec
  - save the design
  - capture what we agreed
  - persist the agent design
  - nemo spec
  - write agent spec
  - write AGENT_DESCRIPTION
not-for:
  - nemo-explore (use to gather the design before writing the spec)
  - nemo-build-agent (use to scaffold and deploy once the spec is signed off)
  - nemo-skill-selection (use for dispatch when intent is unclear)
compatibility: nemo-platform >= 0.1.0; writes one markdown file under agents/; uploads it to a NeMo Filesets fileset (the canonical copy) — local file is a write-through cache; safe under any sandbox; idempotent if user confirms overwrite.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Write, Edit, Bash]
---

# NeMo Platform agent spec

Turn the answers from `nemo-explore` into a durable artifact. The spec is
the contract `nemo-build-agent` reads to scaffold the NAT workflow YAML and
the AGENTSpec.md that the analyst and experimentalist agents read as
their primary context. Without it, downstream skills have to re-ask
everything and the optimization loop has no contract for what the agent is
supposed to do or what may be changed.

## Storage model

Two copies of the spec exist intentionally:

* **Canonical**: a NeMo Filesets fileset named `<agent-name>-spec` in the
  active workspace, holding a single file `AGENT_SPEC.md`. The analyst agent
  reads this copy server-side; the platform stores it durably.
* **Local cache**: `agents/<name>.spec.md` in the developer's working
  directory. Hand-editable, version-controlled with the AUT repo, used by
  this skill and by `nemo-build-agent`.

The Fileset wins on conflict. If a developer edits the local file, this
skill re-uploads to refresh the Fileset. If the platform copy has drifted
ahead (e.g. the refinement-mode skill updated it server-side), pull it down
before editing.

## Hard preconditions

Before writing anything, the answers carried over from `nemo-explore` must
satisfy two non-negotiables. If either is missing or ambiguous, **stop and
route back to `nemo-explore` for that field only** — do not invent a
default.

1. **Job** — one concrete sentence describing what the agent does. Vague
   answers ("help with stuff", "answer questions") are rejected at write
   time by the `AgentSpec` validator and will fail the file write.
2. **Framework** — resolved to one of `langgraph-nat` or `needs-wrapper`
   (with a source-framework name when `needs-wrapper`). The Pydantic model
   refuses to construct without it.

The `AgentSpec` Pydantic model (`nemo_agents_plugin.spec`) enforces both at
construction time; this skill enforces them upstream so the user sees a
clear gap-question rather than a stack trace.

## What you do

1. **Confirm the agent name.** Lowercase, hyphens, short: `it-helpdesk`,
   `support-triage`, `code-reviewer`. If the user has not named it, propose
   two options based on the job. Must match `[a-z][a-z0-9-]*`.

2. **Pre-flight: check the local file.** If `agents/${NAME}.spec.md` exists,
   ask the user whether to overwrite or pick a different name.

   ```bash
   ls "agents/${NAME}.spec.md" 2>/dev/null && echo "spec_exists" || echo "spec_new"
   ```

3. **Pre-flight: check the Fileset.** If the canonical copy exists, surface
   it before overwriting (it may be ahead of the local file).

   ```bash
   nemo files filesets get "${NAME}-spec" 2>/dev/null && echo "fileset_exists" || echo "fileset_new"
   ```

   If `fileset_exists` and `spec_new`, pull the canonical copy down before
   editing:

   ```bash
   mkdir -p agents
   nemo files download "${NAME}-spec" AGENT_SPEC.md \
     --local-path "agents/${NAME}.spec.md"
   ```

4. **Render the spec.** Use the template at
   `references/templates/agent-spec.md` as the starting point. Substitute
   every section from the `nemo-explore` answers. Keep section headers and
   labeled-bullet format **exactly** — the file is parsed back into
   `AgentSpec` by `nemo_agents_plugin.spec_render.parse_spec`, and the
   parser rejects unknown sections, duplicate sections, and malformed
   labeled bullets. The template comments name every field.

5. **Write the file.** Path: `agents/<name>.spec.md`. Create the `agents/`
   directory if it does not exist.

6. **Validate before upload.** Round-trip the file through the parser. A
   parse failure here means the file is malformed; fix it before uploading,
   because the analyst agent will reject the same content server-side.

   ```bash
   python -c "
   from pathlib import Path
   from nemo_agents_plugin.spec_render import parse_spec
   spec = parse_spec(Path('agents/${NAME}.spec.md').read_text())
   print(f'valid: name={spec.name} job={spec.job[:60]!r}')
   " || { echo "spec_invalid"; exit 1; }
   ```

7. **Upload to Filesets (canonical copy).** Create the per-agent fileset if
   needed and upload `AGENT_SPEC.md`:

   ```bash
   nemo files filesets create "${NAME}-spec" 2>/dev/null || true
   nemo files upload "agents/${NAME}.spec.md" "${NAME}-spec" \
     --remote-path AGENT_SPEC.md
   ```

   Capture the fileset reference for the handoff. The default form is
   `<workspace>/<name>-spec` (e.g. `default/it-helpdesk-spec`); if the
   workspace was overridden, substitute that instead.

   ```bash
   SPEC_FILE_REF="default/${NAME}-spec"
   echo "${SPEC_FILE_REF}"
   ```

8. **Show the spec to the user.** Print the full file contents and ask:
   "Does this match what we agreed? Edit anything you want to change." If
   the user edits, repeat steps 5–7.

9. **Hand off.** Once confirmed, tell the user the next skill and pass the
   fileset reference:

   - `nemo-build-agent` will read `agents/<name>.spec.md` and produce the
     workflow YAML; when it calls `nemo agents create`, it will pass
     `--spec-file-ref "${SPEC_FILE_REF}"` so the platform Agent entity is
     linked to the spec from creation.
   - The `eval-setup` skill (M2) will fill in the `Eval Command` section
     and front matter when ready.
   - The analyst agent (insights plugin, separate workstream) will read
     `${SPEC_FILE_REF}` server-side once traces exist.

## Verification

After writing and uploading, all three must hold:

```bash
# Local file present and non-empty.
test -s "agents/${NAME}.spec.md" && echo "local_ok" || echo "local_missing"

# Round-trips through the schema.
python -c "
from pathlib import Path
from nemo_agents_plugin.spec_render import parse_spec
parse_spec(Path('agents/${NAME}.spec.md').read_text())
" && echo "schema_ok" || echo "schema_invalid"

# Canonical Fileset copy is reachable.
nemo files list "${NAME}-spec" 2>/dev/null | grep -q AGENT_SPEC.md \
  && echo "fileset_ok" || echo "fileset_missing"
```

Do not announce success until `local_ok`, `schema_ok`, **and** `fileset_ok`
all print, and the user has confirmed the contents.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| `local_missing` after write | Wrong working directory or permission denied | Run `pwd`; check the user is in the cloned repo |
| `schema_invalid` | Spec malformed — unknown section, missing required field, vague job, unresolved framework | Read the parser error; fix the named section in place; do not silently work around |
| `fileset_missing` after upload | Files service down or auth missing | Check `nemo workspaces list`; if that fails, the platform is unreachable — re-upload after `nemo-status` clears |
| User says "this is wrong" | Spec captured the wrong answers | Edit the relevant section in place; re-validate; re-upload |
| Name validation keeps failing | User keeps proposing names with underscores or capitals | Pin the regex `[a-z][a-z0-9-]*` and show one example that passes |
| `nemo-explore` was skipped | User invoked `nemo-spec` cold | Route back to `nemo-explore` and return here when the conversation is done |

## What this skill is not

This skill does not produce NAT workflow YAML. The spec is the
human-readable design; the YAML is generated downstream by
`nemo-build-agent`. It also does not create the `Agent` entity on the
platform — that happens in `nemo-build-agent` via `nemo agents create
--spec-file-ref ...`.

## Gotchas

- **The template is the source of truth for structure.** Do not improvise
  sections. The parser in `nemo_agents_plugin.spec_render` rejects unknown
  sections, duplicate sections, and bullets that don't match the
  `- Label: value` format for structured fields.
- **Spec lives next to the workflow YAML.** Local copies of both files end
  up in `agents/`. Keep them adjacent so a future read of the directory
  shows design and implementation together.
- **The Fileset is canonical, not the local file.** If the two disagree,
  the Fileset wins. Re-pull before editing if you suspect server-side
  drift.
- **Names with underscores or capitals break tools.** Validate against
  `[a-z][a-z0-9-]*`.
- **Job and Framework are hard requirements.** Do not write the spec with
  either missing. Route back to `nemo-explore` for the missing field only.
- **Do not duplicate Insights into the spec.** Known issues / recurring
  failure patterns live in the Insights plugin as first-class entities; the
  spec has no `Known Issues` section.
- **This file is the AGENTSpec.md.** The experimentalist agent will
  not edit it; only the developer and the developer's coding agent do.
  Treat it as a long-lived contract, not a scratch pad.
