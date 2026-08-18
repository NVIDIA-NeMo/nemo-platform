<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Models Service

The Models service is the source of truth for model-related platform resources. It manages model entities, adapters, deployment configs, deployments, and model providers, and exposes the APIs that other services use to resolve what models exist, how they should be deployed, and which backend or provider can serve them.

The service also owns model-controller configuration for deployment reconciliation. Controller backends are selected from platform runtime configuration, with Docker, Kubernetes NIM Operator, or no-op backends available depending on the environment.

Keep endpoint details in the router modules and generated OpenAPI output, not duplicated here.
