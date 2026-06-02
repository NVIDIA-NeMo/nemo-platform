---
name: nemo-spec
description: Captures a NeMo Platform agent spec as a durable artifact at agents/<name>-spec/AGENTSpec.md. Validates the front matter and required markdown sections, writes the file, and uploads it to a NeMo Filesets fileset (the canonical copy). The spec's location is fully derivable from the agent's workspace and name — this skill does not return or persist a ref. Use over generic planning skills for any NeMo Platform agent spec.
triggers:
  - write the spec
  - save the design
  - capture what we agreed
  - persist the agent design
  - nemo spec
  - write agent spec
  - write AGENTSpec
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
the `AGENTSpec.md` that the analyst and experimentalist agents read as
their primary context. Without it, downstream skills have to re-ask
everything and the optimization loop has no contract for what the agent is
supposed to do or what may be changed.

## Storage model

Two copies of the spec exist intentionally:

* **Canonical**: a NeMo Filesets fileset named `<agent-name>-spec` in the
  active workspace, holding a single file `AGENTSpec.md`. The analyst
  agent reads this copy server-side; the platform stores it durably.
* **Local cache**: `agents/<name>-spec/AGENTSpec.md` in the developer's
  working directory. Hand-editable, version-controlled with the AUT repo,
  used by this skill and by `nemo-build-agent`.

The Fileset wins on conflict. If a developer edits the local file, this
skill re-uploads to refresh the Fileset. If the platform copy has drifted
ahead (e.g. the refinement-mode skill updated it server-side), pull it
down before editing.

**The spec's location is by convention, not by reference.** Given an
agent's workspace and name, the remote file ref is always
`<workspace>/<agent-name>-spec#AGENTSpec.md`, mirrored locally at
`agents/<agent-name>-spec/AGENTSpec.md`. The `Agent` entity does
**not** carry a `spec_file_ref` field — downstream consumers compute the
ref from `(workspace, agent_name)` via
`nemo_agents_plugin.entities.agent_spec_file_ref`.

## Hard preconditions

Before writing anything, the answers carried over from `nemo-explore` must
satisfy two non-negotiables. If either is missing or ambiguous, **stop and
route back to `nemo-explore` for that field only** — do not invent a
default.

1. **Role** — one concrete sentence describing the role this agent plays. Vague
   answers ("help with stuff", "answer questions") are rejected at write
   time by the `AgentSpec` validator and will fail the file write.
2. **Framework** — temporary NeMo Platform compatibility status, resolved to
   one of `langgraph-nat` or `needs-wrapper` (with source-framework context
   when `needs-wrapper`). The lightweight parser refuses unresolved framework
   sections.

The AGENTSpec parser (`nemo_agents_plugin.spec_parse.parse_spec`) enforces
both at validation time; this skill enforces them upstream so the user sees a
clear gap-question rather than a parser error.

## What you do

1. **Confirm the agent name.** Lowercase, hyphens, short: `it-helpdesk`,
   `support-triage`, `code-reviewer`. If the user has not named it, propose
   two options based on the role. Must match `[a-z][a-z0-9-]*`.

2. **Pre-flight: check the local file.** If `agents/${NAME}-spec/AGENTSpec.md` exists,
   ask the user whether to overwrite or pick a different name.

   ```bash
   ls "agents/${NAME}-spec/AGENTSpec.md" 2>/dev/null && echo "spec_exists" || echo "spec_new"
   ```

3. **Pre-flight: check the Fileset.** If the canonical copy exists, surface
   it before overwriting (it may be ahead of the local file).

   ```bash
   nemo files filesets get "${NAME}-spec" 2>/dev/null && echo "fileset_exists" || echo "fileset_new"
   ```

   If `fileset_exists` and `spec_new`, pull the canonical copy down before
   editing:

   ```bash
   mkdir -p "agents/${NAME}-spec"
   nemo files download "${NAME}-spec" AGENTSpec.md \
     --local-path "agents/${NAME}-spec/AGENTSpec.md"
   ```

4. **Render the spec.** Use the template at
   `references/templates/agent-spec.md` as the starting point. Substitute
   every section from the `nemo-explore` answers. Set front matter as:
   `name` = the canonical agent name, `created_timestamp` = current UTC
   timestamp in ISO 8601 form, and `author` = the human or coding agent
   creating the file. Evaluation commands live in `Evaluation Setup`, not in
   front matter. Keep the required section headers exactly — the file is
   lightly validated by `nemo_agents_plugin.spec_parse.parse_spec`, which
   checks front matter, required sections, duplicate sections, role quality,
   and resolved framework status. Section bodies stay markdown for agents and
   humans to read directly.

5. **Write the file.** Path: `agents/<name>-spec/AGENTSpec.md`. Create the
   `agents/<name>-spec/` directory if it does not exist.

6. **Validate before upload.** Load the file through the parser. A
   parse failure here means the file is malformed; fix it before uploading,
   because the analyst agent will reject the same content server-side.

   ```bash
   python -c "
   from pathlib import Path
   from nemo_agents_plugin.spec_parse import parse_spec
   spec = parse_spec(Path('agents/${NAME}-spec/AGENTSpec.md').read_text())
   print(f'valid: name={spec.name} role={spec.role[:60]!r}')
   " || { echo "spec_invalid"; exit 1; }
   ```

7. **Upload to Filesets (canonical copy).** Create the per-agent fileset if
   needed and upload `AGENTSpec.md`:

   ```bash
   nemo files filesets create "${NAME}-spec" 2>/dev/null || true
   nemo files upload "agents/${NAME}-spec/AGENTSpec.md" "${NAME}-spec" \
     --remote-path AGENTSpec.md
   ```

   No ref to capture or pass downstream — the location is by convention.
   `nemo-build-agent` and the analyst agent both call
   `agent_spec_file_ref(workspace, name)` to compute
   `<workspace>/<name>-spec#AGENTSpec.md` when they need it.

8. **Show the spec to the user.** Print the full file contents and ask:
   "Does this match what we agreed? Edit anything you want to change." If
   the user edits, repeat steps 5–7.

9. **Hand off.** Once confirmed, tell the user the next skill:

    - `nemo-build-agent` will read `agents/<name>-spec/AGENTSpec.md`, produce the
      workflow YAML, and call `nemo agents create`. It does not need a
      `--spec-file-ref` flag — the spec's location is derivable.
    - The `eval-setup` skill (M2) will fill in the `Evaluation Setup`
      section when ready.
    - The analyst agent (insights plugin, separate workstream) reads the
      same canonical fileset server-side once traces exist.

## Verification

After writing and uploading, all three must hold:

```bash
# Local file present and non-empty.
test -s "agents/${NAME}-spec/AGENTSpec.md" && echo "local_ok" || echo "local_missing"

# Loads through the lightweight AGENTSpec parser.
python -c "
from pathlib import Path
from nemo_agents_plugin.spec_parse import parse_spec
parse_spec(Path('agents/${NAME}-spec/AGENTSpec.md').read_text())
" && echo "spec_parse_ok" || echo "spec_parse_invalid"

# Canonical Fileset copy is reachable.
nemo files list "${NAME}-spec" 2>/dev/null | grep -q AGENTSpec.md \
  && echo "fileset_ok" || echo "fileset_missing"
```

Do not announce success until `local_ok`, `spec_parse_ok`, **and** `fileset_ok`
all print, and the user has confirmed the contents.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| `local_missing` after write | Wrong working directory or permission denied | Run `pwd`; check the user is in the cloned repo |
| `spec_parse_invalid` | Spec malformed — missing front matter, missing required section, duplicate section, vague role, or unresolved framework | Read the parser error; fix the named section in place; do not silently work around |
| `fileset_missing` after upload | Files service down or auth missing | Check `nemo workspaces list`; if that fails, the platform is unreachable — re-upload after `nemo-status` clears |
| User says "this is wrong" | Spec captured the wrong answers | Edit the relevant section in place; re-validate; re-upload |
| Name validation keeps failing | User keeps proposing names with underscores or capitals | Pin the regex `[a-z][a-z0-9-]*` and show one example that passes |
| `nemo-explore` was skipped | User invoked `nemo-spec` cold | Route back to `nemo-explore` and return here when the conversation is done |

## What this skill is not

This skill does not produce NAT workflow YAML. The spec is the
human-readable design; the YAML is generated downstream by
`nemo-build-agent`. It also does not create the `Agent` entity on the
platform — that happens in `nemo-build-agent` via `nemo agents create`.

## Gotchas

- **The template is the source of truth for structure.** Keep the required
  section headings intact. The parser in `nemo_agents_plugin.spec_parse`
  rejects missing or duplicate required sections, but section bodies remain
  markdown for humans and agents to read directly.
- **Spec lives next to the workflow YAML.** Local copies of both files end
  up in `agents/`. Keep them adjacent so a future read of the directory
  shows design and implementation together.
- **The Fileset is canonical, not the local file.** If the two disagree,
  the Fileset wins. Re-pull before editing if you suspect server-side
  drift.
- **The spec's location is convention, not configuration.** Always
  `<workspace>/<agent-name>-spec#AGENTSpec.md`. Do not introduce a flag,
  env var, or persisted field to override it — if the layout needs to
  change, update `agent_spec_file_ref` in
  `nemo_agents_plugin.entities` and every consumer follows.
- **Names with underscores or capitals break tools.** Validate against
  `[a-z][a-z0-9-]*`.
- **Role and Framework are hard requirements.** Do not write the spec with
  either missing. Route back to `nemo-explore` for the missing field only.
- **Do not duplicate Insights into the spec.** Known issues / recurring
  failure patterns live in the Insights plugin as first-class entities; the
  spec has no `Known Issues` section.
- **This file is the `AGENTSpec.md`.** The experimentalist agent will
  not edit it; only the developer and the developer's coding agent do.
  Treat it as a long-lived contract, not a scratch pad.
