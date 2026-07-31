<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Eval Author

> **Active development. Not intended for external use.**
>
> This plugin is incomplete and its interfaces will change without notice. It also
> runs code from the repository you point it at: validating a config imports that
> repository's agent module into the running process, which executes that module's
> top level. Treat pointing Eval Author at a repository as equivalent to running that
> repository's code yourself, and only do it for code you already trust. Sandboxing is
> not implemented yet.

The Eval Author plugin is a NeMo OO Agent specialized in auditing and improving the
eval suite of a target agent.

It turns an Experimentalist Insight and its production trace refs into
evaluator dataset changes, creating or augmenting regression signals that
capture the failure mode before optimization begins.

This package hard-depends on Experimentalist for evaluator, staging, and trace
helpers. Experimentalist insight mode imports and runs this Eval Author before
beginning optimization.

## Current state

`nemo eval-author discover` is the only implemented command. It answers whether
Harbor can run a repository's evals and records the answer.

The command assembles a candidate Harbor `JobConfig` from the strongest source
the repository offers: a Harbor config file it already maintains, a `config.json`
from a prior job Harbor resolved and ran, an Experimentalist `optimizer.yaml`
profile plus the agent wrapper, or the Harbor task directory layout alone.

It validates that candidate through a ladder of Harbor's own calls rather than
reimplemented rules: schema, job resolution, task validity and coverage,
required host variables, the agent class, the environment backend, and a round
trip of the persisted bytes through `harbor job start --print-config`.
[`discovery/validate.py`](../discovery/validate.py) names the Harbor API behind
each rung. Findings that Harbor returned carry a `harbor_call`; the one check
that reads the repository directly — whether each test script names a reward
file — carries none and can only warn, because a script that builds the path in
a variable is indistinguishable from one that writes nothing.

The result is recorded to the `nemo-eval-author` fileset as
`<agent>/discovery.md`. A `<agent>/harbor-job.yaml` is published alongside the
report only when discovery authored the config; when the repository maintains
its own valid config file, the report points at that file instead. Nothing is
written into the repository under inspection.

Every run revalidates from scratch. The report is a record of what was true when
it was written, not a cache that a later run consults.

Exit code 0 means a config was validated and recorded. Every other outcome exits
non-zero, including a config Harbor accepted but that could not be uploaded,
which is what makes the command usable as a gate.

`discover` takes these flags:

- `--repo`: agent repository to inspect. Defaults to the current directory.
- `--agent`: name the artifacts are stored under. Defaults to the agent named in
  `optimizer.yaml`, else a slug of the directory name.
- `--dry-run`: print the findings and the config without uploading anything.

There are no flags for platform state. The workspace and cluster come from the
active `nemo` context, `NMP_WORKSPACE` still overrides the workspace, and the
Harbor environment backend comes from the repository's own config or Harbor's
default.

The other verbs are registered in [`cli.py`](../cli.py) so the command tree is
discoverable. Each one exits non-zero with a not-implemented message.

## Planned commands

- `nemo eval-author audit`: report coverage gaps in an existing Harbor suite
  against `ETHOS.md`, without changing the suite.
- `nemo eval-author propose`: draft reviewable Harbor tasks and verifier patches
  for the gaps the audit found.
- `nemo eval-author run`: run `discover`, `audit`, and `propose` as one pipeline.
- `nemo eval-author doctor`: check the credentials, platform access, and runtime
  the other commands need.
