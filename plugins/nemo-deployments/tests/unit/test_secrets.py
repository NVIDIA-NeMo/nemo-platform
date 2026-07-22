# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for execution-time Platform secret resolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nemo_deployments_plugin.entities import Container, DeploymentConfig, EnvVar, SecretRef
from nemo_deployments_plugin.secrets import (
    SecretResolutionError,
    platform_ngc_secret_ref,
    resolve_deployment_config_secrets,
)
from nemo_platform_plugin.client.errors import NemoClientError, NotFoundError


def _config(secret_ref: SecretRef, *, env_name: str = "NGC_API_KEY") -> DeploymentConfig:
    return DeploymentConfig(
        name="cfg",
        workspace="default",
        containers=[
            Container(
                name="server",
                image="nvcr.io/nim/test:latest",
                env=[EnvVar(name=env_name, secretRef=secret_ref)],
            )
        ],
    )


def _not_found() -> NotFoundError:
    request = httpx.Request("GET", "http://test/secrets")
    return NotFoundError(httpx.Response(404, request=request, text="missing"))


def test_env_var_rejects_plaintext_and_secret_reference_together() -> None:
    with pytest.raises(ValueError, match="only one"):
        EnvVar(
            name="NGC_API_KEY",
            value="must-not-be-stored",
            secretRef=SecretRef(workspace="system", name="ngc-api-key"),
        )


def test_platform_ngc_secret_ref_contains_reference_and_fallback_name_only() -> None:
    config = SimpleNamespace(
        ngc_api_key_secret="system/ngc-api-key",
        ngc_api_key_env_var="NGC_API_KEY",
    )
    with patch("nemo_deployments_plugin.secrets.get_platform_config", return_value=config):
        secret_ref = platform_ngc_secret_ref()

    assert secret_ref == SecretRef(
        workspace="system",
        name="ngc-api-key",
    )


@pytest.mark.asyncio
async def test_resolve_deployment_config_secrets_keeps_stored_config_reference_only() -> None:
    original = _config(SecretRef(workspace="system", name="ngc-api-key"))
    response = MagicMock()
    response.data.return_value = SimpleNamespace(value="resolved-value")
    secrets = AsyncMock()
    secrets.access_secret.return_value = response

    platform = SimpleNamespace(
        ngc_api_key_secret="system/ngc-api-key",
        ngc_api_key_env_var="NGC_API_KEY",
    )
    with (
        patch("nemo_deployments_plugin.secrets.client_from_platform", return_value=secrets),
        patch("nemo_deployments_plugin.secrets.get_platform_config", return_value=platform),
    ):
        resolved = await resolve_deployment_config_secrets(MagicMock(), original)

    assert original.containers[0].env[0].value is None
    assert original.containers[0].env[0].secret_ref == SecretRef(workspace="system", name="ngc-api-key")
    assert "resolved-value" not in original.model_dump_json(by_alias=True)
    assert resolved.containers[0].env[0].value == "resolved-value"
    assert resolved.containers[0].env[0].secret_ref is None


@pytest.mark.asyncio
async def test_resolve_deployment_config_secrets_uses_environment_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(SecretRef(workspace="system", name="ngc-api-key"))
    secrets = AsyncMock()
    secrets.access_secret.side_effect = _not_found()
    monkeypatch.setenv("NGC_API_KEY", "fallback-value")

    platform = SimpleNamespace(
        ngc_api_key_secret="system/ngc-api-key",
        ngc_api_key_env_var="NGC_API_KEY",
    )
    with (
        patch("nemo_deployments_plugin.secrets.client_from_platform", return_value=secrets),
        patch("nemo_deployments_plugin.secrets.get_platform_config", return_value=platform),
    ):
        resolved = await resolve_deployment_config_secrets(MagicMock(), config)

    assert resolved.containers[0].env[0].value == "fallback-value"


@pytest.mark.asyncio
async def test_resolve_deployment_config_secrets_fails_without_value() -> None:
    config = _config(SecretRef(workspace="system", name="ngc-api-key"))
    secrets = AsyncMock()
    secrets.access_secret.side_effect = _not_found()

    platform = SimpleNamespace(
        ngc_api_key_secret="system/ngc-api-key",
        ngc_api_key_env_var="NGC_API_KEY",
    )
    with (
        patch("nemo_deployments_plugin.secrets.client_from_platform", return_value=secrets),
        patch("nemo_deployments_plugin.secrets.get_platform_config", return_value=platform),
        pytest.raises(SecretResolutionError, match="NGC_API_KEY"),
    ):
        await resolve_deployment_config_secrets(MagicMock(), config)


@pytest.mark.asyncio
async def test_secret_access_error_does_not_fall_back_to_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(SecretRef(workspace="system", name="ngc-api-key"))
    secrets = AsyncMock()
    secrets.access_secret.side_effect = NemoClientError("access denied")
    monkeypatch.setenv("NGC_API_KEY", "must-not-be-used")
    platform = SimpleNamespace(
        ngc_api_key_secret="system/ngc-api-key",
        ngc_api_key_env_var="NGC_API_KEY",
    )

    with (
        patch("nemo_deployments_plugin.secrets.client_from_platform", return_value=secrets),
        patch("nemo_deployments_plugin.secrets.get_platform_config", return_value=platform),
        pytest.raises(SecretResolutionError, match="access failed"),
    ):
        await resolve_deployment_config_secrets(MagicMock(), config)


@pytest.mark.asyncio
async def test_resolve_deployment_config_secrets_rejects_untrusted_reference() -> None:
    config = _config(
        SecretRef(workspace="system", name="unrelated-secret"),
        env_name="EXFILTRATED_VALUE",
    )
    platform = SimpleNamespace(
        ngc_api_key_secret="system/ngc-api-key",
        ngc_api_key_env_var="NGC_API_KEY",
    )

    with (
        patch("nemo_deployments_plugin.secrets.get_platform_config", return_value=platform),
        pytest.raises(SecretResolutionError, match="Unsupported"),
    ):
        await resolve_deployment_config_secrets(MagicMock(), config)
