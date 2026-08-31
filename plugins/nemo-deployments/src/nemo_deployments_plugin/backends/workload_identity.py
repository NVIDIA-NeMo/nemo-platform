# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend-neutral deployment workload identity helpers."""

from __future__ import annotations

from nemo_deployments_plugin.entities import DeploymentConfig
from nemo_platform_plugin.auth import AuthContext
from nemo_platform_plugin.auth.workload_identity import is_workload_identity_token_exchange_enabled

DEFAULT_WORKLOAD_KIND = "deployment"


def workload_identity_requested(config: DeploymentConfig) -> bool:
    spec = config.workload_identity
    return spec is not None and spec.enabled


def workload_identity_activation_error(
    *,
    config: DeploymentConfig,
    auth_context: AuthContext | None,
) -> str | None:
    """Return a user-facing error if workload identity cannot be activated."""
    if not workload_identity_requested(config):
        return None
    if not is_workload_identity_token_exchange_enabled():
        return "workload_identity requires auth.oidc.workload_token_exchange_enabled to be enabled"
    if auth_context is None:
        return "workload_identity requires deployment auth_context for on-behalf-of delegation"
    return None


def workload_kind(config: DeploymentConfig) -> str:
    spec = config.workload_identity
    if spec is not None and spec.workload_kind:
        return spec.workload_kind
    return DEFAULT_WORKLOAD_KIND


def workload_id(config: DeploymentConfig, deployment_name: str) -> str:
    spec = config.workload_identity
    if spec is not None and spec.workload_id:
        return spec.workload_id
    return deployment_name
