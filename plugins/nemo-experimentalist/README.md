<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Experimentalist

NeMo Experimentalist is the agent-improvement plugin for
[NeMo Platform](https://github.com/NVIDIA-NeMo/nemo-platform). It consumes
Insights produced by the Platform-owned Insights plugin and improves a local
or Git-backed agent against Harbor-compatible train and validation datasets.

## Install and develop

Use **Python 3.12 or 3.13** (`>=3.12,<3.14`). NOOA and Harbor do not support
Python 3.11 or 3.14. The workspace keeps a 3.11 floor for the rest of NeMo
Platform; enable Experimentalist only via the `experimentalist` dependency group.

From the root of this checkout:

```bash
uv sync --group experimentalist
export NEMO="$PWD/.venv/bin/nemo"
```

For a NeMo Platform source checkout, use the
[source-Platform installer](docs/e2e/install-experimentalist-plugin.sh), which keeps
Platform packages editable while installing both plugins' direct runtime
dependencies:

```bash
REPO="$PWD" PLAT=/path/to/nemo-platform bash docs/e2e/install-experimentalist-plugin.sh
export NEMO=/path/to/nemo-platform/.venv/bin/nemo
```

The source dependencies are pinned to tagged or immutable revisions in
`pyproject.toml`. NVIDIA-labs OO Agents (NOOA) is pinned to its public
GitHub `v0.0.6` release.

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

Configure the models before running an experiment:

```bash
export EXPERIMENTALIST_API_BASE=https://inference-api.nvidia.com/v1
export EXPERIMENTALIST_API_KEY=sk-...
export EXPERIMENTALIST_SMART_MODEL_NAME=openai/openai/openai/gpt-5.5
export EXPERIMENTALIST_FAST_MODEL_NAME=openai/openai/openai/gpt-5-mini
```

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

Pass one or more framework skill directories with `--framework-skills` when
the agent needs framework-specific modification guidance. The checked-in Tau2
profile demonstrates profile-owned datasets and task template configuration:
[`examples/tau2-nemo-oo-agent/optimizer.yaml`](examples/tau2-nemo-oo-agent/optimizer.yaml).

Each run writes its local artifacts under `--experiment-dir`, or under
`.nemo-optimizer/experiments/` beside the governing profile by default.

License: Apache-2.0.
