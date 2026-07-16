# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Executor-level Kubernetes backend configuration."""

from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field, field_validator

_DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")

# Downward-API env var carrying the controller pod's own namespace. The core
# controller deployment (where the deployments backend runs) injects this via
# ``fieldRef: metadata.namespace`` (see k8s/helm/templates/core/controller-deployment.yaml).
_POD_NAMESPACE_ENV = "POD_NAMESPACE"

# Last-resort namespace when neither an explicit config value nor the downward
# API is available (e.g. local/out-of-cluster runs).
_FALLBACK_NAMESPACE = "default"


class K8sExecutorConfig(BaseModel):
    """Knobs for a named k8s executor instance (not entity backend_config)."""

    kubeconfig_path: str | None = Field(
        default=None,
        description="Path to kubeconfig file. When unset, uses in-cluster config or default kubeconfig.",
    )
    default_namespace: str | None = Field(
        default=None,
        min_length=1,
        max_length=63,
        description=(
            "Namespace for resources when entity backend_config.k8s.namespace is unset. When this is "
            "itself unset, the executor defaults to its own pod namespace (POD_NAMESPACE, injected via "
            "the downward API), so a deployed platform places agents beside itself; if that is also "
            "unavailable it falls back to 'default'. See effective_namespace."
        ),
    )
    request_timeout: int = Field(
        default=60,
        ge=1,
        description="Kubernetes API client timeout in seconds.",
    )

    @field_validator("default_namespace")
    @classmethod
    def _validate_default_namespace(cls, value: str | None) -> str | None:
        if value is not None and not _DNS_LABEL_PATTERN.fullmatch(value):
            raise ValueError("default_namespace must be a lowercase DNS-1123 label (alphanumeric, interior hyphens)")
        return value

    @property
    def effective_namespace(self) -> str:
        """Resolve the namespace to deploy into.

        Precedence: an explicit ``default_namespace`` config value wins; else the
        controller's own pod namespace (``POD_NAMESPACE`` downward API); else
        ``"default"``. This lets a deployed platform omit the setting and still
        place agents in its own namespace, while an operator can always pin one.
        """
        if self.default_namespace is not None:
            return self.default_namespace
        pod_namespace = os.environ.get(_POD_NAMESPACE_ENV, "").strip()
        if pod_namespace:
            return pod_namespace
        return _FALLBACK_NAMESPACE
