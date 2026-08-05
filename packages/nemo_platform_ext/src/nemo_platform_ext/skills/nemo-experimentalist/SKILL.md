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

## Configure the environment

The Experimentalist needs a running NeMo Platform, an LLM endpoint for its
optimizer agents, and a model for each tier. For the NVIDIA Inference Gateway,
set the Platform URL, inference key, and model tiers:

```bash
export NMP_BASE_URL=http://localhost:8080
export INFERENCE_API_KEY=<gateway-api-key>
export NEMO_EXPERIMENTALIST_MODELS_SMART=<model-name>
export NEMO_EXPERIMENTALIST_MODELS_MID=<model-name>
export NEMO_EXPERIMENTALIST_MODELS_FAST=<model-name>
```

The CLI uses the NVIDIA Inference Gateway by default and reuses
`INFERENCE_API_KEY` as the Experimentalist key. For another OpenAI-compatible
endpoint, set these instead of `INFERENCE_API_KEY`:

```bash
export NEMO_EXPERIMENTALIST_API_BASE=https://llm.example.com/v1
export NEMO_EXPERIMENTALIST_API_KEY=<endpoint-api-key>
```

Keep these values in your shell environment or an ignored environment file,
never in `optimizer.yaml`, the run configuration, or Git. Configure any
credentials required by the agent under test according to its own setup. To
publish a winning Git candidate, authenticate the relevant CLI in the same
execution environment: `gh auth login` for GitHub or `glab auth login` for
GitLab.

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

Choose either a reusable `optimizer.yaml` profile or pass the required inputs
directly as CLI flags. A profile is optional; when used, flags override its
values. With no `--profile`, the CLI discovers `optimizer.yaml` by walking up
from the current directory.

| Input | Purpose | Required |
| --- | --- | --- |
| `--profile` | The `optimizer.yaml` profile containing the agent, datasets, workspace, and optional config. | No; discovered when present. |
| `--insight` / `--insight-id` | The problem to improve. `--insight` accepts a local Insight file or a platform Insight ID; `--insight-id` selects an entry in a local multi-Insight file. | Insight-driven mode. |
| `--no-insight` | Disables profile Insight discovery for an explicit evaluation run. | Explicit mode. |
| `--agent` | Local agent directory or Git URL. A Git URL enables candidate branch and PR/MR publication. | Explicit mode; optional when an Insight supplies the agent. |
| `--agent-spec` | Markdown description of the agent. | Optional; use the profile or conventional `AGENT-SPEC.md` when available. |
| `--train-dataset` / `--validation-dataset` | Separate local Harbor datasets or registry references used to measure improvement. | Yes, unless the profile supplies both. |
| `--task-template` | A directory containing one Harbor task template (`task.toml`, with placeholder values). In Insight-driven mode, Eval Author copies and fills it for representative failing traces to create the targeted evaluation suite. | Required in Insight-driven mode unless the profile supplies it. |
| `--config` | YAML or JSON **mapping** that validates as the Experimentalist run configuration: top-level run limits plus optional `source`, `storage`, `goal_config`, `coder`, `analyzer`, `proposer`, `evaluator`, and `eval_author` sections. It does not configure model endpoints or model tiers. | No; profile or defaults apply. |
| `--workspace` / `--base-url` | NeMo workspace and platform URL. | Workspace defaults to the profile or `default`; base URL uses `NMP_BASE_URL` or localhost. |
| `--experiment-dir` | Parent directory for all run outputs: the resolved source agent, generated candidates, per-trial results, analysis, `run.json` state, and `OPTIMIZATION.md` summary. | No; the CLI creates a timestamped default. |
| `--framework-skills` | Additional framework-skill directories for the optimization agents. | No; may be repeated. |

An `optimizer.yaml` profile must identify the agent and its source, one task
template, and independent train and validation datasets. It can also set the
workspace, agent specification, run configuration, and framework skills. The
Analyst and Experimentalist share this profile, allowing the latter to use the
default Insight created by the former.

## Explore configuration

Start with
`plugins/nemo-experimentalist/examples/tau3-nooa-agent/experimentalist-smoke.yaml`
for a deliberately small run. The top-level options control rounds and
candidate counts; `source` controls checkout behavior; `storage` controls
candidate branches and PR/MR publication; `evaluator` controls trial
execution; and `eval_author` controls Insight-driven evaluation authoring. See
the [example-agent walkthrough](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/docs/get-started/example-agent.mdx)
for a complete worked optimizer configuration and run.

To inspect the complete schema—including nested options and their defaults—run:

```bash
uv run --package nemo-experimentalist-plugin python -c \
  'import json; from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig; print(json.dumps(EvolutionaryOptimizerConfig.model_json_schema(), indent=2))'
```

Keep model endpoint and model-tier settings out of this file; configure those
as Experimentalist deployment settings instead.

### Tune the Evolutionary Optimizer

Use a smoke configuration to prove that source checkout, Harbor, credentials,
and artifact collection work together. It is intentionally too small to judge
whether an agent is better. For a real run, give the optimizer enough
candidates and train tasks to learn, then rely on the separate validation split
to select the winner.

| Setting | Smoke run | Real run starting point | Effect |
| --- | --- | --- | --- |
| `max_rounds` | `1` | `10`–`15` | Maximum optimization rounds. |
| `max_candidates` / `max_survivors` | `1` / `1` | `3` / `3` | Exploration per round and candidates retained as parents. |
| `max_train_batch_tasks` | Small fixed batch, e.g. `4` | `null` for all train tasks, or a representative fixed batch | Cost and signal available while proposing changes. |
| `max_trajectory_tasks` | `2` | `8` | Tasks used for trajectory/goal-tree scoring. |
| `disable_trajectory_scoring` / `disable_convergence_check` | `true` / `true` | Omit them (both default to `false`) | Skips costly diagnostic work for smoke runs; restores quality and early stopping for real runs. |
| `coder.max_fix_attempts` | `1` | `2` (default) | Maximum repair iterations when a candidate fails its integration check. |
| `evaluator.n_attempts` | `1` | `1`; increase only when task results are noisy | Repeats each evaluation trial. |
| `eval_author.max_traces` | `3` | `10` | Representative Insight traces deeply analyzed in Insight-driven mode. |

A small explicit smoke configuration looks like this:

```yaml
max_rounds: 1
min_rounds_before_stopping: 1
max_survivors: 1
max_candidates: 1
max_trajectory_tasks: 2
max_train_batch_tasks: 4
disable_trajectory_scoring: true
disable_convergence_check: true
storage:
  publish_winner: false
coder:
  max_fix_attempts: 1
evaluator:
  n_attempts: 1
eval_author:
  max_traces: 3
```

### Create a low-cost smoke dataset

When the full dataset is expensive, create small **copied** train and
validation subsets for the smoke run. Select a few representative task
directories from each original split—for example, different task types or
known failure modes—and copy each complete Harbor task directory, including
its `task.toml` and verifier files:

```bash
mkdir -p smoke/train smoke/validation
for task in task-a task-b task-c; do
  cp -R "full/train/$task" smoke/train/
done
for task in task-d task-e; do
  cp -R "full/validation/$task" smoke/validation/
done
```

Point the smoke command at `smoke/train` and `smoke/validation`. Record the
selected task IDs with the smoke configuration. Do not edit or replace the
canonical splits, and do not use a smoke subset to decide whether a candidate
is an improvement; run that decision against the full validation split.

For a real run, begin with the default values, raise only the settings that
match the available evaluation budget, and preserve the same validation split
throughout. Use `storage.archive_candidates: true` only when you need every
candidate branch for review; it increases remote repository noise.

## Run from an Insight

Pass the inputs explicitly when running a one-off optimization:

```bash
nemo agents experimentalist run \
  --insight <platform-id-or-local-file> \
  --agent path-or-git-url \
  --task-template path/to/harbor-task-template \
  --train-dataset path-or-harbor-ref \
  --validation-dataset path-or-harbor-ref \
  --workspace <workspace> \
  --config path/to/experimentalist.yaml
```

`--agent` is optional when the Insight already identifies the agent source.

For a reusable setup, the equivalent information can live in an
`optimizer.yaml` profile. When the profile is complete and the Analyst has
created a default Insight for the agent, this shorter command is enough:

```bash
nemo agents experimentalist run --profile path/to/optimizer.yaml
```

Pass `--insight <platform-id-or-local-file>` to override the profile's default
Insight.

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
`git@github.com:owner/repository.git@main`.
For a local source, candidates remain in the experiment artifacts and no PR or
MR can be opened.

## Verify and review

Inspect `<experiment-dir>/eval-and-optimize/run.json` for the selected winner
and compare candidate directories under `<experiment-dir>/eval-and-optimize/agents/`.

Review the validation result and generated PR or MR before merging. Do not
overwrite the baseline agent directly.
