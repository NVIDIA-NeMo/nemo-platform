# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executor-level Kubernetes backend configuration."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class K8sExecutorConfig(BaseModel):
    """Knobs for a named k8s executor instance (not entity backend_config)."""

    kubeconfig_path: str | None = Field(
        default=None,
        description="Path to kubeconfig file. When unset, uses in-cluster config or default kubeconfig.",
    )
    default_namespace: str = Field(
        default="default",
        min_length=1,
        max_length=63,
        description="Namespace for resources when entity backend_config.k8s.namespace is unset.",
    )
    request_timeout: int = Field(
        default=60,
        ge=1,
        description="Kubernetes API client timeout in seconds.",
    )

    @field_validator("default_namespace")
    @classmethod
    def _validate_default_namespace(cls, value: str) -> str:
        if not _DNS_LABEL_PATTERN.fullmatch(value):
            raise ValueError("default_namespace must be a lowercase DNS-1123 label (alphanumeric, interior hyphens)")
        return value
