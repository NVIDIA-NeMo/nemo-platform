# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executor-level Kubernetes backend configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class K8sExecutorConfig(BaseModel):
    """Knobs for a named k8s executor instance (not entity backend_config)."""

    kubeconfig_path: str | None = Field(
        default=None,
        description="Path to kubeconfig file. When unset, uses in-cluster config or default kubeconfig.",
    )
    default_namespace: str = Field(
        default="default",
        min_length=1,
        description="Namespace for resources when entity backend_config.k8s.namespace is unset.",
    )
    request_timeout: int = Field(
        default=60,
        ge=1,
        description="Kubernetes API client timeout in seconds.",
    )
