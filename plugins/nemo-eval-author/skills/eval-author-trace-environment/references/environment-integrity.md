<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Environment integrity protocol

Apply this protocol to every candidate before finalization.

## Network isolation

In addition to the separate no-network verifier contract, require the agent
environment to set `[environment].network_mode = "no-network"`. A step-local
agent environment may inherit that setting or repeat `network_mode =
"no-network"`; it must never enable public networking. Resolve and vendor the
complete build and runtime dependency closure before grading.
This is an authoring requirement, not a claim that the static helper verifies
the complete dependency closure.

## Reproducibility manifest

Record the exact task tree before running Harbor:

```bash
python <skill_dir>/scripts/trace_environment.py record-reproducibility \
  --task-dir <task-dir>
```

The manifest hashes every task path, file byte, directory, and executable bit.
It records a declared source revision, Dockerfile base images, external
`COPY --from` and `RUN --mount=from=...` image dependencies, configured agent,
verifier and step `docker_image` references, network modes,
and one image-reference state: `local_only`, `image_pinned_recipe`, or
`immutable_image`. `image_pinned_recipe` means the agent Dockerfile exists
and every inventoried external image is pinned by digest. Local named or numeric
build stages are distinguished from external images. Unresolved variable-based
references keep the task `local_only`. A configured agent image is immutable
only when its reference contains a SHA-256 digest and all inventoried image
dependencies are immutable. Use Harbor's `docker_image` field, not `image`.
These states describe image pinning only. The manifest and public result
explicitly report `dependency_closure: "unverified"`: arbitrary package
downloads, tool installations, and external build inputs are not proven
reproducible. Do not describe `image_pinned_recipe` as a rebuildability verdict.

The scan fails closed on Git metadata in `task/environment`, exact solution or
hidden-test files copied into the agent build context, private keys, bearer
credentials, credential-bearing URLs, and symlinks. It is a static task-tree
gate, not an inspection of opaque image layers. Keep image-construction
transcripts private and inspect pre-existing opaque images separately.

## Repeat and negative-control proof

Run every arm as an independent Harbor invocation with new task containers.
Require at least two NOP runs, two
Oracle runs, and one negative control. NOP must receive reward `0`, Oracle must
receive reward `1`, and every run must finish without an exception.

The negative control must be a deliberately incomplete or subtly incorrect,
non-crashing solution relevant to the task and must receive reward `0`. Do not
reuse NOP as the negative control. Record the mutation in private construction
notes without exposing verifier logic.

Before **every** invocation, run `record-run-inputs` with its arm and future job
directory (see the skill's NOP example). This writes an owner-private receipt
under `private/run-inputs/` and refuses existing jobs or receipts. It binds the
full task-tree digest, including executable bits, and Harbor's directory
checksum to the future job. Proof commands use Harbor's `Task.checksum` API
directly; use the existing Harbor Python environment.

For the negative control, retain the custom agent source and supply its exact
`module:Class` identity and task-specific mutation rationale before execution:

```bash
python <skill_dir>/scripts/trace_environment.py record-run-inputs \
  --task-dir <task-dir> --arm negative --job-dir private/jobs/negative-1 \
  --negative-agent negative_agent:IncompleteSolution \
  --negative-source private/negative_agent.py \
  --negative-rationale "<specific incomplete behavior this control exercises>"
PYTHONPATH=<task-dir>/private harbor run -p <task-dir>/task \
  -a negative_agent:IncompleteSolution \
  --jobs-dir <task-dir>/private/jobs --job-name negative-1
```

Ensure that the import resolves to that retained source and retain any local
dependencies as construction evidence. The helper compares the declared source
digest and recorded agent identity; it does not import or execute the control
to infer its semantics. Both `config.agent.name` and `config.agent.import_path`
representations are supported, but conflicting nonempty fields are rejected.
Built-in NOP/Oracle import paths are recognized and cannot serve as the negative
control. NOP and Oracle proof arms must identify their respective built-in agent.

Retain each exact Harbor job directory. Repeat each job option once per result:

```bash
python <skill_dir>/scripts/trace_environment.py record-validation \
  --task-dir <task-dir> \
  --nop-job-dir private/jobs/nop-1 \
  --nop-job-dir private/jobs/nop-2 \
  --oracle-job-dir private/jobs/oracle-1 \
  --oracle-job-dir private/jobs/oracle-2 \
  --negative-job-dir private/jobs/negative-1 \
  --harbor-version "$(harbor --version)"
```

The helper requires unique Harbor job IDs, each result's task checksum matching
the current task and its pre-run receipt, separate verifier mode in every
result, and matching pre-run/current/reproducibility task-tree digests. Old
results cannot be attached to a changed task by regenerating its manifest.
The report records `distinct_jobs: true` only after checking unique job paths
and IDs. It explicitly reports `container_freshness: "unverified"`, including
in exported results. Neither job identity nor the pre-run task receipt proves
container identity or absence of reused container state. Fresh containers remain
an execution requirement, not a property established by this helper. A passing
report means the retained rewards and evidence are consistent, not that container
freshness has been verified. Failed rewards remain technical evidence: retain
them and report the candidate as failed.

Validation v5, reproducibility v3, and public product v3 replace the previous
contracts and their broader claim names. Preserve previous reports privately
before regenerating them from the unchanged task and retained evidence; do not
edit schema strings or claims in place. Jobs with genuine matching pre-run
receipts can be rechecked without claiming a new execution. Historical proof
without those receipts must be rerun; do not fabricate receipts for completed
jobs. Keep historical fixture results labeled with their original contract.
Run receipts and negative-control source/rationale stay private and are never
exported.
