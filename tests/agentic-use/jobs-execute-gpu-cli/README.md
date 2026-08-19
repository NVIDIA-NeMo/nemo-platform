<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Execute GPU Jobs Through NeMo Platform Jobs Pipeline (CLI)

Tests real GPU job execution through the NeMo Platform jobs controller and Docker backend. Unlike the proof-of-concept GPU evals that bypass the NeMo Platform job system, this eval dispatches GPU containers through the actual NeMo Platform pipeline.

## What This Tests

- NeMo Platform jobs controller scheduling GPU jobs via Docker backend
- Real GPU container dispatch (nvidia-smi, CUDA operations)
- Job lifecycle: create → schedule → execute → complete/error
- Failure handling and diagnosis through the jobs API

## How It Works

1. Docker socket mounted into Harbor container (DOOD pattern from MR !6902)
2. NeMo Platform jobs controller uses Docker backend to spawn sibling containers with GPU access
3. Agent creates jobs via `nmp jobs create --input-data` with `provider: "gpu"`
4. Jobs run in separate containers with nvidia GPU runtime

## Prerequisites

- Docker socket accessible at `/var/run/docker.sock`
- NVIDIA Container Toolkit installed on host
- `nvidia/cuda:12.8.0-base-ubuntu22.04` image available (pre-pulled in setup)
