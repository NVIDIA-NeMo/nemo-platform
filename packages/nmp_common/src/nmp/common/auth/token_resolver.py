# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from nmp.common.config import AuthConfig

from .jwt import JWTValidator, TokenClaims
from .models import Principal

ResolvedTokenKind = Literal["access_key", "oidc_access_token", "workload_access_token", "workload_subject_token"]


@dataclass(frozen=True)
class ResolvedBearerToken:
    claims: TokenClaims
    token_kind: ResolvedTokenKind

    @property
    def principal(self) -> Principal:
        return Principal(
            id=self.claims.subject,
            email=self.claims.email,
            groups=self.claims.groups,
        )

    @property
    def scopes(self) -> list[str]:
        return self.claims.scopes

    def principal_headers(self) -> dict[str, str]:
        headers = self.principal.get_headers()
        if self.scopes:
            headers["X-NMP-Scopes"] = " ".join(self.scopes)
        return headers


ExtraBearerTokenResolver = Callable[[str], Awaitable[ResolvedBearerToken | None]]


async def resolve_bearer_token(
    config: AuthConfig,
    token: str,
    *,
    jwt_validator: JWTValidator | None = None,
    extra_resolvers: Sequence[ExtraBearerTokenResolver] = (),
    skip_access_key_check: bool = False,
) -> ResolvedBearerToken | None:
    if config.access_keys.enabled and not skip_access_key_check:
        from .access_keys import validate_access_key_token

        access_key_claims = await validate_access_key_token(config, token)
        if access_key_claims is not None:
            return ResolvedBearerToken(claims=access_key_claims, token_kind="access_key")

    for extra_resolver in extra_resolvers:
        resolved = await extra_resolver(token)
        if resolved is not None:
            return resolved

    if not config.oidc.enabled and not config.allow_unsigned_jwt:
        return None

    validator = jwt_validator or JWTValidator(config)
    oidc_claims = await validator.validate_token(token)
    if oidc_claims is None:
        return None
    return ResolvedBearerToken(claims=oidc_claims, token_kind="oidc_access_token")
