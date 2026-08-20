<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ETHOS authoritative rename

Date: 2026-08-19
Status: approved for implementation (PR 1 of the ETHOS two-PR roadmap)

The migration code, its tests and fixtures, the migration guide, the boundary
checker, and this record are the only places that may name the prior artifact.

## Problem

The agent behavior contract has two names. Code, flags, prompts, Filesets, and
documentation use `AGENT-SPEC.md` and `agent_spec`, while the product calls the
artifact ETHOS. The mixed vocabulary increases review effort and blocks schema
work. PR 1 renames only. PR 2 versions the schema.

## Non-goals

PR 1 adds no `schema_version`, section, status, draft, or approval field. It
does not change the `nemo-explore` interview, add spend questions, add Change
Scope presets, or add a machine-readable objective function. It adds no
compatibility alias, runtime fallback, or deprecation shim. Section bodies stay
unchanged.

## Artifact and storage decisions

| Item | Value after PR 1 |
| --- | --- |
| Filename | `ETHOS.md` |
| Local package | `agents/<agent-name>-ethos/` |
| Fileset | `<agent-name>-ethos` |
| Ethos file ref | `<workspace>/<agent-name>-ethos#ETHOS.md` |
| Writer skill | `nemo-ethos` |

The complete package moves. `agent.yaml`, packaged skills, and other relative
artifacts retain their positions. Container staging continues to exclude the
contract file. `agent_config_file_ref()` resolves the renamed Fileset.

The roadmap names `agents/nemo-studio-copilot-spec/`, but the checked-in package
is `agents/nemo-studio-assistant-spec/`. The checked-in package becomes
`agents/nemo-studio-assistant-ethos/`.

## Preserved schema and parser behavior

The front matter retains the required `name`, `created_timestamp`, and `author`
keys. It has no version key. The 13 required `##` headings stay unchanged and
keep this order: Role, Purpose, Scope, Tools, Model, Framework, Harness,
Behavior, Success Criteria, Evaluation Setup, Change Scope, Signals, and Open
Questions.

`parse_ethos()` has the behavior of `parse_spec()`:

1. The YAML front matter fence starts at offset zero.
2. Invalid YAML raises `yaml.YAMLError`. A parsed non-mapping raises `YAML front matter must be a mapping`.
3. `name` and `author` are nonempty strings. `created_timestamp` accepts a `datetime` or a nonempty ISO 8601 string.
4. Headings match `^## +(.+?)\s*$`. Duplicate headings fail, including headings outside the required set.
5. `Framework` is neither empty nor `_(none)_`.
6. Bodies retain raw Markdown except for leading and trailing newlines. Extra `##` sections remain in `sections`.
7. Validation order is fence, mapping, sections, `Framework`, then front matter fields.
8. Validation failures raise `EthosParseError`, a `ValueError` subclass. YAML errors retain their type.
9. `Ethos.role` returns `sections["Role"]`.

The parser does not validate section order, role quality, bullet formats, label
formats, or framework enum values. The `nemo-ethos` skill can provide guidance
for those rules.

## Module and symbol renames

Rename with no import alias or deprecated wrapper:

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

`agent_config_file_ref()` retains its name and returns the renamed Fileset. The
`nemo-agents` CLI, `runner/fabric_artifact_staging.py`, and their entity, CLI,
deletion, and staging tests follow. `parse_ethos(markdown: str) -> Ethos`
remains a pure parser without file access.

## Public interface renames

```text
--agent-spec           -> --ethos
agent_spec:            -> ethos:
AnalyzeSpec.agent_spec -> AnalyzeSpec.ethos
```

The prior forms are not runtime aliases. Child plugin changes rename their
owned profile values. The Platform migrator does not discover or rewrite
developer-managed profiles. Rename `split_agent_spec()` in the Experimentalist
repository helper to `split_agent_source_uri()`. The helper splits
`<url@ref>#<agent_path>`, so its name must not preserve an unrelated meaning.

## Skill rename

```text
packages/nemo_platform_ext/.../skills/nemo-spec/ -> .../skills/nemo-ethos/
references/templates/agent-spec.md               -> references/templates/ethos.md
```

`nemo-ethos` writes the same unversioned 13-section content at the renamed
package and filename. It runs no intent-first interview in PR 1.

Remove the shipped skill's direct reads of the prior local path, Fileset, and
filename. Before writing, `nemo-ethos` can run:

```bash
nemo agents ethos migrate --name <agent-name> --workspace <workspace>
```

The command reports conflicts without changing the source. A missing source and
target is an error. A matching target is a verified no-op. Lifecycle skills
must not name a prior form, which lets the boundary check cover
`packages/nemo_platform_ext/**` without exceptions.

`nemo-explore` retains its infer-first, single-review behavior.
`nemo-skill-selection`, `nemo-build-agent`, `nemo-agent-config`,
`nemo-model-selection`, and `nemo-teardown` change names and paths only.
Routing tests use `nemo-ethos`.

## Migration command

`nemo agents ethos migrate` converts the package and Fileset that the Platform
writes. The `ethos` command group sits beside `deployments` in the
`nemo-agents` CLI.

| Option | Behavior |
| --- | --- |
| `--name` | Identifies one agent name. The value must be one path component. |
| `--workspace` | Selects the Fileset workspace. |
| `--base-url` | Selects the platform API endpoint. |
| `--dry-run` | Assesses the selected mode without writes or deletions. |
| `--cleanup` | Selects cleanup mode. |

The local source is always `agents/<agent-name>-spec/`. The command does not
discover or modify standalone contracts, external profiles, or other
developer-managed repository files.

When `nemo agents create` receives `agent.yaml` from the canonical source
package, it prints the following warning and continues registration:

```text
Warning: This package uses the legacy AGENT-SPEC.md format.
Upgrade to ETHOS.md using:
nemo agents ethos migrate --name AGENT_NAME --workspace WORKSPACE
```

The command substitutes the selected agent name and workspace.
Registration omits `AGENT-SPEC.md` from the target Ethos Fileset and removes
that path when a retained target contains it. The printed migration command can
then add `ETHOS.md` without a target conflict. Registration uploads all other
package artifacts unchanged.

### Additive mode

Without `--cleanup`, the command is additive and rerunnable:

1. Discover a local package, a Fileset, or matching files from both sources.
2. Merge the sources. Files present in one source copy into staging. Shared files must have equal bytes.
3. Rename the contract and rewrite only its identity region.
4. Validate `ETHOS.md` with `parse_ethos()`.
5. Build or complete the local package and Fileset targets.
6. Verify both target manifests.

The command does not modify or delete the source package or source Fileset.
It preserves all other package paths and bytes without scanning their content
for prior terminology.

A partial target can receive missing files when every file it contains matches
the staged output. A target that contains an extra file or different bytes is a
conflict. The command checks both targets before it writes either target.

### Cleanup mode

With `--cleanup`, the command only removes prior artifacts:

1. Require complete, matching local and Fileset targets.
2. Require a valid `ETHOS.md`.
3. Delete the source local package if it remains.
4. Delete the source Fileset if it remains.

Cleanup never performs additive migration. It does not inspect Insights jobs or
Experimentalist runs. The explicit flag is the operator acknowledgment. If an
interruption occurs between deletions, rerun cleanup. Each deletion applies only
when its source artifact remains.

### Dry run and errors

`--dry-run` performs the selected mode's assessment without local writes,
Fileset creation, upload, or deletion. It can download a Fileset to assess it.

Source files that differ at the same relative path cause a conflict before any
write. Invalid agent names, package-root or descendant symlinks, and invalid
target contracts also fail before the command reports success.

## Legacy-term boundary

Add `tools/lint/ethos_boundary.py` and
`tools/lint/lint-ethos-boundary.sh`. Register the check in
`tools/lint/lint-all.sh` and the local `pre-commit` hooks. Run it with:

```bash
bash tools/lint/lint-ethos-boundary.sh
```

The checker scans tracked paths and text. It rejects `AGENT-SPEC.md`,
`AGENT_SPEC`, `AgentSpec`, `agent_spec`, `agent-spec`, `parse_spec`,
`SpecParseError`, `nemo-spec`, `agent spec`, and `Agent Spec`. Only migration
code, migration tests and fixtures, the migration guide, this design, and the
checker can contain those terms. The checker matches denied terms
case-insensitively.

Unrelated names that contain a prior substring remain valid. Match a longer
allowed term before a shorter denied term.

| Allowed terms | Path scope |
| --- | --- |
| `EvaluateAgentSpec`, `nemo_evaluator.jobs.agent_spec`, `--spec`, `--spec-file`, `BuildSpec` | `plugins/nemo-evaluator/**`, `skills/nemo-evaluator-plugin/**`, `plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/**`, `docs/evaluator/**` |
| `nemo-agents-spec-v1` | `plugins/nemo-agents/**`, `plugins/nemo-optimization/**`, `packages/nemo_platform_ext/**/skills/**`, `sdk/python/nemo-platform/**/skills/**`, `web/packages/studio/**`, `agents/**`, `e2e/test_nemo_agents.py`, `docs/agents/**`, `docs/about/release-notes/**` |
| `agent-specific` | `**` |

Occurrences outside these scoped, present-day exemptions prompt review.

## Delivery topology

The PR 1 integration branch carries the core contract rename, migration command,
lifecycle skills, checked-in package, documentation, shared examples, Studio
skill actions, generated OpenAPI and CLI reference files, and the boundary
check.

Two child PRs branch from PR 1 and target PR 1: Analyst migration support,
owned by the Insights team, and Experimentalist migration support. Neither
targets `main`. Analyst owns the profile resolver that Experimentalist imports.
Merge them in this order:

1. Merge Analyst into PR 1.
2. Rebase Experimentalist on the updated PR 1 branch.
3. Verify and merge Experimentalist into PR 1.
4. Run cross-plugin and migration verification on PR 1.
5. Merge the completed PR 1 into `main`.

### Analyst scope

Analyst renames the profile key, resolver, CLI option, header, parameters, and
`AnalyzeSpec.agent_spec` field to their Ethos forms. It preserves the existing
profile resolution and README fallback behavior. It adds no validation,
labeling, or other behavior.

### Experimentalist scope

Experimentalist renames the profile key, resolver, CLI option, prepared input,
context, seam, role fields, backend accessor, strategy fields, and prompts.
Workspace materialization writes `ETHOS.md`. Examples, benchmarks, skill
documentation, tests, and smoke-agent profiles follow.

## Acceptance

- Additive migration preserves all 13 section bodies and the complete source package and Fileset.
- Source-only files reach the staged package. Divergent shared source files leave artifacts unchanged.
- Compatible partial local and Fileset targets receive missing files. Extra or divergent target files fail before a target write.
- Cleanup requires matching valid targets. A cleanup rerun completes after either deletion.
- Dry runs write no local files or Filesets.
- The CLI exposes `--cleanup` and omits `--agents-root`, `--profile`, and `--experiment-dir`.
- Registration of a canonical source package prints the migration command and otherwise continues unchanged.
- `nemo-ethos` handles migration results through the exit status. No runtime alias remains, and the boundary check passes.

## Verification

```bash
uv run --frozen pytest plugins/nemo-agents/tests/unit/test_ethos_parse.py -v
uv run --frozen pytest plugins/nemo-agents/tests/unit/test_ethos_migrate.py -q
make test-package PACKAGE=nemo-agents-plugin
uv run pytest plugins/nemo-insights/tests -v
uv run --frozen pytest plugins/nemo-experimentalist/tests -v
uv run ruff check plugins/nemo-insights plugins/nemo-experimentalist
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

PR 2 starts after PR 1 merges. Its input is an authoritative, unversioned,
13-section `ETHOS.md` at the final locations. PR 2 owns `schema_version: 1`,
the approved intent fields, the strict v1 parser, and the intent-first
interview. It adds schema-upgrade behavior to `nemo agents ethos migrate` when
the version key is absent. PR 1 does not anticipate this behavior.
