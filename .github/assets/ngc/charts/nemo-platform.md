---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

description: Deploy NeMo Platform on Kubernetes to build, evaluate, harden, and optimize AI agents
---

## NeMo Platform Helm Chart

NeMo Platform is a toolkit for building, evaluating, hardening, and optimizing
AI agents through a REST API, Python SDK, CLI, and web UI. This chart deploys
those services on Kubernetes.

### Features
Inference, evaluation, guardrails, jobs, observability, and CPU/GPU orchestration.

### Use Cases
Shared agent platform; pre-production evaluation and red-teaming; GPU-backed customization and synthetic-data jobs.

### System Requirements
Kubernetes, Helm, kubectl, ReadWriteMany storage, and an NGC API key.
GPU workloads need NVIDIA GPU nodes and the GPU Operator or device plugin.
See the [support matrix](https://docs.nvidia.com/nemo-platform/documentation/reference/support-matrix).

### License
This chart is licensed under the [Apache License 2.0](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/LICENSE).
