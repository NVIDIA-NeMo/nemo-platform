<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Terminus Bench Experimentalist agent

This is the Experimentalist-side companion for Harbor's `terminus-2` harness.
`prepare-candidate-source.sh` snapshots the Harbor checkout into a separate
staging directory and overlays this example's
`harbor_wrapper.py:WrappedAgent`. Every candidate is therefore a complete
Harbor source tree, while the NVIDIA-specific evaluation adapter stays out of
the Harbor branch. Changes under `src/harbor` remain directly backportable.

The wrapper loads Terminus-2 from the staged candidate's `src` tree in an
isolated import window, so Harbor modules already loaded by the evaluator
cannot shadow the candidate. It also publishes Terminus-2's
canonical `agent/trajectory.json` into Experimentalist's existing
`artifacts/traces/*.atif.json` layout and pins the Opus 4.8 Inference Hub
configuration; no shared evaluator behavior is changed.

The Harbor branch supplies the baseline and emits its normal ATIF trajectories.
Only the wrapper is overlaid; `optimizer.example.yaml` does not substitute a
second agent implementation for Terminus-2.

First create a fresh staged candidate source outside both repositories:

```bash
plugins/nemo-experimentalist/examples/terminus-bench-agent/prepare-candidate-source.sh \
  /path/to/harbor /durable/path/to/staged-harbor-source
```

Then copy `optimizer.example.yaml` to `optimizer.yaml`, set `agent_source` to
that staged directory, and fill in independent Terminal-Bench train/validation
datasets. Do not point both fields at the same data, and keep the extracted
datasets in a durable location rather than `/tmp`. Pass an `--experiment-dir`
outside this repository as well; generated candidate copies under the plugin
tree are large and are discovered by repository-wide checks. Then run:

```bash
NMP_BASE_URL=http://localhost:8080 \
uv run --package nemo-experimentalist-plugin nemo agents experimentalist doctor \
  --profile plugins/nemo-experimentalist/examples/terminus-bench-agent/optimizer.yaml
```

The example is deliberately a one-round, one-candidate smoke profile. Increase
the round and candidate counts only after the baseline succeeds on both splits.
