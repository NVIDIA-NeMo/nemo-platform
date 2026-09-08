---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: eval-author-trace-environment
description: >-
  Turn one MLflow, Intake, OpenTelemetry, or existing ATIF trace into a private,
  text-only candidate for a reproducible Harbor task environment. Use when a
  coding agent should derive an evaluation environment from recorded behavior
  and retain a candidate or no_candidate summary by task.
triggers:
  - create an evaluation environment from a trace
  - turn ATIF into a Harbor task environment
  - derive an eval task from MLflow Intake or OpenTelemetry data
not-for:
  - eval-author (use for the shared standard and routing)
  - mlflow-to-atif (use only to normalize MLflow traces into ATIF)
  - eval-author-task-create (use to close an actionable audit coverage gap)
  - eval-author-inspect-trace (use to explain an Intake trace without creating an environment)
compatibility: >-
  Python 3.11 or later for the standalone helper. MLflow normalization uses the
  sibling mlflow-to-atif skill. Intake reads require the nemo CLI. Candidate
  verification requires an existing Harbor installation and Docker. No model,
  provider, or agent-framework configuration is required.
maturity: alpha
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Grep, Glob]
---

# Eval Author: trace to environment

Read `eval-author` for the shared evidence standard and boundaries. This flow
uses the current coding agent to turn one recorded interaction into one small,
reproducible Harbor task. It does not require a particular coding agent, model,
or framework.

```text
bounded source → canonical ATIF → private text scrub → candidate decision
                                                     ├─ no_candidate → summary
                                                     └─ candidate → Harbor task → summary
```

The ATIF file is the only handoff into candidate analysis. Keep exact source
exports restricted. Do not put trace payloads, credentials, or generated task
workspaces in Git.

## Artifact contract

Use one workspace per task:

```text
.eval-author/trace-environments/
  .gitignore
  <task-id>/
    private/source.atif.json
    private/ground-truth/
    safe/trace.atif.json
    safe/privacy.json
    candidate.json
    task/
    validation.json
    summary.json
    summary.md
```

`scripts/trace_environment.py init` writes the parent `.gitignore` so every
task directory is ignored, makes directories owner-only, and refuses to replace
an existing task workspace. The helper prints content-free JSON summaries.

## Step 1: create the private task workspace

Choose a stable lowercase kebab-case task ID. Derive it from a caller-supplied
case name or trace ID; do not put a person's name, email address, account number,
or other private value in it.

```bash
python <skill_dir>/scripts/trace_environment.py init \
  --task-id <task-id>
```

Keep every source export and intermediate conversion under the returned task
directory. Use `umask 077` before redirecting provider output there.

## Step 2: normalize exactly one source to ATIF

Do not merge unrelated traces. Preserve the source's trace and span identifiers
in `extra`, order steps by recorded time, and record every missing or lossy field
under `extra.normalization.uncertainties` or `extra.normalization.losses`.
Never invent an instruction, tool result, file, or final answer.

### Existing ATIF

Use the trajectory as the canonical input. Do not relabel its ATIF version.

### MLflow

Read and follow `mlflow-to-atif`. Put its owner-private output under the task
workspace and use the emitted `.atif.json` file as the canonical input.

### Intake

Resolve the CLI exactly as `eval-author-inspect-trace` specifies. Read one exact
trace and every detailed span into owner-private JSON files:

```bash
umask 077
nemo intake traces get --output-format=json --workspace="WORKSPACE" --mode=detailed "TRACE_ID" > <task-dir>/private/intake-trace.json
nemo intake spans list --output-format=json --workspace="WORKSPACE" --filter.trace-id="TRACE_ID" --mode=detailed --sort=started_at --all-pages > <task-dir>/private/intake-spans.json
```

Require every returned span's `trace_id` to match the selected trace. The coding
agent converts those records to ATIF: root input becomes the user instruction;
model or assistant output becomes agent steps; each tool span becomes a paired
tool call and observation; errors and unmapped attributes remain cited in
`extra.intake`. If there is no complete human instruction, record no_candidate.

### OpenTelemetry

Prefer an existing Intake trace produced from the telemetry and use the Intake
path above. For a bounded JSON OTLP export, the coding agent may map the root and
descendant spans directly using the same rules. Preserve trace IDs, span IDs,
parent IDs, timestamps, status, and semantic attributes under `extra.otel`.
Do not parse protobuf bytes, contact a collector, or ingest remote data in this
flow. If the export cannot establish parentage or a human instruction, record
no_candidate instead of guessing.

Before continuing, verify the canonical file has one ATIF v1.0-v1.7 object, one-based
sequential step IDs, at least one user step, and resolvable tool-call references.

## Step 3: make a text-only safe copy

```bash
python <skill_dir>/scripts/trace_environment.py prepare \
  --task-dir <task-dir> \
  --atif <canonical-atif-file> \
  --source-kind <atif|mlflow|intake|otel>
```

The helper retains an exact owner-private original, writes a scrubbed safe copy,
replaces image parts with omission markers, and records only redaction counts.
It recognizes common secret fields, bearer tokens, private keys, email addresses,
phone numbers, social-security numbers, IP addresses, and user home paths.

This deliberately small scanner cannot recognize names, organizations, street
addresses, proprietary code, or every credential format. Review every text field
in `safe/trace.atif.json` and the generalized task files before passing
`--privacy-reviewed`. Never copy a redacted value into a verifier. An image-only
user instruction is a blocking reason and must remain no_candidate.

## Step 4: inventory ground truth and software requirements

Before deciding candidacy, look for ground truth that is distinct from the
agent's observed answer:

- a separate reference or successful trajectory;
- expected output, golden files, fixtures, or labeled data;
- verifier inputs or reference solutions; and
- explicit human or evaluator feedback that establishes correctness.

An agent answer is not ground truth merely because the trace succeeded. Record
ground truth as `available`, `partial`, `absent`, or `unknown`. Retain available
artifacts under `private/ground-truth/`, make them owner-only, record their
SHA-256 digests, and cite the ATIF steps that establish their relationship to
the task. Do not copy private ground-truth values into the generated task;
generalize only what the verifier needs.

Also inventory software needed to reproduce the work or verify the outcome.
Include libraries and CLIs, desktop applications such as CAD tools, services,
hardware, and proprietary or commercially licensed software. For each item,
record whether it is actually required, its version when known, license class,
local availability, redistributability, evidence steps, and a short note.

Do not silently replace required software with a different application or mock
when the requested behavior depends on the real product. Required unavailable
software prevents candidacy. Unknown availability keeps the environment
unproven until resolved. Proprietary or non-redistributable software is usable
only when a legitimate, reproducible runtime path exists; never copy licensed
binaries into the task.

## Step 5: decide candidate or no_candidate

Read only `safe/trace.atif.json`. Later user corrections outrank earlier turns.
Every decision must cite real ATIF `step_id` values. Write `candidate.json` with
this shape:

```json
{
  "schema": "nemo.eval_author.trace_environment_candidate.v1",
  "status": "candidate",
  "instruction": "Observable task instruction without private values",
  "requirements": ["Objectively testable requirement"],
  "verification_mode": "execution",
  "evidence_steps": [1, 2],
  "uncertainties": [],
  "reason_codes": [],
  "ground_truth": {
    "availability": "available",
    "artifacts": [
      {
        "kind": "expected_output",
        "path": "private/ground-truth/expected.json",
        "sha256": "sha256:<64-hex-digest>",
        "evidence_steps": [2],
        "notes": "Expected output attached to the recorded task."
      }
    ],
    "absence_reason": null
  },
  "software_requirements": [
    {
      "name": "ExampleCAD",
      "category": "desktop_application",
      "required": true,
      "version": "2026",
      "license": "proprietary",
      "availability": "unknown",
      "redistributable": false,
      "evidence_steps": [1, 2],
      "notes": "The requested edit and verifier depend on native CAD behavior."
    }
  ]
}
```

Use `candidate` only when the request and expected outcome are complete,
reproducible without private or live external state, and objectively testable.
This basic flow supports execution verification only. Do not add a model judge
or convert a subjective, visual, or prose-quality outcome into a brittle string
check.

For no candidate, set `status` to `no_candidate`, `instruction` and
`verification_mode` to `null`, keep `requirements` empty, and include one or more
stable `reason_codes`. Keep the `ground_truth` and `software_requirements`
inventories in the record even when they are empty or explain the blocker.
Typical reasons are `missing_instruction`,
`missing_outcome`, `requires_private_state`, `requires_live_external_state`,
`non_text_evidence_required`, `subjective_verification`, and
`insufficient_trace_evidence`. Use `required_software_unavailable` or
`proprietary_runtime_unavailable` when the software inventory blocks a
reproducible task. Ground truth may be absent without blocking a task, but its
absence must be explicit.

## Step 6: author and prove a candidate environment

Skip this step for no_candidate. Under `<task-dir>/task/`, create the smallest
Harbor task that reproduces the initial state and objectively verifies the
generalized outcome:

- `task.toml` with realistic timeouts and resources;
- `instruction.md` matching `candidate.json` without leaking tool names or test logic;
- `environment/` containing prerequisites but never the solution;
- `tests/test.sh` that grades only the observable outcome;
- `solution/solve.sh` with the reference solution; and
- `README.md` containing reviewer-facing development context, not a copy of the
  agent instruction.

The task README is not passed to the agent. Give it a level-one task title and
these substantive level-two sections:

- `Difficulty explanation`: why the task is difficult for agents and humans;
- `Environment and software requirements`: runtimes, services, hardware,
  versions, licensing, and availability constraints;
- `Ground-truth provenance`: what establishes correctness and where that
  evidence came from, without exposing private values;
- `Solution explanation`: the high-level reference approach without duplicating
  `solution/solve.sh`;
- `Verification explanation`: the observable outcomes and how the verifier
  distinguishes success from failure; and
- `Relevant experience`: human-supplied experience relevant to authoring or
  reviewing the task.

Keep each section concise and evidence-backed. Do not repeat `instruction.md`,
reveal verifier internals to the agent, or invent author experience. If a human
cannot supply and review `Relevant experience`, keep the environment `unproven`
rather than claiming it is ready.

Do not copy private trace payloads into the task. Include only the minimal files
needed to reproduce the starting state. Pin external source to an exact public
commit when it is truly required; otherwise prefer a small local fixture.

Run both deterministic arms:

```bash
harbor run -p <task-dir>/task -a nop
harbor run -p <task-dir>/task -a oracle
```

NOP must finish without an exception and receive reward `0`; Oracle must finish
without an exception and receive reward `1`. Do not weaken the verifier to make
Oracle pass. Write their exact evidence to `validation.json`:

```json
{
  "schema": "nemo.eval_author.trace_environment_validation.v1",
  "nop": {"reward": 0, "exception": null, "job_dir": "private/jobs/nop"},
  "oracle": {"reward": 1, "exception": null, "job_dir": "private/jobs/oracle"}
}
```

Retain each exact Harbor job directory at the relative path recorded above.
These evidence directories must stay inside the ignored task workspace.

If Harbor or Docker is missing, the environment is `unproven`; do not describe
it as ready. If either arm fails, record `failed` and retain the useful failure
summary in the task workspace.

## Step 7: finalize and verify the summary

Record concise facts about the conversion and construction. Do not include raw
payloads or redacted values in these flags.

For a ready candidate:

```bash
python <skill_dir>/scripts/trace_environment.py finalize \
  --task-dir <task-dir> \
  --status candidate \
  --environment-status ready \
  --privacy-reviewed \
  --worked-well "<evidence-backed success>" \
  --did-not-work "<evidence-backed limitation>"
```

For no_candidate:

```bash
python <skill_dir>/scripts/trace_environment.py finalize \
  --task-dir <task-dir> \
  --status no_candidate \
  --reason "<why no reproducible environment can be built>"
```

Then verify digests and required artifacts:

```bash
python <skill_dir>/scripts/trace_environment.py check \
  --task-dir <task-dir>
```

Report the task ID, `candidate` or `no_candidate`, ground-truth availability and
artifact count, required software and licensing constraints, environment
status, privacy review status, NOP and Oracle rewards when run, and paths to
`summary.md` and the generated task. A `valid: true` check proves the recorded
files are internally consistent; Harbor is the authority for whether the task
actually runs.
