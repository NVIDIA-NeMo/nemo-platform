<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ETHOS authoritative rename

Date: 2026-08-19  
Status: approved for implementation (PR 1 of the ETHOS two-PR roadmap)

This record, the migration code, the migration tests and fixtures, and the
migration guide are the only places that may name the old artifact. Every other
file moves to `ethos`.

## Problem

The agent behavior contract has two names. Code, flags, prompts, Filesets, and
documentation say `AGENT-SPEC.md` or `agent_spec`. The product says ETHOS. The
mixed vocabulary costs the `nemo-agents`, Analyst, and Experimentalist teams
review time, and it blocks the schema work.

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

`parse_ethos()` keeps the exact behavior of `parse_spec()`:

- require front matter and the three fields;
- require every heading;
- reject duplicate `##` headings;
- reject an empty or `_(none)_` Framework section;
- return raw markdown section bodies;
- accept extra front-matter keys and extra sections;
- enforce no section order, role quality, bullet format, or framework enum.

Correct the skill text that claims the parser rejects a vague role. Role quality
stays skill guidance.

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
13-section schema. It reads no file and writes no file.

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
package and filename. When it finds an old package, it invokes
`nemo agents ethos migrate`. It runs no intent-first interview in PR 1.

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

### Sequence

1. Discover the old local package, the old Fileset, the profile references, and
   the target state.
2. Stop when an old package and a target package both exist with different
   content.
3. Refuse while relevant Insights jobs are queued or active.
4. Refuse while an Experimentalist run can still resume under the old contract.
   The user must finish or abandon that run first.
5. Stage a copy of the complete local package as `<agent-name>-ethos`.
6. Rename the contract file to `ETHOS.md`.
7. Preserve every semantic section body and every non-contract artifact
   unchanged.
8. Rewrite contract-identity scaffolding only, such as the standard H1 and the
   template banner.
9. Scan the staged package for unresolved artifact-specific legacy references.
   Stop and report each nonstandard reference that needs human review.
10. Validate the staged markdown with `parse_ethos()`.
11. Create and upload the complete `<agent-name>-ethos` Fileset.
12. Rewrite `optimizer.yaml` from the old key and path to
    `ethos: .../ETHOS.md`.
13. Verify local files, remote files, checksums, non-contract artifacts, refs,
    and profiles.
14. Delete the old local package and the old Fileset only after every
    verification passes.

Steps 2 through 4 are preflight gates. A gate that fails ends the command before
step 5, so no state changes.

### Failure behavior

- A dry run reads only. It reports the same touchpoints and changes nothing.
- A failed apply leaves the old state authoritative.
- A rerun is idempotent.
- Target output that matches the staged output is accepted.
- Target output that differs from the staged output is a conflict.
- There is no `--keep-legacy` option.
- Completed Experimentalist run directories stay historical data. The command
  does not rewrite them.

## Legacy-term boundary

Add a repository check that rejects artifact-specific old terms outside these
paths:

- the migration module;
- migration tests and fixtures;
- the migration guide and this design record.

The check uses path-scoped allowlists for unrelated names that keep the old
substring. Do not use one broad substring ban.

| Allowed term | Why it stays |
| --- | --- |
| `EvaluateAgentSpec` and evaluator job models | Evaluator input schema, not the contract |
| `nemo_evaluator.jobs.agent_spec` | Evaluator module path, not the contract |
| `nemo-agents-spec-v1` | Format tag of the executable `agent.yaml` |
| `agent-specific` | English adjective |
| `--spec`, `--spec-file`, `BuildSpec`, evaluator builders | Unrelated interfaces |

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
contracts/profile.py: resolve_agent_spec_path() -> resolve_ethos_path()
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

Analyst keeps the fallback order `ETHOS.md`, then `README.md`. `README.md` stays
unvalidated analysis context. No text may describe it as a schema-compliant
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

- a dry run reports every local, Fileset, profile, active-job, active-run, and
  conflict touchpoint;
- a normal migration preserves all 13 section bodies;
- the complete local package and the complete Fileset move;
- non-contract artifacts and checksums match after the move;
- profile keys and paths become `ethos`;
- the old package and the old Fileset disappear only after verification;
- a rerun is idempotent;
- a divergent target stops the command;
- an Experimentalist run that can resume stops the command;
- no runtime fallback or alias remains;
- the legacy-term boundary check passes.

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
