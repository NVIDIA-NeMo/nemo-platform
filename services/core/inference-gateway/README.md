<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Inference Gateway Service

The Inference Gateway is the platform's inference proxy. It accepts provider-, model-, OpenAI-compatible-, and VirtualModel-scoped requests, resolves the target backend through Models service state, applies configured inference middleware, and forwards requests to the backend while preserving streaming and response behavior where possible.

The service loads middleware plugins through the `nemo.inference_middleware` entry point group at startup. VirtualModels use that path for routing, translation, guardrail, and other request/response middleware behavior, including plugins such as Switchyard and NeMo Guardrails.

Keep endpoint details in the router modules and generated OpenAPI output, not duplicated here.
