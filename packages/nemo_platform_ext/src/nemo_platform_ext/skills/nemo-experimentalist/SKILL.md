---
name: nemo-experimentalist
description: Improve an existing NeMo agent from an Insight or explicit Harbor-compatible evaluation datasets. Run the Experimentalist, validate candidate changes against a held-out split, and optionally publish a changed winner as a draft PR or MR.
triggers:
  - run experimentalist
  - experimentalist plugin
  - optimize from an insight
  - improve an agent with evaluation data
  - create an experimentalist candidate
  - draft PR for an agent improvement
not-for:
  - nemo-explore (use to design a new agent before it exists)
  - nemo-experiments-upload (use to upload traces or evaluation results)
  - nemo-evaluator (use to author a new evaluation or metric)
  - agents-optimize (use to tune routing, cost, or latency for a deployed agent)
compatibility: nemo-platform >= 0.1.0; requires the Experimentalist plugin, Docker for Harbor evaluation, and a running local platform.
maturity: beta
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write]
---

# NeMo Experimentalist

Use the Experimentalist to improve an existing agent. It evaluates a baseline,
proposes code changes, and keeps only candidates that improve validation.

## Prepare the agent

The Experimentalist improves an existing, evaluable agent; it does not design
or scaffold one. Before running it, make sure you have:

- agent source code and locked dependencies. For PR/MR publication, use a Git
  repository with a clean working tree and a pushed baseline revision;
- an `AGENT-SPEC.md` covering the agent's **Goal**, **Scope**, **Tools**, and
  **Evaluation** contract, including access configuration and constraints but
  never secret values;
- versioned, Harbor-compatible train and validation datasets. Keep a separate
  test split for the final baseline-versus-winner comparison; never use it for
  candidate selection;
- a baseline smoke test that proves the agent runs, scores, and emits its
  expected artifacts and traces; and
- an `optimizer.yaml` profile, or the explicit inputs described below.

Record the agent revision, dataset versions, configuration, and result path
with each run so another operator can reproduce it. If the agent or its spec
does not exist yet, use `nemo-explore` to design it and `nemo-spec` to create
the spec before returning here.

## Pre-flight

Run the built-in checks first:

```bash
nemo agents experimentalist doctor
```

Stop and resolve any missing platform, credential, Docker, or dataset check
before starting a run.

## Choose a run mode

- **Insight-driven:** use an Insight ID or the default Insight written by
  `nemo agents analyst run` in the agent profile. An Insight is a systematic
  symptom inferred from a set of traces. Use this mode when the agent has no
  reliable, verifiable reward for the behavior you need to improve.
- **Explicit evaluation:** pass `--no-insight`, an agent, and separate train
  and validation datasets. Use this mode when a benchmark or other evaluator
  provides a trustworthy, verifiable reward that is a good measure of agent
  quality.

Keep validation independent from training. Never change an evaluation dataset
just to make a candidate win.

## Inputs

Flags override values in `optimizer.yaml`; unresolved values use the command
defaults. With no `--profile`, the CLI discovers `optimizer.yaml` by walking up
from the current directory.

| Input | Purpose | Required |
| --- | --- | --- |
| `--profile` | The `optimizer.yaml` profile containing the agent, datasets, workspace, and optional config. | No; discovered when present. |
| `--insight` / `--insight-id` | The problem to improve. `--insight-id` selects an entry in a local multi-Insight file. | Insight-driven mode. |
| `--no-insight` | Disables profile Insight discovery for an explicit evaluation run. | Explicit mode. |
| `--agent` | Local agent directory or Git URL. A Git URL enables candidate branch and PR/MR publication. | Explicit mode; optional when an Insight supplies the agent. |
| `--agent-spec` | Markdown description of the agent. | Optional; use the profile or conventional `AGENT-SPEC.md` when available. |
| `--train-dataset` / `--validation-dataset` | Separate local Harbor datasets or registry references used to measure improvement. | Yes, unless the profile supplies both. |
| `--task-template` | Evaluator task template. | Required in Insight-driven mode unless the profile supplies it. |
| `--config` | YAML or JSON run settings, including rounds, candidates, and publication options. | No; profile or defaults apply. |
| `--workspace` / `--base-url` | NeMo workspace and platform URL. | Workspace defaults to the profile or `default`; base URL uses `NMP_BASE_URL` or localhost. |
| `--experiment-dir` | Directory for the `eval-and-optimize` artifacts. | No; the CLI creates a timestamped default. |
| `--framework-skills` | Additional framework-skill directories for the optimization agents. | No; may be repeated. |

## Run from an Insight

With an `optimizer.yaml` profile:

```bash
nemo agents experimentalist run --profile path/to/optimizer.yaml
```

Pass `--insight <id-or-local-file>` to override the profile's default Insight.

## Run from explicit datasets

```bash
nemo agents experimentalist run \
  --no-insight \
  --agent path-or-git-url \
  --agent-spec path/to/AGENT-SPEC.md \
  --train-dataset path-or-harbor-ref \
  --validation-dataset path-or-harbor-ref \
  --workspace <workspace> \
  --config path/to/experimentalist.yaml
```

For a Git source, append a ref such as
`git@github.com:owner/repository.git@main`. Enable
`storage.publish_winner` in the configuration to open a draft PR or MR for a
changed winner. Set `storage.archive_candidates: true` to also push every
generated candidate branch.

For a local source, candidates remain in the experiment artifacts and no PR or
MR can be opened.

## Verify and review

Inspect `<experiment-dir>/eval-and-optimize/run.json` for the selected winner
and compare candidate directories under `<experiment-dir>/eval-and-optimize/agents/`.

Review the validation result and generated PR or MR before merging. Do not
overwrite the baseline agent directly.
