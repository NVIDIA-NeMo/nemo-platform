<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Run the Tau3 Airline workflow

This runbook prepares one Tau3 dataset for Insights and Experimentalist, uploads
a 20-task agent trace corpus without benchmark answers, analyzes those traces,
and runs a 3-train/2-validation Experimentalist smoke test.

Run every command from the NeMo Platform repository root.

## Prerequisites

NeMo Platform and Docker must be running. Configure an NVIDIA Inference Gateway
virtual key before continuing:

```bash
export NMP_BASE_URL=http://localhost:8080
export INFERENCE_API_BASE=https://inference-api.nvidia.com/v1
export INFERENCE_API_KEY=sk-...

export MODEL=openai/openai/openai/gpt-5-mini
export OPENAI_API_KEY="$INFERENCE_API_KEY"
export OPENAI_BASE_URL="$INFERENCE_API_BASE"
export EXPERIMENTALIST_API_KEY="$INFERENCE_API_KEY"
export EXPERIMENTALIST_API_BASE="$INFERENCE_API_BASE"

# Upstream Tau3 currently reads these compatibility variable names.
export TAU2_USER_MODEL="$MODEL"
export TAU2_NL_ASSERTIONS_MODEL="$MODEL"
export AUT_MODEL_NAME="$MODEL"

export EXPERIMENTALIST_SMART_MODEL_NAME="$MODEL"
export EXPERIMENTALIST_MID_MODEL_NAME="$MODEL"
export EXPERIMENTALIST_FAST_MODEL_NAME="$MODEL"

curl -sf "$NMP_BASE_URL/health/ready"
docker info >/dev/null
```

## Prepare the datasets

Download the official `sierra-research/tau3-bench@1` dataset and stage the
20-task Insights corpus and Experimentalist smoke splits:

```bash
plugins/nemo-experimentalist/examples/tau3-nooa-agent/prepare-airline-datasets.sh
```

The script creates:

```text
plugins/nemo-experimentalist/tmp/tau3-airline/insights
plugins/nemo-experimentalist/tmp/tau3-airline/experimentalist/train
plugins/nemo-experimentalist/tmp/tau3-airline/experimentalist/validation
```

## Upload the Insights trace corpus

Run the agent over all 20 Insights tasks:

```bash
uv run --frozen \
  plugins/nemo-experimentalist/examples/tau3-nooa-agent/run_airline_insights.py
```

The runner creates the `tau3-airline` workspace, uploads only agent execution
traces, waits until all 20 traces are readable from Intake, and writes an
`uploaded-traces.json` summary under:

```text
plugins/nemo-experimentalist/tmp/tau3-airline-insights/<experiment-id>/
```

Use a fresh workspace name when repeating the run because Intake appends traces:

```bash
uv run --frozen \
  plugins/nemo-experimentalist/examples/tau3-nooa-agent/run_airline_insights.py \
  --workspace tau3-airline-rerun
```

For a one-task preflight:

```bash
uv run --frozen \
  plugins/nemo-experimentalist/examples/tau3-nooa-agent/run_airline_insights.py \
  --task-id tau3-bench__tau3-airline-0 \
  --expected-task-count 1 \
  --workspace tau3-airline-preflight
```

## Analyze the traces

```bash
uv run --frozen nemo insights analyze \
  --agent nemo-experimentalist-tau3-nooa \
  --workspace tau3-airline \
  --base-url "$NMP_BASE_URL"
```

Open the uploaded traces at:

```text
http://localhost:8080/studio/workspaces/tau3-airline/intake/traces
```

## Run the Experimentalist smoke test

Create a workspace for the optimization run:

```bash
uv run --frozen nemo workspaces create canonical-tau3-airline \
  --description "Tau3 Airline Experimentalist runs" \
  --exist-ok
```

Run one Experimentalist round over the 3-train/2-validation smoke split:

```bash
uv run --frozen nemo experimentalist run \
  --no-insight \
  --agent plugins/nemo-experimentalist/examples/tau3-nooa-agent \
  --agent-spec plugins/nemo-experimentalist/examples/tau3-nooa-agent/AGENT-SPEC.md \
  --train-dataset plugins/nemo-experimentalist/tmp/tau3-airline/experimentalist/train \
  --validation-dataset plugins/nemo-experimentalist/tmp/tau3-airline/experimentalist/validation \
  --workspace canonical-tau3-airline \
  --framework-skills plugins/nemo-experimentalist/framework-skills/nooa \
  --config plugins/nemo-experimentalist/examples/tau3-nooa-agent/experimentalist-smoke.yaml \
  --experiment-dir plugins/nemo-experimentalist/tmp/tau3-airline-experimentalist \
  --base-url "$NMP_BASE_URL"
```

After completion, inspect `eval-and-optimize/run.json` in the experiment
directory for the selected candidate and compare `agent-0` with `agent-1`.
