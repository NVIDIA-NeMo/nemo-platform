<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ETHOS authoritative rename

Date: 2026-08-19  
Status: approved for implementation (PR 1 of the ETHOS two-PR roadmap)

This record, the migration code, the migration tests and fixtures, the migration
guide, and the boundary checker are the only places that may name the old
artifact. Every other file moves to `ethos`.

## Problem

The agent behavior contract has two names. Code, flags, prompts, Filesets, and
documentation use `AGENT-SPEC.md` and `agent_spec`, while the product calls the
artifact ETHOS. The mixed vocabulary costs the `nemo-agents`, Analyst, and
Experimentalist teams review time, and it blocks the schema work.

One change that both renames the artifact and versions its schema is too large
to review. PR 1 renames only. PR 2 owns schema v1 and intent-first onboarding.

## Goals

- Make `ETHOS.md` the one canonical filename.
- Move every artifact-specific path, symbol, flag, and field to `ethos`.
- Keep the unversioned 13-section schema and the parser behavior unchanged.
- Give users one command that migrates local packages, Filesets, and profiles.
- Confine the old vocabulary to a boundary that a repository check enforces.

## Non-goals

PR 1 adds none of these:

- `schema_version` or any other version field;
- additional sections such as Vision, Constraints, or Priorities;
- a status, draft, or approval field;
- changes to the `nemo-explore` interview behavior;
- automated spend questions;
- Change Scope presets;
- a machine-readable objective function;
- compatibility aliases, runtime fallbacks, or deprecation shims;
- changes to the meaning or the format of existing section bodies.

## Artifact and storage decisions

Hard-rename the artifact. Each value below replaces the old form completely.

| Item | Value after PR 1 |
| --- | --- |
| Filename | `ETHOS.md` |
| Local package | `agents/<agent-name>-ethos/` |
| Fileset | `<agent-name>-ethos` |
| Ethos file ref | `<workspace>/<agent-name>-ethos#ETHOS.md` |
| Config file ref | `<workspace>/<agent-name>-ethos#agent.yaml` |
| Writer skill | `nemo-ethos` |

The complete package moves. `agent.yaml`, packaged skills, and every other
relative artifact keep their positions inside the package. Runtime container
staging keeps excluding the contract file.

## Preserved schema and parser behavior

The front matter keeps three required fields and no version key:

```yaml
---
name: <canonical-agent-name>
created_timestamp: <ISO 8601 timestamp>
author: <human or agent>
---
```

The document keeps the same 13 required `##` headings, in this canonical order:
Role, Purpose, Scope, Tools, Model, Framework, Harness, Behavior, Success
Criteria, Evaluation Setup, Change Scope, Signals, and Open Questions.

`parse_ethos()` keeps the exact behavior of `parse_spec()`. The list below is the
complete validation set, transcribed from `spec_parse.py`. Every item must hold
after the rename.

Front matter:

1. The document must start with a `---` fence. The match is anchored at offset 0,
   so a leading blank line, comment, or heading fails with
   `missing YAML front matter`.
2. `yaml.safe_load` must return a mapping. An empty block becomes `{}`. Any other
   type fails with `YAML front matter must be a mapping`.
3. `name` must be a non-empty string. The parser strips it.
4. `author` must be a non-empty string. The parser strips it.
5. `created_timestamp` accepts a `datetime` as-is. It accepts a non-empty string
   through `datetime.fromisoformat`, after `str.replace` substitutes `+00:00` for
   every `Z`. Any other value fails as required or as not ISO 8601.
6. Extra front-matter keys are ignored, not rejected.

Sections:

7. Headings match `^## +(.+?)\s*$` in multiline mode. At least one space is
   required, so `##Role` is body text, not a heading.
8. A repeated heading fails with `duplicate section: ## <title>`. The rule covers
   every `##` heading, not only the 13 required ones.
9. Each required title must be present, or the parse fails with
   `missing section: ## <title>`.
10. `Framework`, once stripped, must be neither empty nor `_(none)_`.
11. Section bodies keep raw markdown. The parser strips leading and trailing
    newlines only, so inner blank lines, indentation, and `###` subheadings
    survive unchanged.
12. Extra `##` sections are kept in `sections`.
13. Text between the front matter and the first `##` heading is discarded. The
    H1 title and the template banner live there, so neither reaches `sections`.

Order and typing:

14. Validation order is fixed: front matter fence, mapping type, section split,
    required sections, Framework, then the three front-matter fields. A document
    that is missing both a section and `name` reports the section first. Error
    tests depend on this order.
15. Every failure raises one exception type. `SpecParseError` becomes
    `EthosParseError` and stays a `ValueError` subclass.
16. `Ethos.role` returns `sections["Role"]`.

The parser enforces nothing else. It does not check section order, role quality,
bullet format, label format, or framework enum values.

Correct the skill text that claims otherwise. `nemo-spec/SKILL.md` states that
the validator rejects a vague role and that the parser checks "role quality".
Neither is true. Role quality, bullet format, and the
`supported-harness`, `nat-workflow`, and `needs-adapter` values stay skill
guidance, and the skill must say so.

## Module and symbol renames

Rename these files and symbols with no import alias and no deprecated wrapper:

```text
plugins/nemo-agents/src/nemo_agents_plugin/spec.py        -> ethos.py
plugins/nemo-agents/src/nemo_agents_plugin/spec_parse.py  -> ethos_parse.py
plugins/nemo-agents/tests/unit/test_spec_parse.py         -> test_ethos_parse.py

AGENT_SPEC_SECTION_TITLES -> ETHOS_SECTION_TITLES
AgentSpec                 -> Ethos
SpecParseError            -> EthosParseError
parse_spec                -> parse_ethos
```

`entities.py` renames its storage constants and helpers:

```text
AGENT_SPEC_FILENAME         -> ETHOS_FILENAME = "ETHOS.md"
AGENT_SPEC_LOCAL_ROOT       -> ETHOS_LOCAL_ROOT = "agents"
MAX_AGENT_SPEC_STAGED_BYTES -> MAX_ETHOS_STAGED_BYTES
MAX_AGENT_SPEC_STAGED_FILES -> MAX_ETHOS_STAGED_FILES
agent_spec_fileset_name()   -> ethos_fileset_name()
agent_spec_local_path()     -> ethos_local_path()
agent_spec_file_ref()       -> ethos_file_ref()
```

`agent_config_file_ref()` keeps its name and returns the renamed Fileset. The
`nemo-agents` CLI, `runner/fabric_artifact_staging.py`, and their entity, CLI,
deletion, and staging tests follow the same rename.

`parse_ethos(markdown: str) -> Ethos` stays a pure parser of the unversioned
13-section schema. It takes markdown and returns a value, with no file or network
access.

## Public interface renames

```text
--agent-spec           -> --ethos
agent_spec:            -> ethos:
AnalyzeSpec.agent_spec -> AnalyzeSpec.ethos
```

The old forms are not runtime aliases. Only the migration module may read an old
form, and it reads that form only to rewrite it.

Also rename the unrelated Git-source helper `split_agent_spec()` in
`plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/experimentalist/components/repository.py`
to `split_agent_source_uri()`. That function splits `<url@ref>#<agent_path>` and
has nothing to do with the contract, so the old phrase must not survive under a
second meaning.

## Skill rename

```text
packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-spec/
  -> .../skills/nemo-ethos/
references/templates/agent-spec.md -> references/templates/ethos.md
```

`nemo-ethos` writes the same unversioned 13-section content at the renamed
package and filename. It runs no intent-first interview in PR 1.

### Detection belongs to migration

The migration module is the only code that names or reads an old form. The
shipped skill breaks that rule: its preflight runs `ls` against
`agents/${NAME}-spec/AGENT-SPEC.md`, calls `nemo files filesets get` on
`${NAME}-spec`, and downloads the old filename. Delete all three.

`nemo-ethos` preflight becomes one call:

```bash
nemo agents ethos migrate --name "${NAME}" --dry-run
```

The dry run is read-only, exits 0, and prints one token from a closed set. The
skill branches on the token and never inspects an old path itself:

| Token | Skill action |
| --- | --- |
| `nothing-to-migrate` | Continue with the target-only preflight |
| `already-migrated` | Continue with the target-only preflight |
| `migration-required` | Run the apply, then continue |
| `roll-forward-required` | Run the apply, then continue |
| `source-conflict` | Stop. Show the diverging paths and ask the user to reconcile |
| `target-conflict` | Stop. Show the difference and ask the user to choose |
| `blocked-active-job` | Stop. Name the active job and ask the user to wait or cancel |
| `blocked-resumable-run` | Stop. Name the run directory and ask the user to finish or abandon it |

The apply exits non-zero for the last four tokens. The dry run exits 0 for all
eight, so the skill can explain the state instead of reading an exit code.

Every remaining path in the skill names a target: `agents/${NAME}-ethos/ETHOS.md`
and the `${NAME}-ethos` Fileset. The same rule binds every other lifecycle skill.
No skill file outside the migration guide contains an old literal, which is what
lets the boundary check cover `packages/nemo_platform_ext/**` with no exception.

`nemo-explore` keeps its infer-first, single-review behavior. Only its names,
paths, and handoffs change. `nemo-skill-selection`, `nemo-build-agent`,
`nemo-agent-config`, `nemo-model-selection`, and `nemo-teardown` change names and
paths only. Routing tests use `nemo-ethos`, and no installed `nemo-spec` alias
remains.

## Migration command

`nemo agents ethos migrate` performs the whole mechanical conversion. Add an
`ethos` command group to the `nemo-agents` plugin CLI, next to the existing
`deployments` group.

Options:

```text
--name <agent-name>
--workspace <workspace>
--agents-root <path>
--dry-run
```

### Source authority

The writer contract in `nemo-spec/SKILL.md` calls the Fileset canonical and the
local package a write-through cache, and it resolves a conflict by letting the
Fileset win. That rule fits an interactive edit loop, where the user is present
and can re-pull. Migration is a one-shot move with no undo, so it does not apply
that rule. It never overwrites either copy from the other.

Migration builds the staged package from the union of the old local package and
the old Fileset, keyed by relative path:

| Path found in | Staged content |
| --- | --- |
| The local package only | The local file |
| The Fileset only | The downloaded file |
| Both, with equal bytes | Either copy |
| Both, with different bytes | Nothing. This is a source conflict |

A source conflict stops the command before staging. The report names every
diverging path and the two byte counts. The user reconciles the copies with an
explicit pull or push, then reruns. Neither copy is modified or deleted.

The dry-run report names the source of every staged file, so the user can see
which files came from the Fileset alone.

### Preflight predicates

Two gates depend on live state. Both are defined against values that exist in the
repository, and both must be table-testable.

**Insights active jobs.** Refuse when a job for this agent and workspace has
`source == "insights"` and a status in `_ACTIVE_JOB_STATUSES` from
`plugins/nemo-insights/src/nemo_insights_plugin/controller.py`: `created`,
`pending`, `active`, `cancelling`, `paused`, `pausing`, and `resuming`. Import
that constant. Do not copy the literal list, or the gate drifts from the
controller that owns it. Also refuse when the agent's `AnalysisConfig` has
`status == AnalysisConfigStatus.RUNNING`, which covers a run in flight whose job
record is not yet visible.

**Experimentalist resumable runs.** The runner keeps run state in
`<experiment-dir>/run.json` as an `ExperimentRun`, whose `status` is one of
`running`, `completed`, or `failed`. Candidate records live in
`<experiment-dir>/candidates/`. Mirror the refusal rules in
`experimentalist/runner.py`. A run blocks migration when either holds:

- `run.json` parses, `status` is `running` or `failed`, and the profile's
  strategy sets `supports_resume = True`; or
- `run.json` is absent or unreadable while `candidates/` still holds records,
  which the runner treats as recoverable work on disk.

Migration proceeds when the directory holds no `run.json` and no candidate
records, when `status` is `completed`, or when the strategy sets
`supports_resume = False`. The base class in `experimentalist/roles.py` defaults
to `False`, and `strategies/evolutionary.py` sets `True`.

Test both gates as tables. For Insights, one job per status: the seven active
statuses refuse and every other status proceeds. For Experimentalist, the cross
product of `run.json` status, `supports_resume`, and candidate-record presence.

### State matrix

The command is defined over the presence of four things: the old local package,
the old Fileset, the target local package, and the target Fileset. The table
collapses the two target items into one target-state column, with three values:

- *absent*: neither target exists.
- *complete*: both targets hold the same paths with matching checksums, and the
  target `ETHOS.md` parses.
- *partial*: at least one target exists, but that check fails.

Evaluate the rows in order. The first row that matches wins, so a source conflict
is reported even when a target already exists.

| Old local | Old Fileset | Target state | Outcome |
| --- | --- | --- | --- |
| absent | absent | absent | Nothing to migrate. Report and exit 0 |
| absent | absent | complete | Already migrated. Verify, rewrite any remaining old profile key, exit 0 |
| absent | absent | partial | Roll forward. Re-stage from the target, re-upload, verify, exit 0 |
| present | absent | absent | Migrate from the local package |
| absent | present | absent | Migrate from the Fileset |
| present | present, agreeing | absent | Migrate from the union of both |
| present | present, diverging | any | Source conflict. Stop before staging |
| present | any | complete and equal to staged | Roll forward. Rewrite profiles, verify, delete old state, exit 0 |
| present | any | complete and differing from staged | Target conflict. Stop |
| present | any | partial | Roll forward from the failed step |

Two conflicts are distinct and must report differently. A source conflict is a
disagreement between the two old copies. A target conflict is a disagreement
between the staged output and an existing target.

### Sequence

1. Read the old local package, the old Fileset, the profile files, and the target
   state. Classify the result against the state matrix.
2. Stop on a source conflict or a target conflict.
3. Apply the Insights active-job gate.
4. Apply the Experimentalist resumable-run gate.
5. Stage the union of the two old sources in a temporary directory as
   `<agent-name>-ethos`.
6. Rename the contract file to `ETHOS.md`.
7. Copy every section body and every non-contract file byte for byte. The section
   bodies are the text from each `##` heading to the next one.
8. Rewrite only the two regions that sit before the first `##` heading: the H1
   title line and the leading blockquote banner. The parser discards that region,
   so no validated content changes. In the shipped template these read
   `# Agent Spec: <name>` and a banner that names the old file and the old skill.
9. Scan the staged package for any remaining old literal: the old filename, the
   old package directory name, the old Fileset name, the old profile key, the old
   flag, and the old symbol names. Rewrite rules cover the known positions. Stop
   and list every occurrence that no rewrite rule produced, with its file and line
   number, because it may be prose, a hand-written relative path, an entry in
   `agent.yaml`, or a packaged skill file.
10. Validate the staged `ETHOS.md` with `parse_ethos()`.
11. Create the `<agent-name>-ethos` Fileset and upload every staged file.
12. Verify the upload: every staged path is present and every checksum matches,
    and the uploaded `ETHOS.md` parses. **This is the commit point.**
13. Write the target local package from the staging directory.
14. Rewrite each profile key and path to `ethos`, including
    `optimizer.yaml` to `ethos: .../ETHOS.md`.
15. Verify local files, Fileset files, checksums, non-contract files, refs, and
    profiles.
16. Delete the old local package, then delete the old Fileset.

Steps 2 through 4 are preflight gates. A gate that fails ends the command before
step 5, so the command changes nothing.

On a roll-forward row where no old state remains, there is nothing to stage from
the old sources. The command stages from the target instead, then continues at
step 11. Steps 6 through 9 are skipped, because a target package is already
renamed and already rewritten.

### Commit point and rollback

Step 12 is the commit point: the target Fileset holds a complete, verified copy
under the target name. Before and after that step the command behaves
differently, and the state matrix encodes the difference.

Before the commit point, the command has only added a staging directory and a
partial Fileset. On any failure it deletes both, then exits non-zero and names
the failed step. The old local package, the old Fileset, and every old profile
key stay authoritative and unmodified.

After the commit point there is no rollback. The command rolls forward. Deleting
a verified target Fileset to restore the old name would destroy the only verified
copy at the one moment when both exist, which is the least safe action available.
A rerun repeats steps 13 through 16 until they succeed.

Steps 13 through 16 are ordered so that a crash between any two of them leaves
the target complete and the old state present. The state matrix classifies that
as roll forward, so the rerun finishes the move instead of restarting it.

### Failure behavior

- A dry run reads only. It reports every location the command would read or
  write, plus the state-matrix outcome, and changes nothing.
- A failure before the commit point leaves the old state authoritative.
- A failure after the commit point leaves the target authoritative and rolls
  forward on rerun.
- A rerun is idempotent. Rewriting a profile key that already reads `ethos` is a
  no-op, and re-uploading an identical file leaves the checksum unchanged.
- A rerun that finds only target state runs verification and profile rewrite
  only. It creates nothing, deletes nothing, and never re-creates old state.
- Target output that equals the staged output is accepted.
- Target output that differs from the staged output is a target conflict.
- Two old copies that differ on a shared path are a source conflict.
- There is no `--keep-legacy` option.
- Completed Experimentalist run directories stay historical data. The command
  does not read or rewrite them.

## Legacy-term boundary

Add `tools/lint/ethos_boundary.py` with a `tools/lint/lint-ethos-boundary.sh`
wrapper, matching the shape of the existing `tools/lint/lint-*.sh` scripts.
Register it in the `CHECKS` array in `tools/lint/lint-all.sh` as
`lint-ethos-boundary:tools/lint/lint-ethos-boundary.sh`, so `make lint` and CI
run it. Add a matching local `pre-commit` hook, as
`no-nmp-common-in-plugins` does.

Run it alone with:

```bash
bash tools/lint/lint-ethos-boundary.sh
```

The checker enumerates tracked files with `git ls-files`, so it skips build
output and ignored paths. It rejects these artifact-specific old literals:
`AGENT-SPEC.md`, `AGENT_SPEC`, `AgentSpec`, `agent_spec`, `agent-spec`,
`parse_spec`, `SpecParseError`, and `nemo-spec`.

These paths may contain them:

```text
plugins/nemo-agents/src/nemo_agents_plugin/ethos_migrate.py
plugins/nemo-agents/tests/unit/test_ethos_migrate.py
plugins/nemo-agents/tests/fixtures/ethos_migrate/**
docs/agents/ethos-migration.mdx
docs/superpowers/specs/2026-08-19-ethos-authoritative-rename-design.md
tools/lint/ethos_boundary.py
```

The last two entries are load-bearing. The checker holds the banned literals, and
this record and the migration guide explain the move, so all three must name the
old form.

Unrelated names keep the old substring. Match the longer allowed term first, then
scan for the banned literal, so `EvaluateAgentSpec` never reports as `AgentSpec`.
Each exception is path-scoped. Do not use one broad substring ban.

| Allowed term | Path scope | Why it stays |
| --- | --- | --- |
| `EvaluateAgentSpec` | `plugins/nemo-evaluator/**` | Evaluator input schema, not the contract |
| `nemo_evaluator.jobs.agent_spec` | `plugins/nemo-evaluator/**` | Evaluator module path, not the contract |
| `nemo-agents-spec-v1` | `plugins/nemo-agents/**`, `web/packages/studio/**`, `plugins/nemo-optimization/**` | Format tag of the executable `agent.yaml` |
| `agent-specific` | repository-wide | English adjective |
| `--spec`, `--spec-file`, `BuildSpec` | `plugins/nemo-evaluator/**`, `skills/nemo-evaluator-plugin/**` | Unrelated interfaces |

## Delivery topology

Implement these directly on the PR 1 integration branch:

- the core contract rename;
- the migration command;
- the lifecycle skills;
- the checked-in agent package;
- the documentation, including the migration guide;
- the shared examples;
- the Studio skill actions;
- the generated OpenAPI and CLI reference files;
- the legacy-term boundary check.

The boundary check permits the migration guide to name the old artifact.

Exactly two child PRs branch from PR 1 and target PR 1:

1. Analyst migration support, owned by the Insights team.
2. Experimentalist migration support, owned by the Experimentalist team.

Neither child PR targets `main`. Analyst owns the shared profile resolver that
Experimentalist imports, so the merge order is fixed:

1. Merge Analyst into PR 1.
2. Rebase Experimentalist on the updated PR 1 branch.
3. Verify Experimentalist, then merge it into PR 1.
4. Run the full cross-plugin and migration verification on PR 1.
5. Merge only the completed PR 1 into `main`.

### Analyst scope

Analyst renames these in `plugins/nemo-insights`:

```text
contracts/profile.py: resolve_agent_spec_path()  -> resolve_context_path()
                      _AGENT_SPEC_FILENAMES      -> _CONTEXT_FILENAMES
profile.py:           AnalysisProfile.agent_spec -> .ethos
                      pick_agent_spec()          -> pick_ethos()
preflight.py:         read_agent_spec()          -> read_ethos()
                      check_agent_spec()         -> check_ethos()
cli.py:               --agent-spec               -> --ethos
analyst/agent.py:     AGENT_SPEC_HEADER          -> ETHOS_HEADER
analyst/run.py:       agent_spec parameter       -> ethos
jobs/analyze.py:      AnalyzeSpec.agent_spec     -> AnalyzeSpec.ethos
```

Doctor labels, errors, tests, testbed adapters, the README, the Analyst skill,
and Insights-owned documentation follow.

#### Context-source discovery order

Analyst does not resolve one artifact. It resolves the analysis context document,
and it accepts two unrelated kinds of document. `resolve_context_path()` keeps its
behavior:

1. When the profile sets `ethos`, resolve that path and require it to exist.
2. Otherwise, return the first file that exists from `_CONTEXT_FILENAMES`, in the
   order `ETHOS.md`, then `README.md`.

Step 2 is a discovery order over candidate context sources. It is not an alias
list, not a rename fallback, and not a schema fallback. `README.md` has never
named this artifact, and migration never reads or rewrites a `README.md`. The
boundary check needs no exception for it.

Analyst reads whichever file it finds as raw markdown. Neither file goes through
`parse_ethos()` on this path, so finding `ETHOS.md` here does not mean the
document is schema-valid. Preflight reports the resolved filename, so the user can
see which source was used.

The resolver keeps a neutral name for that reason. Naming it `resolve_ethos_path`,
as the roadmap suggests, would assert that a returned `README.md` is an ETHOS. The
configured profile field stays `ethos`, because that field does name a configured
ETHOS.

### Experimentalist scope

Experimentalist renames these:

- the profile key, the resolver, and the CLI option;
- the prepared input, the context, the seam, and the role fields;
- the backend accessor `get_agent_spec()` to `get_ethos()`;
- the strategy, trace scorer, goal-tree, analyzer, rationalizer, and coder
  parameters and prompts.

Workspace materialization writes `ETHOS.md`. Experimentalist-owned examples,
benchmarks, skill documentation, and tests follow. The examples include the
smoke-agent, terminal-bench, and tau3 profiles.

## Rollout

Old job payloads carry the old field names, which no runtime path accepts after
PR 1. Before rollout, drain or cancel every serialized Insights and
Experimentalist job that uses the old names. Completed historical results stay
readable, and no old payload is replayable.

Run `make vendor-nemo-platform-ext` after any source skill change. Do not
hand-edit the vendored skill copies.

## Acceptance

Migration acceptance cases:

- a dry run lists every local file, Fileset file, and profile file the command
  would read or write, plus the active-job result, the resumable-run result, and
  the state-matrix outcome;
- a normal migration preserves all 13 section bodies;
- the complete local package and the complete Fileset move;
- non-contract files and checksums match after the move;
- profile keys and paths become `ethos`;
- the old package and the old Fileset disappear only after verification;
- a rerun is idempotent;
- a divergent target stops the command;
- an Experimentalist run that can resume stops the command;
- no runtime fallback or alias remains;
- the legacy-term boundary check passes.

Cases added by the source-authority, state-matrix, and commit-point rules:

- every state-matrix row is covered by one test, including the empty row;
- two old copies that differ on a shared path stop the command, and neither copy
  is modified;
- a path present in only one old source reaches the staged package;
- a failure injected before step 12 removes the staging directory and the partial
  Fileset, and leaves the old state authoritative;
- a failure injected after step 12 leaves the target authoritative, and the rerun
  finishes steps 13 through 16;
- a rerun with only target state present writes no file and deletes nothing;
- the Insights gate refuses for each of the seven active statuses and proceeds for
  every other status;
- the Experimentalist gate refuses a resumable run, refuses an unreadable
  `run.json` beside candidate records, and proceeds for a completed run;
- `nemo-ethos` reaches every branch through the dry-run token, and no skill file
  reads an old path.

### Verification

Targeted:

```bash
uv run --frozen pytest plugins/nemo-agents/tests/unit/test_ethos_parse.py -v
make test-package PACKAGE=nemo-agents-plugin
uv run pytest plugins/nemo-insights/tests -v
uv run --frozen pytest plugins/nemo-experimentalist/tests -v
uv run ruff check plugins/nemo-insights plugins/nemo-experimentalist
```

Repository-wide and generated content:

```bash
bash tools/lint/lint-ethos-boundary.sh
uv run ruff check
uv run --frozen ty check
make vendor-nemo-platform-ext
make refresh-openapi
make generate-cli-reference-docs
make docs-check
make docs-broken-links
```

## Relationship to PR 2

PR 2 starts only after PR 1 merges. Its input is an authoritative, unversioned,
13-section `ETHOS.md` at the final local and Fileset locations. PR 2 owns
`schema_version: 1`, the approved intent fields, the strict v1 parser, and the
intent-first interview. It extends `nemo agents ethos migrate` with a
schema-upgrade mode that the absent version key triggers.

PR 1 must not anticipate that work. It adds no version key, no section, and no
interview change.

## Roadmap corrections

- The roadmap names `agents/nemo-studio-copilot-spec/`. The checked-in package
  is `agents/nemo-studio-assistant-spec/`, so PR 1 renames it to
  `agents/nemo-studio-assistant-ethos/` and its `AGENT-SPEC.md` to `ETHOS.md`.
- The roadmap names the Analyst resolver `resolve_ethos_path`. This design uses
  `resolve_context_path`, because the function can return a `README.md` and the
  roadmap name would assert that the returned file is an ETHOS. Behavior and
  discovery order are unchanged.
- The roadmap says migration must preserve semantic content but does not say which
  old copy is the source when the old local package and the old Fileset disagree.
  This design resolves that as a source conflict rather than applying the writer
  contract's "Fileset wins" rule, which exists for an interactive edit loop.
