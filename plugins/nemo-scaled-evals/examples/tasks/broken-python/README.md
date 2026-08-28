<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# broken-python — Kubernetes evaluation smoke task

Single-task OpenThoughts-TBLite smoke for the Kubernetes sandbox runtime:

| Field | Value |
|-------|-------|
| Task | `openthoughts_tblite::broken-python` |
| Dataset | `openthoughts-tblite@2.0` |
| Agent | Harbor **oracle** (reward 0 or 1; timeouts are failures) |
| Policy model | Not required |

It runs through `sandbox_k8s` using `configs/harbor_oracle_k8s.yaml`, the local
`task/` directory, and a remote Kubernetes sandbox.

## Assets (this directory)

- `task/` — Harbor task tree (remote K8s: `--user` pip installs for read-only root FS)
- `build-image.sh` — build/push `TASK_IMAGE` when not using a public base image
- `configs/harbor_oracle_k8s.yaml` — Harbor CLI config (agent-sandbox K8s env)

## Quick start

Enable `SANDBOX_K8S_*` in the deployment configuration and submit an
evaluation with `"runtime": "sandbox_k8s"`. The deployment smoke command is
`deploy/k8s/eval-smoke.sh`.
