<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tau2 NeMo OO Agent optimization fixture

This is the agent under test for the NeMo Experimentalist dogfood flow. The
checked-in `optimizer.yaml` connects the existing `state-v9` trace corpus,
NeMo Insights, and the Dockerless OpenShell Experimentalist runtime.

## Prerequisites

Run from a bootstrapped NeMo Platform source checkout with Docker Desktop and
OpenShell available. The Platform must expose `auth`, `entities`, `intake`,
`models`, `inference-gateway`, and `secrets`, plus the `models` controller.
Intake's ClickHouse span store must also be running.

If the Platform is not already running:

```bash
nemo services start \
  --services auth,entities,intake,models,inference-gateway,secrets \
  --controllers models \
  --sidecars clickhouse
```

Copy `.env.example` to the ignored `.env` file and fill in the inference key.
The internal GitLab dataset registry also requires `GITLAB_TOKEN`.

## Four-command playbook

From this directory:

```bash
nemo traces import state-v9
nemo insights analyze
nemo experimentalist run
```

`nemo traces import` downloads the existing 270-span corpus, restores it into
the profile's `tau2-airline` workspace, and records the corpus time range.
`nemo insights analyze` reads that context and writes
`.nemo-optimizer/insights.yaml`. If the file contains multiple Insights,
`nemo experimentalist run` prompts for one before it starts OpenShell.

The Experimentalist command starts its ephemeral Harbor bridge, configures the
dedicated OpenShell providers, selects the Docker Desktop policy on macOS,
builds or reuses the container image, runs the optimization loop, downloads
the artifacts, and stops the bridge.

The fixture assumes the published `nemo-oo-airline` traces represent this
checked-in agent revision. That provenance is not encoded in the legacy
`state-v9` bundle.
