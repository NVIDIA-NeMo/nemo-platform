# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nmp.common.auth.jwt import TokenClaims
from nmp.common.auth.token_resolver import ResolvedBearerToken, resolve_bearer_token
from nmp.common.config import AuthConfig
from nmp.common.config.base import AccessKeyConfig, OIDCConfig


def _claims(subject: str = "alice@example.com") -> TokenClaims:
    return TokenClaims(
        subject=subject,
        email=subject,
        groups=["team-ml"],
        scopes=["models:read"],
        raw_claims={"jti": "ak_example"},
    )


@pytest.mark.asyncio
async def test_resolver_skips_access_key_validator_when_access_keys_are_disabled() -> None:
    config = AuthConfig(
        enabled=True,
        access_keys=AccessKeyConfig(enabled=False),
        oidc=OIDCConfig(enabled=False),
    )

    with patch("nmp.common.auth.access_keys.validate_access_key_token") as validate_access_key:
        resolved = await resolve_bearer_token(config, "bearer-token")

    assert resolved is None
    validate_access_key.assert_not_called()


@pytest.mark.asyncio
async def test_resolver_uses_access_key_validator_when_access_keys_are_enabled() -> None:
    config = AuthConfig(
        enabled=True,
        access_keys=AccessKeyConfig(enabled=True),
        oidc=OIDCConfig(enabled=False),
    )
    claims = _claims()

    with patch(
        "nmp.common.auth.access_keys.validate_access_key_token",
        new=AsyncMock(return_value=claims),
    ) as validate_access_key:
        resolved = await resolve_bearer_token(config, "scoped-access-key")

    assert resolved == ResolvedBearerToken(claims=claims, token_kind="access_key")
    assert resolved is not None
    assert resolved.principal.id == "alice@example.com"
    assert resolved.principal_headers() == {
        "X-NMP-Principal-Id": "alice@example.com",
        "X-NMP-Principal-Email": "alice@example.com",
        "X-NMP-Principal-Groups": "team-ml",
        "X-NMP-Scopes": "models:read",
    }
    validate_access_key.assert_awaited_once_with(config, "scoped-access-key")


@pytest.mark.asyncio
async def test_resolver_uses_extra_resolvers_before_oidc() -> None:
    config = AuthConfig(
        enabled=True,
        access_keys=AccessKeyConfig(enabled=False),
        oidc=OIDCConfig(enabled=True, issuer="https://sso.example.com", client_id="nemo-platform-cli"),
    )
    workload_claims = _claims("system:serviceaccount:nemo:job")
    extra_resolver = AsyncMock(
        return_value=ResolvedBearerToken(
            claims=workload_claims,
            token_kind="workload_access_token",
        )
    )
    jwt_validator = MagicMock()

    resolved = await resolve_bearer_token(
        config,
        "workload-token",
        jwt_validator=jwt_validator,
        extra_resolvers=[extra_resolver],
    )

    assert resolved == ResolvedBearerToken(claims=workload_claims, token_kind="workload_access_token")
    extra_resolver.assert_awaited_once_with("workload-token")
    jwt_validator.validate_token.assert_not_called()


@pytest.mark.asyncio
async def test_resolver_falls_back_to_oidc_validator() -> None:
    config = AuthConfig(
        enabled=True,
        access_keys=AccessKeyConfig(enabled=True),
        oidc=OIDCConfig(enabled=True, issuer="https://sso.example.com", client_id="nemo-platform-cli"),
    )
    oidc_claims = _claims("bob@example.com")
    jwt_validator = MagicMock()
    jwt_validator.validate_token = AsyncMock(return_value=oidc_claims)

    with patch(
        "nmp.common.auth.access_keys.validate_access_key_token",
        new=AsyncMock(return_value=None),
    ):
        resolved = await resolve_bearer_token(config, "oidc-token", jwt_validator=jwt_validator)

    assert resolved == ResolvedBearerToken(claims=oidc_claims, token_kind="oidc_access_token")
    jwt_validator.validate_token.assert_awaited_once_with("oidc-token")
