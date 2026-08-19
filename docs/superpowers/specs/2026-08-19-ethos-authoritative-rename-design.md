<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ETHOS authoritative rename

Date: 2026-08-19  
Status: approved for implementation (PR 1 of the ETHOS two-PR roadmap)

The migration code, its tests and fixtures, the migration guide, the boundary
checker, and this record are the only places that may name the old artifact.

## Problem

The agent behavior contract has two names. Code, flags, prompts, Filesets, and
documentation use `AGENT-SPEC.md` and `agent_spec`, while the product calls the
artifact ETHOS. The mixed vocabulary costs review time and blocks the schema work.
One change that both renames the artifact and versions its schema is too large to
review, so PR 1 renames only.

PR 1 therefore moves every artifact-specific path, symbol, flag, and field to `ethos`,
keeps the unversioned 13-section schema and the parser behavior unchanged, ships one
command that migrates local packages, Filesets, and profiles, and confines the old
vocabulary to a boundary that a repository check enforces.

## Non-goals

PR 1 adds no `schema_version` or other version field, no additional section such as
Vision, Constraints, or Priorities, and no status, draft, or approval field. It does not
change the `nemo-explore` interview, add automated spend questions, add Change Scope
presets, or add a machine-readable objective function. It adds no compatibility alias,
runtime fallback, or deprecation shim, and it leaves existing section bodies untouched.

## Artifact and storage decisions

| Item | Value after PR 1 |
| --- | --- |
| Filename | `ETHOS.md` |
| Local package | `agents/<agent-name>-ethos/` |
| Fileset | `<agent-name>-ethos` |
| Ethos file ref | `<workspace>/<agent-name>-ethos#ETHOS.md` |
| Writer skill | `nemo-ethos` |

The complete package moves: `agent.yaml`, packaged skills, and every other relative
artifact keep their positions inside it, and container staging keeps excluding the
contract file. `agent_config_file_ref()` resolves into the renamed Fileset.

## Preserved schema and parser behavior

The front matter keeps exactly three required keys, `name`, `created_timestamp`, and
`author`, and no version key. The 13 required `##` headings stay unchanged, in this
order: Role, Purpose, Scope, Tools, Model, Framework, Harness, Behavior, Success
Criteria, Evaluation Setup, Change Scope, Signals, and Open Questions.

`parse_ethos()` keeps the behavior of `parse_spec()`. This is the complete validation
set, transcribed from `spec_parse.py`:

1. The `---` fence match is anchored at offset 0, so a leading blank line, comment, or
   heading fails with `missing YAML front matter`.
2. Malformed YAML is not caught: `yaml.safe_load` raises `yaml.YAMLError`, which
   propagates unchanged. Only a parsed non-mapping fails with
   `YAML front matter must be a mapping`. An empty block becomes `{}`.
3. `name` and `author` must each be a non-empty string, and the parser strips both.
   Extra front-matter keys are ignored.
4. `created_timestamp` accepts a `datetime` as-is, or a non-empty string through
   `datetime.fromisoformat` after `str.replace` substitutes `+00:00` for every `Z`.
   Anything else fails as required or as not ISO 8601.
5. Headings match `^## +(.+?)\s*$` in multiline mode, so `##Role` is body text.
6. A repeated heading fails with `duplicate section: ## <title>`, for every `##` heading
   and not only the 13 required ones. A missing required title fails with
   `missing section: ## <title>`.
7. `Framework`, once stripped, must be neither empty nor `_(none)_`.
8. Bodies keep raw markdown. The parser strips leading and trailing newlines only, so
   inner blank lines, indentation, and `###` subheadings survive. Extra `##` sections
   are kept in `sections`.
9. Text between the front matter and the first `##` heading is discarded, so the H1
   title and the template banner never reach `sections`.
10. Validation order is fixed: fence, mapping type, section split, required sections,
    Framework, then the three fields. A document missing both a section and `name`
    reports the section first.
11. Validation failures raise `SpecParseError`, which becomes `EthosParseError` and stays
    a `ValueError` subclass. The `yaml.YAMLError` in item 2 is the one failure of another
    type.
12. `Ethos.role` returns `sections["Role"]`.

The parser checks nothing else: not section order, role quality, bullet format, label
format, or framework enum values. `nemo-spec/SKILL.md` claims the validator rejects a
vague role and that the parser checks role quality. Both claims are false and must be
corrected; those rules stay skill guidance.

## Module and symbol renames

Rename with no import alias and no deprecated wrapper:

```text
plugins/nemo-agents/src/nemo_agents_plugin/spec.py        -> ethos.py
plugins/nemo-agents/src/nemo_agents_plugin/spec_parse.py  -> ethos_parse.py
plugins/nemo-agents/tests/unit/test_spec_parse.py         -> test_ethos_parse.py

AGENT_SPEC_SECTION_TITLES   -> ETHOS_SECTION_TITLES
AgentSpec                   -> Ethos
SpecParseError              -> EthosParseError
parse_spec                  -> parse_ethos

entities.py:
AGENT_SPEC_FILENAME         -> ETHOS_FILENAME = "ETHOS.md"
AGENT_SPEC_LOCAL_ROOT       -> ETHOS_LOCAL_ROOT = "agents"
MAX_AGENT_SPEC_STAGED_BYTES -> MAX_ETHOS_STAGED_BYTES
MAX_AGENT_SPEC_STAGED_FILES -> MAX_ETHOS_STAGED_FILES
agent_spec_fileset_name()   -> ethos_fileset_name()
agent_spec_local_path()     -> ethos_local_path()
agent_spec_file_ref()       -> ethos_file_ref()
```

`agent_config_file_ref()` keeps its name and returns the renamed Fileset. The
`nemo-agents` CLI, `runner/fabric_artifact_staging.py`, and their entity, CLI, deletion,
and staging tests follow. `parse_ethos(markdown: str) -> Ethos` stays a pure parser with
no file or network access.

## Public interface renames

```text
--agent-spec           -> --ethos
agent_spec:            -> ethos:
AnalyzeSpec.agent_spec -> AnalyzeSpec.ethos
```

The old forms are not runtime aliases, and only the migration module reads one, to
rewrite it. Also rename the unrelated Git-source helper `split_agent_spec()` in
`plugins/nemo-experimentalist/.../experimentalist/components/repository.py` to
`split_agent_source_uri()`. It splits `<url@ref>#<agent_path>`, so the old phrase must
not survive under a second meaning.

## Skill rename

```text
packages/nemo_platform_ext/.../skills/nemo-spec/ -> .../skills/nemo-ethos/
references/templates/agent-spec.md               -> references/templates/ethos.md
```

`nemo-ethos` writes the same unversioned 13-section content at the renamed package and
filename, and runs no intent-first interview in PR 1.

The shipped skill preflight reads old names directly: `ls` on the old path,
`nemo files filesets get` on the old Fileset, and a download of the old filename. Delete all
three, because migration owns every old-name lookup. Instead, `nemo-ethos` may invoke
`nemo agents ethos migrate --name --workspace` before writing. The command is idempotent and
safe in any state: no legacy source and no target is a read-only no-op, a complete target
alone is a verified no-op, and a conflict or active work exits non-zero with a human-readable
error that the skill shows unchanged. There is no machine-readable output contract, and no
lifecycle skill names an old form, which lets the boundary check cover
`packages/nemo_platform_ext/**` with no exception.

`nemo-explore` keeps its infer-first, single-review behavior. `nemo-skill-selection`,
`nemo-build-agent`, `nemo-agent-config`, `nemo-model-selection`, and `nemo-teardown`
change names and paths only. Routing tests use `nemo-ethos`, and no `nemo-spec` alias
remains.

## Migration command

`nemo agents ethos migrate` performs the whole mechanical conversion. Add an `ethos` command
group to the `nemo-agents` plugin CLI, next to the existing `deployments` group. Options:
`--name`, `--workspace`, `--agents-root`, `--dry-run`, and a repeatable `--experiment-dir`.

### Legacy sources

Either old copy is a valid legacy source: the old local package, the old Fileset, or
both. Staging merges them by relative path. A path in one source only is copied from that
source, and a shared path with equal bytes is copied once. A shared path with different
bytes is a source conflict: the command stops before any write and reports each diverging
path. The writer contract in `nemo-spec/SKILL.md` resolves such a disagreement by letting
the Fileset win. Migration does not, because it is a one-shot move and picking a side
would discard the other copy with no undo.

### Preflight gates

**Insights jobs.** Query the generic Platform Jobs API for the workspace. Refuse when a job
has `source == "insights"`, a nonterminal status, and `job.spec["agent"]` equal to the agent
name. The job response model carries `workspace`, `source`, `spec`, and `status`, and
`AnalyzeSpec.agent` populates `spec["agent"]`. Use
`PlatformJobStatus` from
`packages/nemo_platform_plugin/src/nemo_platform_plugin/jobs/schemas.py`, whose
terminal statuses are `completed`, `error`, and `cancelled`, and call `is_terminal()`
rather than listing statuses inline. Do not import a private Insights constant, and do
not add a `nemo-agents` dependency on `nemo-insights`.

**Experimentalist runs.** State lives under `<experiment-dir>/eval-and-optimize/`:
`run.json` holds an `ExperimentRun` whose `status` is `running`, `completed`, or
`failed`, and candidate records are `candidates/*.json`. Mirror the refusal rules in
`experimentalist/runner.py`. A directory blocks migration in two cases. The first is a
`run.json` that parses with `status` of `running` or `failed` while the profile's strategy
sets `supports_resume = True`. The second is a missing or unreadable `run.json` beside
surviving `candidates/*.json`, which the runner treats as recoverable work on disk.

Check directories derived from each affected profile, at
`<profile-dir>/.nemo-optimizer/experiments/*`, which is the default the Experimentalist CLI
reserves, and every path passed with `--experiment-dir`. A run started with an explicit
`--experiment-dir` outside that tree is not discoverable: the command performs no global
filesystem scan and must not claim one. Rollout drains those runs or passes each directory.

### State table

Legacy state means either legacy source is present. A target is *complete* only when the final
local package and the final Fileset carry the same paths with matching checksums, the target
`ETHOS.md` parses, and every affected profile key and path reads `ethos`. A package-complete
target with an unconverted profile is therefore incomplete, so the command resumes profile
conversion instead of reporting success.

| Packages | Profiles | Outcome |
| --- | --- | --- |
| Journal present | any | Recover first, then re-evaluate |
| None | converted or absent | Nothing to migrate. Exit 0 |
| None | old references | Conflict. Name each stale profile |
| Legacy, no target | any | Migrate |
| Legacy plus a target equal to the staged output | any | Finish the move: convert profiles, verify, delete legacy |
| Legacy plus a partial or divergent target | any | Conflict. Stop |
| Complete target only | old references | Resume profile conversion, then verify |
| Complete target only | converted | Idempotent success. Exit 0 |
| Partial or divergent target only, no journal | any | Conflict. Stop |

### Apply as a compensating transaction

**Binding rule: every controlled apply failure leaves the old local package, the
old Fileset, and the old profile keys authoritative.**

The journal lives outside the repository, at
`nmp_user_data_dir() / "ethos-migrations" / <workspace>-<agent>.json`. Import
`nmp_user_data_dir` from `nemo_platform_plugin.config`, because plugins must not import
`nmp_common`. `--agents-root` never moves the journal, so a crashed migration cannot land
in a user's commit. The journal records the workspace, the staged checksums, each
attempted and completed step, the backup locations, and whether this transaction created
the target Fileset. Hold an exclusive lock per workspace and agent for the whole
transaction, so two migrations cannot interleave on one journal, and write every journal
update atomically: write a temporary file, `fsync` it, then replace the journal.

1. Take the lock and write the journal, then stage the merged legacy sources in a
   temporary directory.
2. Rename the contract file to `ETHOS.md`. Copy every section body and every
   non-contract file byte for byte.
3. Rewrite only the region before the first `##` heading: the H1 title line and the
   leading blockquote banner, which in the shipped template read
   `# Agent Spec: <name>` and a banner naming the old file and skill. The parser
   discards that region, so no validated content changes.
4. Scan the staged package for any remaining old literal. Stop and list, with file and line,
   every occurrence no rewrite rule produced: prose, a hand-written relative path, an
   `agent.yaml` entry, or a packaged skill file.
5. Validate the staged `ETHOS.md` with `parse_ethos()`.
6. Copy both legacy sources into the journal directory as backups, then verify each backup by
   checksum.
7. Upload the staged files to the final `<agent-name>-ethos` Fileset, recording in the
   journal whether this transaction created it. The old Fileset stays authoritative
   throughout. Never modify a pre-existing target Fileset: accept it when every path and
   checksum already equals the staged output, and otherwise stop before any write.
8. Write the target local package, then rewrite each affected profile key and path to
   `ethos`, including `optimizer.yaml` to `ethos: .../ETHOS.md`.
9. Verify the target local package, the target Fileset, and every profile write.
10. Delete the old local package, then delete the old Fileset.
11. Commit: step 9 verified and both deletions in step 10 completed. Only now is the
    target authoritative. Delete the backups and the journal, then release the lock.

The gates run before step 1, and steps 1 through 6 change nothing outside the temporary
directory and the journal directory.

On any error before step 11, compensate from the journal and the backups: undo the target
local package and the profile writes, delete the target Fileset only when the journal
records that this transaction created it, restore any old item already deleted, and remove
the staging directory. Verify the restored profiles as well as the restored packages, then
remove the journal, release the lock, exit non-zero, and name the failed step.

If compensation itself fails, keep the journal and the verified backups, report that
recovery is required, and exit non-zero. The next run must recover before new work.

On restart with a journal present, recover first. When both legacy sources are gone and
the final target verifies, including its profiles, the transaction reached step 11 and
only cleanup remains: delete the backups and the journal, then report success. Otherwise
compensate as above and report the failure the journal recorded.

A dry run reads only: it reports the state-table outcome, each gate result, and every
location the command would read or write. Reruns are idempotent, because rewriting a
profile key that already reads `ethos` is a no-op and re-uploading an identical file
leaves the checksum unchanged. There is no `--keep-legacy` option. Completed
Experimentalist run directories stay historical data, and the command neither reads nor
rewrites them.

## Legacy-term boundary

Add `tools/lint/ethos_boundary.py` with a `tools/lint/lint-ethos-boundary.sh` wrapper,
matching the existing `tools/lint/lint-*.sh` scripts. Register it in the `scripts` array
in `tools/lint/lint-all.sh` as `lint-ethos-boundary:tools/lint/lint-ethos-boundary.sh`,
and add it to `is_no_fix_lint` in the same file, because it has no auto-fix. Add a
matching local `pre-commit` hook, as `no-nmp-common-in-plugins` has. Run it alone with
`bash tools/lint/lint-ethos-boundary.sh`.

The checker enumerates tracked files with `git ls-files` and scans two things: the
tracked path names and the tracked text contents. Path-name scanning catches a directory
or file that still carries the old name after its contents are clean. It rejects
`AGENT-SPEC.md`, `AGENT_SPEC`, `AgentSpec`, `agent_spec`, `agent-spec`, `parse_spec`,
`SpecParseError`, `nemo-spec`, and the prose forms `agent spec` and `Agent Spec`, matched
case-insensitively. These paths may contain them:

```text
plugins/nemo-agents/src/nemo_agents_plugin/ethos_migrate.py
plugins/nemo-agents/tests/unit/test_ethos_migrate.py
plugins/nemo-agents/tests/fixtures/ethos_migrate/**
docs/agents/ethos-migration.mdx
docs/superpowers/specs/2026-08-19-ethos-authoritative-rename-design.md
tools/lint/ethos_boundary.py
```

Unrelated names keep the old substring. Match the longer allowed term first, so
`EvaluateAgentSpec` never reports as `AgentSpec`. Never use one broad substring ban, and
path-scope every exception.

| Allowed term | Path scope |
| --- | --- |
| `EvaluateAgentSpec`, `nemo_evaluator.jobs.agent_spec`, `--spec`, `--spec-file`, `BuildSpec` | `plugins/nemo-evaluator/**`, `skills/nemo-evaluator-plugin/**`, `plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/**`, `docs/evaluator/**` |
| `nemo-agents-spec-v1` | `plugins/nemo-agents/**`, `plugins/nemo-optimization/**`, `packages/nemo_platform_ext/**/skills/**`, `sdk/python/nemo-platform/**/skills/**`, `web/packages/studio/**`, `agents/**`, `e2e/test_nemo_agents.py`, `docs/agents/**`, `docs/about/release-notes/**` |
| `agent-specific` | `**` |

The nine `nemo-agents-spec-v1` scopes are the directories holding that format tag today, so
an occurrence outside them is a review prompt rather than an automatic pass.

## Delivery topology

Implement these directly on the PR 1 integration branch: the core contract rename, the
migration command, the lifecycle skills, the checked-in agent package, the docs including the
migration guide, the shared examples, the Studio skill actions, the generated OpenAPI and CLI
reference files, and the boundary check.

Exactly two child PRs branch from PR 1 and target PR 1: Analyst migration support, owned
by the Insights team, and Experimentalist migration support. Neither targets `main`.
Analyst owns the shared profile resolver that Experimentalist imports, so the merge order
is fixed:

1. Merge Analyst into PR 1.
2. Rebase Experimentalist on the updated PR 1 branch.
3. Verify Experimentalist, then merge it into PR 1.
4. Run the full cross-plugin and migration verification on PR 1.
5. Merge only the completed PR 1 into `main`.

### Analyst scope

```text
contracts/profile.py: resolve_agent_spec_path()  -> resolve_ethos_path()
profile.py:           AnalysisProfile.agent_spec -> .ethos
                      pick_agent_spec()          -> pick_ethos()
preflight.py:         read_agent_spec()          -> read_ethos()
                      check_agent_spec()         -> check_ethos()
cli.py:               --agent-spec               -> --ethos
analyst/agent.py:     AGENT_SPEC_HEADER          -> ETHOS_HEADER
analyst/run.py:       agent_spec parameter       -> ethos
jobs/analyze.py:      AnalyzeSpec.agent_spec     -> AnalyzeSpec.ethos
```

Doctor labels, errors, tests, testbed adapters, and Insights docs follow.

**Split the README fallback out of the Ethos path.** One resolver returns either
`ETHOS.md` or `README.md` today, and its result flows through symbols named for the
contract. After the split, `resolve_ethos_path()`, `pick_ethos()`, `read_ethos()`,
`check_ethos()`, and `ETHOS_HEADER` only ever receive the configured ethos path or a
conventional `ETHOS.md`.

`AnalyzeSpec` gains no field. The only payload change is the rename above, and `ethos`
carries Ethos content alone. When no Ethos exists, the Analyst worker discovers
`README.md` from the checkout it already has through an internal helper, and an internal
README header formats that content. No new field enters any public job or profile schema,
and no discovered README path is serialized.

The effective discovery order stays `ETHOS.md`, then `README.md`, which is repository
context: not an old artifact name, not an alias, and not a schema fallback. Migration
never reads or rewrites one, so the boundary needs no exception for it. Neither file goes
through `parse_ethos()` here, so finding `ETHOS.md` does not imply schema validity.

### Experimentalist scope

Experimentalist renames the profile key, the resolver, the CLI option, the prepared input,
the context, the seam, the role fields, the backend accessor `get_agent_spec()` to
`get_ethos()`, and the strategy, trace scorer, goal-tree, analyzer, rationalizer, and
coder parameters and prompts. Workspace materialization writes `ETHOS.md`. Its examples,
benchmarks, skill docs, and tests follow, including the smoke-agent, terminal-bench, and
tau3 profiles.

## Rollout

Old job payloads carry the old field names, which no runtime path accepts after PR 1. Before
rollout, drain or cancel every serialized Insights and Experimentalist job using the old
names, and drain every Experimentalist run held in a custom experiment directory the
command cannot discover. Run `make vendor-nemo-platform-ext` after any source skill change,
and never hand-edit the vendored copies.

## Acceptance

- The dry run reports the state-table outcome, both gate results, and every location the
  command reads or writes.
- Every state-table row has a case, including the empty row and the journal row.
- A normal migration keeps all 13 section bodies, moves the complete local package and
  Fileset, keeps non-contract files and checksums equal, and converts every profile key
  and path to `ethos`.
- A path in one legacy source only reaches the staged package, and a shared path that
  differs stops the command with neither copy modified.
- A failure injected at each step before step 11, including between the two deletions in step
  10, restores the old package, Fileset, and profile keys, and deletes the target Fileset only
  when the journal records that this transaction created it.
- A pre-existing target Fileset that differs stops the command before any write and survives
  unchanged. A failed compensation keeps the journal and backups and reports that recovery is
  required.
- A restart whose journal shows the legacy sources gone and the target and its profiles
  verified finishes cleanup, and any other journal restores the old state.
- A complete target with an unconverted profile resumes conversion instead of reporting
  success.
- The Insights gate refuses a nonterminal job whose `spec["agent"]` matches, and proceeds for
  the three terminal statuses.
- The Experimentalist gate refuses a resumable run, refuses an unreadable `run.json` beside
  candidate records, proceeds for a completed run, and checks both profile-derived and
  `--experiment-dir` directories.
- `nemo-ethos` reaches every branch through the exit status, no skill file reads an old path,
  no runtime fallback or alias remains, and the boundary check passes.

### Verification

```bash
# Targeted
uv run --frozen pytest plugins/nemo-agents/tests/unit/test_ethos_parse.py -v
make test-package PACKAGE=nemo-agents-plugin
uv run pytest plugins/nemo-insights/tests -v
uv run --frozen pytest plugins/nemo-experimentalist/tests -v
uv run ruff check plugins/nemo-insights plugins/nemo-experimentalist
# Repository-wide and generated content
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

PR 2 starts only after PR 1 merges. Its input is an authoritative, unversioned, 13-section
`ETHOS.md` at the final locations. PR 2 owns `schema_version: 1`, the approved intent
fields, the strict v1 parser, and the intent-first interview, and it extends
`nemo agents ethos migrate` with a schema-upgrade mode that the absent version key
triggers. PR 1 must not anticipate any of it.

## Roadmap correction

The roadmap names `agents/nemo-studio-copilot-spec/`. The checked-in package is
`agents/nemo-studio-assistant-spec/`, so PR 1 renames it to
`agents/nemo-studio-assistant-ethos/` and its `AGENT-SPEC.md` to `ETHOS.md`.
