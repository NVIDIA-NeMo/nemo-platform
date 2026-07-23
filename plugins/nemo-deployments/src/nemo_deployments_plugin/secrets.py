# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve Platform secret references at substrate execution boundaries."""

from __future__ import annotations

import os

from nemo_deployments_plugin.entities import DeploymentConfig, EnvVar, SecretRef
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import NemoClientError, NotFoundError
from nemo_platform_plugin.config import get_platform_config
from nemo_platform_plugin.secrets.client import AsyncSecretsClient


class SecretResolutionError(RuntimeError):
    """A required environment secret could not be resolved."""


def platform_ngc_secret_ref() -> SecretRef | None:
    """Return the configured NGC secret reference without reading its value."""
    config = get_platform_config()
    parts = config.ngc_api_key_secret.strip().split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return SecretRef(workspace=parts[0], name=parts[1])


async def resolve_secret_ref(sdk: AsyncNeMoPlatform, secret_ref: SecretRef) -> str | None:
    """Resolve a Platform secret value without logging reference or value data."""
    try:
        secrets = client_from_platform(sdk, AsyncSecretsClient)
        response = (await secrets.access_secret(name=secret_ref.name, workspace=secret_ref.workspace)).data()
        if response.value:
            return response.value
    except NotFoundError:
        return None
    except NemoClientError as exc:
        raise SecretResolutionError("Platform secret access failed") from exc
    return None


async def resolve_deployment_config_secrets(sdk: AsyncNeMoPlatform, config: DeploymentConfig) -> DeploymentConfig:
    """Return an execution-only copy whose secret references have resolved values."""
    resolved = config.model_copy(deep=True)
    for container in (*resolved.init_containers, *resolved.containers):
        env: list[EnvVar] = []
        for item in container.env:
            resolved_item = await _resolve_env_var(sdk, item)
            if resolved_item is not None:
                env.append(resolved_item)
        container.env = env
    return resolved


async def _resolve_env_var(sdk: AsyncNeMoPlatform, item: EnvVar) -> EnvVar | None:
    """Resolve an authorized secret-backed environment variable.

    NGC credentials are best-effort: when neither the configured secret nor the
    process-environment fallback is available, omit the variable so mock/local
    NIM images can still start. Unauthorized references and secret-service
    access failures remain hard errors.
    """
    if item.secret_ref is None:
        return item
    ngc_secret_ref = platform_ngc_secret_ref()
    if item.name != "NGC_API_KEY" or item.secret_ref != ngc_secret_ref:
        raise SecretResolutionError(f"Unsupported secret reference for environment variable {item.name!r}")
    value = await resolve_secret_ref(sdk, item.secret_ref)
    if value is None:
        value = os.environ.get(get_platform_config().ngc_api_key_env_var)
    if value is None:
        return None
    return EnvVar(name=item.name, value=value)
