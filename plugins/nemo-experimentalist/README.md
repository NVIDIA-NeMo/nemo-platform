<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Experimentalist

NeMo Experimentalist is the agent-improvement plugin for
[NeMo Platform](https://github.com/NVIDIA-NeMo/nemo-platform). It consumes
Insights produced by the Platform-owned Insights plugin and improves a local
or Git-backed agent against Harbor-compatible train and validation datasets.

## Install and develop

This plugin lives in the `nemo-platform` monorepo and shares the root `.venv`.
From the root of the checkout:

```bash
uv sync
export NEMO="$PWD/.venv/bin/nemo"
```

Requires `uv >=0.9.14,<0.10.0`.

**To verify an end-to-end run, follow
[Get started with an example agent](../../docs/get-started/example-agent.mdx).**

The source dependencies are pinned to tagged or immutable revisions in
`pyproject.toml`. NVIDIA-labs OO Agents (NOOA) is pinned to a public GitHub
commit, currently one past `v0.0.6` that carries an MCP transport-timeout fix.

## Insight-to-experiment flow

The supported handoff is:

```text
nemo agents analyst run → .nemo-optimizer/insights.yaml or Platform Insight ID
                       → nemo agents experimentalist doctor
                       → nemo agents experimentalist run
```

Run `nemo agents analyst run` using the Platform Insights plugin and its
documented trace, workspace, and output options. It always persists an Insight
on Platform and reports its ID; `--insights-file-output` additionally mirrors
those rows into a local file, which this plugin can consume in place of an ID.
The Experimentalist does not analyze traces, schedule analysis, or host an
Insight API.

From an agent directory with an `optimizer.yaml` profile, validate the
effective inputs:

```bash
$NEMO agents experimentalist doctor
```

## Run the Experimentalist locally

`nemo agents experimentalist run` runs the local Experimentalist loop. It evaluates
a baseline agent on Harbor-compatible train and validation datasets, proposes
candidate mutations, and records its artifacts under the selected experiment
directory.

### Recommended laptop isolation

Use [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/) instead of a
privileged Docker-in-Docker container or a host Docker socket mount. The
Experimentalist runs inside an isolated microVM, while Harbor uses that
sandbox's private Docker daemon for task containers. Clone mode gives the
Experimentalist a private writable clone instead of write access to the host
checkout. This flow requires Docker Engine 29.6.2 or later and was tested with
Docker Sandboxes (`sbx`) 0.37.1.

Create the sandbox and run the Experimentalist:

```bash
repo="$(git rev-parse --show-toplevel)"
sbx create --clone --name nemo-experimentalist shell "$repo"
sbx exec --workdir "$repo" \
  --env UV_PROJECT_ENVIRONMENT=/home/agent/.venvs/nemo-platform \
  --env INFERENCE_API_KEY \
  --env NEMO_EXPERIMENTALIST_API_BASE \
  --env NEMO_EXPERIMENTALIST_API_KEY \
  --env NEMO_EXPERIMENTALIST_MODELS_SMART \
  --env NEMO_EXPERIMENTALIST_MODELS_MID \
  --env NEMO_EXPERIMENTALIST_MODELS_FAST \
  nemo-experimentalist \
  uv run --frozen --python 3.13 --package nemo-experimentalist-plugin --with ./plugins/nemo-agents \
  nemo agents experimentalist run
```

Append the run options described below. `UV_PROJECT_ENVIRONMENT` keeps the
sandbox's Linux environment separate from the host checkout's `.venv`. Clone
mode prevents sandbox writes to the host checkout, but it is not a secret
isolation boundary: the complete host repository, including ignored `.env`
files, remains readable at `/run/sandbox/source`. Values passed with `sbx exec
--env` are readable by the optimizer, candidate agent, verifier, and their
subprocesses. Use dedicated, revocable, spending-limited keys. Optimizer and
task code can use any outbound access granted to the sandbox. The sandbox must
be able to reach the package, model, registry, Harbor dataset, and NeMo Platform
endpoints required by the run.

Copy experiment artifacts you want to retain to the host with `sbx cp`; the
[complete example](../../docs/get-started/example-agent.mdx#5-optimize-performance-with-the-experimentalist)
includes concrete inspection, comparison, and copy commands.
`sbx stop nemo-experimentalist` preserves the VM, output, packages, and private
Docker cache; `sbx rm nemo-experimentalist` deletes them. On Apple silicon,
Harbor tasks that publish only `linux/amd64` images do not run in the
`linux/arm64` sandbox. This currently includes the Terminal-Bench `fix-git`
task; use an x86_64 machine or VM for that suite.

### Endpoint and model settings

Which endpoint the Experimentalist talks to, and with which models, is a *deployment*
setting: one per install, not per experiment. Like every other NeMo plugin it is a
`NemoConfig`, so it can be set either in the `experimentalist:` section of the platform
config file or through the environment, and **the environment wins**.
`nemo experimentalist doctor` reports what is unset.

| Variable | Config key | Default | Used by |
|---|---|---|---|
| `NEMO_EXPERIMENTALIST_API_BASE` | `api_base` | `https://inference-api.nvidia.com/v1` | all optimizer agents |
| `NEMO_EXPERIMENTALIST_API_KEY` | `api_key` | — (required) | all optimizer agents |
| `NEMO_EXPERIMENTALIST_MODELS_SMART` | `models.smart` | — (required) | Coder, Analyzer, Proposer, Rationalizer, TraceAnalyzer |
| `NEMO_EXPERIMENTALIST_MODELS_MID` | `models.mid` | — (required) | trajectory scorer, architecture doc |
| `NEMO_EXPERIMENTALIST_MODELS_FAST` | `models.fast` | — (required) | Terminator, goal tree, summarizers |

The tiers exist to buy capability where it changes the result and speed where it does not,
so give them different models — smart writes the code, fast runs the high-volume judging:

```bash
export NEMO_EXPERIMENTALIST_API_KEY=sk-...
export NEMO_EXPERIMENTALIST_MODELS_SMART=openai/openai/openai/gpt-5.6-sol
export NEMO_EXPERIMENTALIST_MODELS_MID=openai/openai/openai/gpt-5.6-terra
export NEMO_EXPERIMENTALIST_MODELS_FAST=openai/openai/openai/gpt-5.6-luna
```

Model names have no default: a name is only meaningful against a specific endpoint, so
an unset tier fails before the run starts rather than at the first LLM call. Name them
as *your* endpoint does — `openai/openai/openai/gpt-5.6-sol` on the NVIDIA gateway,
`gpt-5.6-sol` against OpenAI directly. The
[example agent's `.env.example`](examples/tau3-nooa-agent/.env.example) is a working set.

Credentials are the one place a default applies: when the API base is the NVIDIA gateway,
a set `INFERENCE_API_KEY` fills `NEMO_EXPERIMENTALIST_API_KEY`. A custom base never
inherits it, so a key scoped to the gateway is not forwarded elsewhere.

The `--config` YAML is the other kind of configuration: it holds what *one experiment*
does (`max_rounds`, `max_survivors`, per-component tuning) and takes no environment
override, so the file is an accurate record of the run.

### Objective function and regression metrics

Declare what the optimizer should improve separately from what it must preserve.
`objective_function` is one ordered list: each item may be a raw evaluator
metric or an aggregate metric produced by the evaluator. The optimizer only receives
reported metric values and the declared policy; it does not evaluate expressions,
invent weights, or encode a selection algorithm.

```yaml
# A single evaluator-produced aggregate metric.
objective_function:
  - name: quality
    direction: maximize

# Include several metrics, for example lower token use and cost.
objective_function:
  - name: tokens
    direction: minimize
  - name: cost
    direction: minimize
regression_metrics:
  - name: success_rate
    direction: maximize
```

For an insight-driven run, Eval Author's authored insight metrics replace the
run-level objective metrics. The configured objective targets move to
`regression_metrics`, alongside the existing guardrails, so the insight is
improved without giving up the run's original priorities.

The agent under test is separate: it reads `AUT_MODEL_NAME`
plus `OPENAI_API_KEY` / `OPENAI_BASE_URL`, which are the only variables forwarded
into the evaluation container.

### Insight-driven optimization

A single local Insight in `.nemo-optimizer/insights.yaml` is selected by
default:

```bash
$NEMO agents experimentalist run
```

Use `--insight` to name another local file. Local files can contain one
Insight object or an `insights` list. A list with multiple entries requires
`--insight-id`, which accepts an exact ID, exact title, or zero-based index:

```bash
$NEMO agents experimentalist run \
  --insight path/to/insights.yaml \
  --insight-id 0
```

For an Insight persisted by Platform, pass its ID with its Platform location:

```bash
$NEMO agents experimentalist run \
  --insight <platform-insight-id> \
  --workspace <workspace> \
  --base-url https://<platform-host>
```

`--agent` may override the baseline agent named by an Insight. The profile
supplies the task template and the required train and validation datasets; flags
can override those values.

### Dataset-driven optimization

Use `--no-insight` to bypass both an explicit Insight and the profile-local
default. Supply a baseline agent when the profile does not provide one:

```bash
$NEMO agents experimentalist run \
  --no-insight \
  --agent path/to/agent \
  --train-dataset path/to/train \
  --validation-dataset path/to/validation \
  --task-template path/to/task_template
```

`--task-template` is only required with `--insight`; a dataset-driven run does
not need one. Pass one or more framework skill directories with
`--framework-skills` when the agent needs framework-specific modification
guidance — `framework-skills/nooa` for the Tau3 example agent.

Step 5 of [the example-agent guide](../../docs/get-started/example-agent.mdx) is
a complete worked instance of this command against the checked-in Tau3 Airline
example, including the `.env` contents and dataset preparation.

Each run writes its local artifacts under `--experiment-dir`, or under
`.nemo-optimizer/experiments/` beside the governing profile by default.

License: Apache-2.0.
