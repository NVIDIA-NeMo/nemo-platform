---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-discover
description: >-
  Record whether a repository's Harbor evaluations are ready to run, and prove it
  with Harbor's own validators instead of guessing. Finds every repository-owned
  job config, dataset, and task directory, then makes Harbor judge each config:
  schema, job resolution, agent, environment backend, per-task validity, tasks
  Harbor silently dropped, and required host variables. Use when the user wants
  to run an eval suite they did not write, hand a suite to a cheaper model, or
  asks "can I run these evals?", "why won't my Harbor config resolve?", "which
  env vars does this suite need?", "where are the evals in this repo?", or "why
  did Harbor skip my task?". Changes none of your source, and leaves behind
  `.eval-author/discovery.md` so your team and the next model read the verdict
  without Harbor and without discovering again.
triggers:
  - can I run the evals in this repo
  - where are the Harbor evals in this repository
  - why won't my Harbor job config resolve
  - which environment variables does this eval suite need
  - why did Harbor skip one of my tasks
  - check whether this eval suite is ready to run
not-for:
  - eval-author (use for the standard, the boundaries, and to pick a sub-flow)
  - nemo-experimentalist (use to run insight-driven optimization end to end, which drives the Eval Author agent itself)
  - nemo-evaluator (use to run an existing benchmark rather than establish that a Harbor suite is runnable)
compatibility: >-
  Python 3.11 or later. Harbor must be importable by the interpreter that runs the
  script for any finding to be proven; without it the script reports an unproven
  inventory and exits 1. Docker is needed only for the environment backend check.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: discover

The Eval Author discovery pass. Read `eval-author` for the standard this follows,
the shared vocabulary, and the boundaries that apply throughout. In short: Harbor
judges every fact recorded here, and anything Harbor did not judge is marked
unproven and is not evidence.

Three phases, in order. The bundled script runs all three in one invocation.

1. **Probe.** Is Harbor importable by this interpreter?
2. **Inventory.** Which config files, datasets, and task directories does the
   repository own?
3. **Judge.** Only when Harbor is importable: run Harbor's full validation ladder.

Without Harbor, phase 3 cannot run and no claim about runnability is possible. The
report still comes back, every finding marked unproven, with a required failure
naming what to install.

## Before you start

Run the script with the interpreter that has Harbor installed. This is the one step
people get wrong, and getting it wrong voids the whole report.

A `harbor` command on your `PATH` does not mean Harbor is importable by the Python
you are about to run. A repository with its own virtual environment usually needs
that environment's interpreter. Try these in order until one prints a version:

```bash
for py in .venv/bin/python ./venv/bin/python python3; do
  "$py" -c "import harbor, sys; print(sys.executable, harbor.__version__)" 2>/dev/null && break
done
```

Nothing prints a version when Harbor is not installed anywhere. Do not install it
yourself; in the user's repository the missing environment is the finding. Tell
them what you found and ask how they want to proceed.

The report records which mode produced it either way, in `runtime.harbor_importable`
and the top-level `proven` field.

## Step 1: run discovery

Point the script at the repository root, not at a suite directory. It searches for
configs to a depth of four directories and finds datasets at any depth.

```bash
.venv/bin/python <skill_dir>/scripts/discover.py --repo .
```

One JSON object goes to stdout, and `--compact` puts it on one line. The script
writes no files; you save the report in **Step 5**.

The exit code carries the verdict, so check it:

- `0` — every repository-owned config passed every required check
- `1` — a required check failed, Harbor was unavailable, or the path was unusable

**Only run this against a repository you trust.** Validating a config that names an
agent `import_path` imports that module, which executes its top-level code.

## Step 2: read the verdict

Read these four fields before any others.

| Field | What it settles |
|---|---|
| `proven` | Whether Harbor judged this report. When `false`, nothing below is evidence |
| `runnable` | Whether every config passed every required check |
| `run_command` | The exact command to run the suite. Present only when the repository has exactly one config and it is runnable |
| `configs[].runnable` | The per-config verdict, when the repository owns several |

`run_command` is deliberately absent when several configs exist. Picking one for the
user guesses at intent, so ask which suite they mean and build the command from that
config's `path`.

## Step 3: fix what failed

Each check names one rung of Harbor's ladder. Work top to bottom, because a lower
rung's failure often disappears once you fix a higher one.

| Check | What it means and what to do |
|---|---|
| `harbor` | Harbor is not importable by this interpreter. Re-run with the interpreter from **Before you start** |
| `config` | No config file declares a nonempty `datasets` or `tasks` list. Confirm with the user where their suite lives |
| `config-parse` | A config file did not parse. Either PyYAML is missing, which means the wrong interpreter, or the file's YAML is broken. The hint says which |
| `schema` | Harbor rejected the config's shape. The message carries the offending field path |
| `resolution` | Harbor could not turn the config into a job. Usually a `datasets[].path` that does not exist. This fails before any container starts |
| `tasks` | Some resolved directories are not valid Harbor tasks. A task directory needs a parseable `task.toml` and an `environment/` directory, even when the image is prebuilt |
| `coverage` | Harbor silently dropped task directories that exist on disk. Harbor skips unparseable tasks without raising, so treat this as a real defect, not noise |
| `credentials` | Reports the host variables the suite needs. Confirm each one is set before running; a missing key surfaces as a failed trial, not a clear error |
| `agent` | The named built-in agent does not exist, or the `import_path` does not import. Check the message for which |
| `backend` | The environment backend failed preflight. For `docker`, confirm the daemon is running with `docker info` |
| `round-trip` | The Harbor CLI rejected the config file's bytes. This is the weakest rung: it round-trips the schema only, so it can pass while `resolution` fails |
| `harbor-cli` | Advisory. No `harbor` executable exists on `PATH`, so the `round-trip` rung cannot run |
| `compatibility` | The installed Harbor does not expose the resolved task list, so `tasks`, `coverage`, and `credentials` cannot run. Install a Harbor version that exposes it |
| `ethos` | Advisory. `ETHOS.md` is absent or unreadable, so no agent doctrine is defined for this repository |
| `tasks-on-disk` | Advisory, and always unproven. A count of directories holding a `task.toml` |

## Step 4: verify before you report

Discovery changes none of the user's source, so verification means confirming the
report describes the repository they meant:

1. `proven` is `true`. When it is `false`, report only that Harbor is missing.
2. `repo_root` is the repository they named.
3. `configs` lists the suite they care about. An empty list on a repository they
   described as having evals means the configs sit deeper than four directories, or
   declare no `datasets` or `tasks` list.
4. `task_count` is in the range they expect. A count of zero with a passing `tasks`
   check means the config resolves tasks from a registry, not from disk.
Report `proven`, `runnable`, and the failing check names. Never describe a suite as
ready to run while `runnable` is `false`.

## Step 5: save the report

Write the report to `.eval-author/discovery.md`, so the next model and the user's
teammates inherit the findings instead of rerunning discovery to get them back.
Lead with the JSON as front matter, verbatim, then the verdict, the failing checks
by name, and the run command. Never paraphrase a check; its wording is the evidence.

Leave the file in the working tree and say where it is. Committing it is the user's
call, and worth suggesting. Do not touch their `.gitignore`. A rerun replaces the
file rather than merging into it.

## Files in this skill

Provider-specific code sits under `scripts/providers/`, so support for a second
evaluation provider is an added directory rather than a change to the entry point.

| Path | Purpose |
|---|---|
| `scripts/discover.py` | Entry point. Owns phase order, report assembly, and the exit code, and nothing provider-specific |
| `scripts/_checks.py` | The check result contract, ported from the platform so both sides read alike |
| `scripts/providers/harbor/_probe.py` | Detects whether Harbor can judge this repository. Standard library only |
| `scripts/providers/harbor/_inventory.py` | Finds configs, datasets, and task directories. Standard library only |
| `scripts/providers/harbor/_ladder.py` | Runs Harbor's validators. Imported only after the probe reports Harbor available |

The provider directory deliberately sits one level down. A `scripts/harbor/`
directory would be importable as `harbor`, which on a machine without Harbor makes
`find_spec("harbor")` succeed and the probe report an install that is not there.
