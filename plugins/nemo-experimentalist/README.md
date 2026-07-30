<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo Experimentalist

NeMo Experimentalist is the agent-improvement plugin for
[NeMo Platform](https://github.com/NVIDIA-NeMo/nemo-platform). It consumes
Insights produced by the Platform-owned Insights plugin and improves a local
or Git-backed agent against Harbor-compatible train and validation datasets.

## Install and develop

From the root of this checkout:

```bash
uv sync
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
`pyproject.toml`. NVIDIA-labs OO Agents (NOOA) is pinned to a public GitHub
commit, currently one past `v0.0.6` that carries an MCP transport-timeout fix.

## Insight-to-experiment flow

The Tau2 dogfood fixture exercises the supported handoff with three commands
after the Platform is running:

```bash
cd examples/tau2-nemo-oo-agent
nemo traces import state-v9
nemo insights analyze
nemo experimentalist run
```

See the fixture's [four-command playbook](examples/tau2-nemo-oo-agent/README.md)
for the required Platform services and credential file. The trace import writes
the selected workspace and corpus time range into profile-local workflow
context. Insights writes `.nemo-optimizer/insights.yaml`; Experimentalist reads
both files without workspace, base-URL, or Insight flags.

From an agent directory with an `optimizer.yaml` profile, validate the
effective inputs:

```bash
$NEMO experimentalist doctor
```

## Run the Experimentalist

`nemo experimentalist run` runs Experimentalist inside OpenShell by default.
The sandbox contains the optimization agents but has no Docker CLI or socket.
Harbor evaluation crosses a narrow API to the local bridge described in the
[OpenShell setup](src/nemo_experimentalist_plugin/openshell/README.md).
Rationalizer and TraceAnalyzer use bridge-owned task dependency sessions, so
their shell commands run inside the Harbor task environment without granting
Docker authority to the sandbox.

From a source checkout, the CLI reuses a compatible
`local/nmp-experimentalist:local` image and otherwise builds that image for the
host architecture. Set `NEMO_EXPERIMENTALIST_IMAGE` to use a different image.

The CLI starts an ephemeral Harbor bridge and configures the dedicated
OpenShell bridge, inference, and source-control providers for each run. Model
names remain ordinary environment settings:

```bash
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

Each OpenShell run downloads its artifacts to `--experiment-dir`, or to
`./tmp/experimentalist-openshell` by default.
There is no host-execution mode or automatic fallback when OpenShell setup or
image preparation fails.

License: Apache-2.0.
