# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for auth-service Scoped Access Key lifecycle validation."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nmp.common.auth.access_key_lifecycle import (
    AccessKeyLifecycleAuthenticator,
    AccessKeyLifecycleUnavailableError,
)
from nmp.common.auth.token_resolver import ResolvedBearerToken
from nmp.common.config import AuthConfig, Configuration, PlatformConfig


def _config() -> AuthConfig:
    return AuthConfig(policy_decision_point_request_timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_authenticator_uses_injected_client_and_returns_trusted_claims() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "principal": "alice@example.com",
                "email": "alice@example.com",
                "groups": ["team-ml"],
                "scopes": ["models:read"],
                "jti": "ak_example",
                "token_kind": "access_key",
            },
        )

    platform_config = PlatformConfig(
        base_url="http://platform.example.com",
        service_discovery={"auth": "http://auth.internal:8080"},
        services="",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with patch.object(Configuration, "get_platform_config", return_value=platform_config):
            result = await authenticator.authenticate("scoped-access-key")

    assert isinstance(result, ResolvedBearerToken)
    assert result.claims.subject == "alice@example.com"
    assert result.claims.groups == ["team-ml"]
    assert result.claims.scopes == ["models:read"]
    assert requests[0].url == httpx.URL("http://platform.example.com/apis/auth/authenticate")


@pytest.mark.asyncio
async def test_aclose_closes_owned_sdk() -> None:
    sdk = MagicMock()
    sdk.close = AsyncMock()
    authenticator = AccessKeyLifecycleAuthenticator(_config())
    authenticator._sdk = sdk

    await authenticator.aclose()

    sdk.close.assert_awaited_once_with()
    assert authenticator._sdk is None


@pytest.mark.asyncio
async def test_aclose_does_not_close_sdk_with_injected_http_client() -> None:
    sdk = MagicMock()
    sdk.close = AsyncMock()
    async with httpx.AsyncClient() as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        authenticator._sdk = sdk

        await authenticator.aclose()

    sdk.close.assert_not_awaited()
    assert authenticator._sdk is None


@pytest.mark.asyncio
@pytest.mark.parametrize("token_kind", ["oidc_access_token", "workload_access_token", "workload_subject_token"])
async def test_authenticator_rejects_successful_non_access_key_response(token_kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "principal": "alice@example.com",
                "groups": [],
                "scopes": [],
                "token_kind": token_kind,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with patch.object(
            Configuration,
            "get_platform_config",
            return_value=PlatformConfig(base_url="http://platform.example.com", services=""),
        ):
            assert await authenticator.authenticate("candidate-token") is None


@pytest.mark.asyncio
async def test_authenticator_can_accept_workload_token_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "principal": "system:serviceaccount:nemo:job",
                "groups": ["team-ml"],
                "scopes": ["openid", "email"],
                "token_kind": "workload_access_token",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with patch.object(
            Configuration,
            "get_platform_config",
            return_value=PlatformConfig(base_url="http://platform.example.com", services=""),
        ):
            result = await authenticator.authenticate_token(
                "workload-access-token",
                token_kinds=("workload_access_token",),
            )

    assert isinstance(result, ResolvedBearerToken)
    assert result.token_kind == "workload_access_token"
    assert result.claims.subject == "system:serviceaccount:nemo:job"
    assert result.claims.groups == ["team-ml"]
    assert result.claims.raw_claims["nmp_token_type"] == "workload_access_token"
    assert "jti" not in result.claims.raw_claims


@pytest.mark.asyncio
async def test_authenticator_rejects_malformed_sdk_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "principal": 123,
                "groups": [],
                "scopes": [],
                "jti": "ak_example",
                "token_kind": "access_key",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with (
            patch.object(
                Configuration,
                "get_platform_config",
                return_value=PlatformConfig(base_url="http://platform.example.com", services=""),
            ),
            pytest.raises(AccessKeyLifecycleUnavailableError) as exc_info,
        ):
            await authenticator.authenticate("candidate-token")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_authenticator_returns_none_when_auth_service_rejects_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request, json={"detail": "Invalid bearer token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with patch.object(
            Configuration,
            "get_platform_config",
            return_value=PlatformConfig(base_url="http://platform.example.com", services=""),
        ):
            assert await authenticator.authenticate("rejected-token") is None


@pytest.mark.asyncio
async def test_authenticator_rejects_access_key_response_without_jti() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "principal": "alice@example.com",
                "groups": [],
                "scopes": [],
                "token_kind": "access_key",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with (
            patch.object(
                Configuration,
                "get_platform_config",
                return_value=PlatformConfig(base_url="http://platform.example.com", services=""),
            ),
            pytest.raises(AccessKeyLifecycleUnavailableError) as exc_info,
        ):
            await authenticator.authenticate("candidate-token")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_authenticator_maps_transport_timeout_to_gateway_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with (
            patch.object(
                Configuration,
                "get_platform_config",
                return_value=PlatformConfig(base_url="http://platform.example.com", services=""),
            ),
            pytest.raises(AccessKeyLifecycleUnavailableError) as exc_info,
        ):
            await authenticator.authenticate("candidate-token")

    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_authenticator_opens_circuit_and_recovers_after_window() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count <= 3:
            return httpx.Response(500, request=request, json={"detail": "auth unavailable"})
        return httpx.Response(
            200,
            request=request,
            json={
                "principal": "alice@example.com",
                "groups": [],
                "scopes": [],
                "jti": "ak_example",
                "token_kind": "access_key",
            },
        )

    monotonic_now = 0.0

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        authenticator = AccessKeyLifecycleAuthenticator(_config(), http_client=http_client)
        with (
            patch.object(
                Configuration,
                "get_platform_config",
                return_value=PlatformConfig(base_url="http://platform.example.com", services=""),
            ),
            patch("nmp.common.auth.access_key_lifecycle.time.monotonic", side_effect=lambda: monotonic_now),
        ):
            for expected_retry_after in (None, None, 5):
                with pytest.raises(AccessKeyLifecycleUnavailableError) as exc_info:
                    await authenticator.authenticate("candidate-token")
                assert exc_info.value.retry_after == expected_retry_after

            with pytest.raises(AccessKeyLifecycleUnavailableError) as exc_info:
                await authenticator.authenticate("candidate-token")
            assert exc_info.value.status_code == 503
            assert exc_info.value.retry_after == 5
            assert request_count == 3

            monotonic_now = 6.0
            result = await authenticator.authenticate("candidate-token")

    assert isinstance(result, ResolvedBearerToken)
    assert request_count == 4
