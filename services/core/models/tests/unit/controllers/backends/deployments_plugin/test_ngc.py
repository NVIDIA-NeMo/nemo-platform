# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for NGC API key resolution used by NIM deployments."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nemo_platform_plugin.client.errors import NotFoundError
from nemo_platform_plugin.secrets.ngc import resolve_ngc_api_key


def _not_found() -> NotFoundError:
    request = httpx.Request("GET", "http://test/secrets")
    return NotFoundError(httpx.Response(404, request=request, text="missing"))


@pytest.mark.asyncio
async def test_resolve_ngc_api_key_from_secret() -> None:
    sdk = MagicMock()
    secrets = AsyncMock()
    access_response = MagicMock()
    access_response.data.return_value = SimpleNamespace(value="from-secret")
    secrets.access_secret = AsyncMock(return_value=access_response)

    with (
        patch(
            "nemo_platform_plugin.secrets.ngc.get_platform_config",
            return_value=SimpleNamespace(ngc_api_key_secret="system/ngc-api-key", ngc_api_key_env_var="NGC_API_KEY"),
        ),
        patch(
            "nemo_platform_plugin.secrets.ngc.client_from_platform",
            return_value=secrets,
        ),
    ):
        assert await resolve_ngc_api_key(sdk) == "from-secret"
    secrets.access_secret.assert_awaited_once_with(name="ngc-api-key", workspace="system")


@pytest.mark.asyncio
async def test_resolve_ngc_api_key_falls_back_to_env_when_secret_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = MagicMock()
    secrets = AsyncMock()
    access_response = MagicMock()
    access_response.data.return_value = SimpleNamespace(value="")
    secrets.access_secret = AsyncMock(return_value=access_response)
    monkeypatch.setenv("NGC_API_KEY", "from-env")

    with (
        patch(
            "nemo_platform_plugin.secrets.ngc.get_platform_config",
            return_value=SimpleNamespace(ngc_api_key_secret="system/ngc-api-key", ngc_api_key_env_var="NGC_API_KEY"),
        ),
        patch(
            "nemo_platform_plugin.secrets.ngc.client_from_platform",
            return_value=secrets,
        ),
    ):
        assert await resolve_ngc_api_key(sdk) == "from-env"


@pytest.mark.asyncio
async def test_resolve_ngc_api_key_falls_back_to_env_when_secret_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = MagicMock()
    secrets = AsyncMock()
    secrets.access_secret.side_effect = _not_found()
    monkeypatch.setenv("NGC_API_KEY", "from-env")

    with (
        patch(
            "nemo_platform_plugin.secrets.ngc.get_platform_config",
            return_value=SimpleNamespace(ngc_api_key_secret="system/ngc-api-key", ngc_api_key_env_var="NGC_API_KEY"),
        ),
        patch(
            "nemo_platform_plugin.secrets.ngc.client_from_platform",
            return_value=secrets,
        ),
    ):
        assert await resolve_ngc_api_key(sdk) == "from-env"


@pytest.mark.asyncio
async def test_resolve_ngc_api_key_returns_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = MagicMock()
    secrets = AsyncMock()
    secrets.access_secret.side_effect = _not_found()
    monkeypatch.delenv("NGC_API_KEY", raising=False)

    with (
        patch(
            "nemo_platform_plugin.secrets.ngc.get_platform_config",
            return_value=SimpleNamespace(ngc_api_key_secret="system/ngc-api-key", ngc_api_key_env_var="NGC_API_KEY"),
        ),
        patch(
            "nemo_platform_plugin.secrets.ngc.client_from_platform",
            return_value=secrets,
        ),
    ):
        assert await resolve_ngc_api_key(sdk) is None
