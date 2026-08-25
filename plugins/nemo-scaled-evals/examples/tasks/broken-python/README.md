<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# broken-python — comparable smoke task

Single-task OpenThoughts-TBLite smoke used across all scaled-evals sandbox runtimes:

| Field | Value |
|-------|-------|
| Task | `openthoughts_tblite::broken-python` |
| Dataset | `openthoughts-tblite@2.0` |
| Agent | Harbor **oracle** (reward 0 or 1; timeouts are failures) |
| Policy model | Not required |

## Runtimes

| `runtime` | Harness | How broken-python runs |
|-----------|---------|------------------------|
| `gym_daytona` | `examples/gym-daytona` | `GYM_SMOKE_PROFILE=broken-python` → `harbor_agent` + Daytona |
| `sandbox_k8s` | `examples/agent-sandbox` | `configs/harbor_oracle_k8s.yaml` → local `task/` on remote K8s |

`gym_sandbox_daytona` intentionally does **not** run this Harbor smoke. That
runtime is reserved for `mini_swe_agent_2` through `nemo_gym.sandbox`.

## Assets (this directory)

- `task/` — Harbor task tree (remote K8s: `--user` pip installs for read-only root FS)
- `build-image.sh` — build/push `TASK_IMAGE` when not using a public base image
- `data/tb_broken_python_one.jsonl` — Gym rollout input (one row)
- `configs/harbor_oracle_daytona_tblite.yaml` — Gym `harbor_agent` config (Daytona env)
- `configs/harbor_oracle_k8s.yaml` — Harbor CLI config (agent-sandbox K8s env)

## Quick start

**Daytona (compose):** set `GYM_SMOKE_PROFILE=broken-python` in
`examples/gym-daytona/targets/daytona.env`, then POST with
`"runtime": "gym_daytona"`.

**Remote K8s:** enable `SANDBOX_K8S_*` in `.env`, `make compose-up`, POST with `"runtime": "sandbox_k8s"`.
