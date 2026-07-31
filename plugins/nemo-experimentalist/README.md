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
nemo insights analyze → .nemo-optimizer/insights.yaml or Platform Insight ID
                    → nemo experimentalist doctor
                    → nemo experimentalist run
```

Run `nemo insights analyze` using the Platform Insights plugin and its
documented trace, workspace, and output options. The producer may write the
local profile default, `.nemo-optimizer/insights.yaml`, or persist an Insight
on Platform and report its ID. The Experimentalist does not analyze traces,
schedule analysis, or host an Insight API.

From an agent directory with an `optimizer.yaml` profile, validate the
effective inputs:

```bash
$NEMO experimentalist doctor
```

## Run the Experimentalist locally

`nemo experimentalist run` runs the local Experimentalist loop. It evaluates
a baseline agent on Harbor-compatible train and validation datasets, proposes
candidate mutations, and records its artifacts under the selected experiment
directory.

Model tiers come from the environment, or from a `models:` block in the `--config`
YAML which is applied to the environment before any agent is built. Credentials are
environment-only and never read from config. `nemo experimentalist doctor` reports
which are unset.

| Variable | Default | Used by |
|---|---|---|
| `EXPERIMENTALIST_API_BASE` | `https://inference-api.nvidia.com/v1` | all optimizer agents |
| `EXPERIMENTALIST_API_KEY` | — (required) | all optimizer agents |
| `EXPERIMENTALIST_SMART_MODEL_NAME` | — (required) | Coder, Analyzer, Proposer, Rationalizer, TraceAnalyzer |
| `EXPERIMENTALIST_MID_MODEL_NAME` | — (required) | trajectory scorer, architecture doc |
| `EXPERIMENTALIST_FAST_MODEL_NAME` | — (required) | Terminator, goal tree, summarizers |

```bash
export EXPERIMENTALIST_API_KEY=sk-...
export EXPERIMENTALIST_SMART_MODEL_NAME=openai/openai/openai/gpt-5-mini
export EXPERIMENTALIST_MID_MODEL_NAME=openai/openai/openai/gpt-5-mini
export EXPERIMENTALIST_FAST_MODEL_NAME=openai/openai/openai/gpt-5-mini
```

Model names have no default: a name is only meaningful against a specific endpoint, so
an unset tier fails before the run starts rather than at the first LLM call. Name them
as *your* endpoint does — `openai/openai/openai/gpt-5-mini` on the NVIDIA gateway,
`gpt-5-mini` against OpenAI directly.

Credentials are the one place a default applies: when `EXPERIMENTALIST_API_BASE` is the
NVIDIA gateway, a set `INFERENCE_API_KEY` fills `EXPERIMENTALIST_API_KEY`. A custom base
never inherits it, so a key scoped to the gateway is not forwarded elsewhere.

The agent under test is separate: it reads `AUT_MODEL_NAME`
plus `OPENAI_API_KEY` / `OPENAI_BASE_URL`, which are the only variables forwarded
into the evaluation container.

### Insight-driven optimization

A single local Insight in `.nemo-optimizer/insights.yaml` is selected by
default:

```bash
$NEMO experimentalist run
```

Use `--insight` to name another local file. Local files can contain one
Insight object or an `insights` list. A list with multiple entries requires
`--insight-id`, which accepts an exact ID, exact title, or zero-based index:

```bash
$NEMO experimentalist run \
  --insight path/to/insights.yaml \
  --insight-id 0
```

For an Insight persisted by Platform, pass its ID with its Platform location:

```bash
$NEMO experimentalist run \
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
$NEMO experimentalist run \
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
