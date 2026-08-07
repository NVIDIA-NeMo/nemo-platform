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

Requires `uv >=0.9.14`.

**To verify an end-to-end run, follow
[Get started with an example agent](../../docs/get-started/example-agent.mdx).**

The source dependencies are pinned to tagged or immutable revisions in the
workspace root `pyproject.toml` under `[tool.uv.sources]`. NVIDIA-labs OO Agents
(NOOA) is pinned to a public GitHub commit past `v0.0.8` that carries the
callable `@strategy(llm=...)` support this plugin depends on.

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

## Agent trace formats

The agent under test can emit traces as OTLP or ATIF. **OTLP is the default** —
skip this section unless your agent emits ATIF.

To use an ATIF-emitting agent:

1. Have the agent write its trajectory under its trace directory (`/app/traces`
   in the Harbor task container) with a `.atif.json` suffix.
2. Select the format on the evaluator, in the profile's `experiment_config`:

   ```yaml
   experiment_config:
     evaluator:
       trace_format: atif   # otlp (default) | atif
   ```

3. Run against a platform, which ATIF requires:

   ```bash
   $NEMO agents experimentalist run --base-url https://<platform-host> ...
   ```

Experiment grouping, run counts, and evaluator scores in Studio behave the same
as for OTLP. ATIF traces do not carry per-step timing, so individual step
durations show as zero.

### Troubleshooting

- *"configured `trace_format='otlp'` matched no trace artifact, but atif
  artifacts are present"* — set `trace_format: atif`.
- *"Cannot read ATIF trajectory from disk … this trace was never uploaded"* — the
  run had no reachable platform, so the trace was never ingested. Supply
  `--base-url` and a workspace.

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
  --env NEMO_DEFAULT_MODEL \
  --env NEMO_FAST_MODEL \
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

### Platform models

Run `nemo setup` once for the active Platform context. Setup registers an inference
provider, stores its credential as a Platform Secret, and asks for two
workspace-qualified Model Entities:

- the default model for quality-critical analysis, proposing, and coding;
- the fast model for latency-sensitive scoring, summarization, and control steps.

The default model is also the compatibility value for existing single-model
contexts. Press Enter at the fast-model prompt to reuse it. The Experimentalist
resolves both entities through Platform and lets the entity's backend format route
the Nooa completion request through any registered provider exposed as OpenAI Chat
Completions or Anthropic Messages. It does not read a separate optimizer endpoint,
provider key, or provider model name.

`nemo agents experimentalist doctor` reports the effective pair. For
non-interactive or isolated environments, `NEMO_DEFAULT_MODEL` and
`NEMO_FAST_MODEL` override the stored selections; both values remain Platform
Model Entity IDs in `workspace/model-name` form. The sandbox examples pass these
overrides because the host's `~/.config/nmp/config.yaml` is not part of the clone.

The `--config` YAML is the other kind of configuration: it holds what *one experiment*
does (`max_rounds`, `max_survivors`, per-component tuning) and takes no environment
override, so the file is an accurate record of the run.

### Objective function and regression metrics

Declare what the optimizer should improve separately from what it must preserve.
`objective_function` is one ordered list: each item may be a raw evaluator
metric or an aggregate metric produced by the evaluator. The optimizer only receives
reported metric values and the declared policy; it does not evaluate expressions,
invent weights, or encode a selection algorithm.

A single evaluator-produced aggregate metric:

```yaml
objective_function:
  - name: quality
    direction: maximize
```

Several metrics, for example lower token use and cost, with a guardrail:

```yaml
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

The agent under test remains separate. The Tau3 example reads `AUT_MODEL_NAME`
plus `OPENAI_API_KEY` / `OPENAI_BASE_URL`; those are the only variables forwarded
into its evaluation container and are not used by the Experimentalist agents.

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
