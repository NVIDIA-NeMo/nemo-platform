# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""JWT validation for native OIDC authentication."""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import jwt
from jwt import PyJWKClient
from nmp.common.config import AuthConfig

logger = logging.getLogger(__name__)

# Cache TTLs for JWTValidator internals.
# JWKS keys are refreshed after this period even for known key IDs,
# ensuring revoked keys are eventually dropped.
_JWKS_CACHE_LIFESPAN = 3600  # 1 hour

# Discovery document is re-fetched after this period so changes to the
# IdP JWKS URI or token endpoint are picked up without a restart.
_DISCOVERY_CACHE_TTL = 3600  # 1 hour


@dataclass
class TokenClaims:
    """Validated token claims."""

    subject: str
    email: Optional[str]
    groups: list[str]
    scopes: list[str]
    raw_claims: dict


class UnsignedJWTRejectedError(Exception):
    """Raised when an unsigned JWT is rejected by configuration."""


class JWTValidator:
    """Validates JWT tokens against an OIDC issuer."""

    def __init__(self, config: AuthConfig):
        self.config = config
        self._jwks_client: Optional[PyJWKClient] = None
        self._discovery_cache: Optional[dict] = None
        self._discovery_cache_time: float = 0.0

    async def _discover_oidc_config(self) -> dict:
        """Fetch OIDC discovery document from issuer.

        Results are cached with a TTL. After expiry the document is
        re-fetched so that changes to the IdP JWKS URI or endpoints
        are eventually picked up without a process restart.
        """
        now = time.monotonic()
        if self._discovery_cache and (now - self._discovery_cache_time) < _DISCOVERY_CACHE_TTL:
            return self._discovery_cache

        discovery_url = f"{self.config.oidc.issuer.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url, timeout=10.0)
            response.raise_for_status()
            self._discovery_cache = response.json()
            self._discovery_cache_time = now
            return self._discovery_cache

    async def _get_jwks_client(self) -> PyJWKClient:
        """Get or create JWKS client for token validation.

        The client is initialized with a lifespan so that cached keys
        are periodically refreshed. This ensures that keys revoked by
        the IdP are eventually dropped even if their key ID was
        previously seen.
        """
        if self._jwks_client:
            return self._jwks_client

        jwks_uri = self.config.oidc.jwks_uri
        if not jwks_uri:
            discovery = await self._discover_oidc_config()
            jwks_uri = discovery["jwks_uri"]

        self._jwks_client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=_JWKS_CACHE_LIFESPAN)
        return self._jwks_client

    def _extract_token_claims(self, claims: dict) -> Optional[TokenClaims]:
        """Extract principal information and scopes from claims."""
        subject = claims.get(self.config.oidc.subject_claim, claims.get("sub"))
        if not isinstance(subject, str) or not subject:
            logger.warning("Token is missing a valid subject claim")
            return None

        email = claims.get(self.config.oidc.email_claim)

        groups: list[str] = []
        for claim_name in [self.config.oidc.groups_claim, "cognito:groups"]:
            if claim_name in claims:
                groups_value = claims[claim_name]
                if isinstance(groups_value, str):
                    groups = [g.strip() for g in groups_value.split(",")]
                elif isinstance(groups_value, list):
                    groups = groups_value
                break

        scopes: list[str] = []
        scope_value = claims.get("scope") or claims.get("scp")
        if scope_value:
            if isinstance(scope_value, str):
                raw_scopes = scope_value.split()
            elif isinstance(scope_value, list):
                raw_scopes = scope_value
            else:
                raw_scopes = []

            prefix = self.config.oidc.scope_prefix
            if prefix:
                scopes = [s[len(prefix) :] if s.startswith(prefix) else s for s in raw_scopes]
            else:
                scopes = raw_scopes

        return TokenClaims(
            subject=subject,
            email=email,
            groups=groups,
            scopes=scopes,
            raw_claims=claims,
        )

    async def validate_token(self, token: str) -> Optional[TokenClaims]:
        """Validate a JWT token and extract claims.

        Args:
            token: The JWT token string to validate.

        Returns:
            TokenClaims if valid, None if invalid or validation fails.
        """
        try:
            token_alg = ""
            try:
                token_header = jwt.get_unverified_header(token)
                token_alg = str(token_header.get("alg", "")).lower()
            except jwt.PyJWTError:
                token_alg = ""

            if token_alg == "none":
                if not self.config.allow_unsigned_jwt:
                    logger.warning("Unsigned JWT rejected: auth.allow_unsigned_jwt is disabled")
                    raise UnsignedJWTRejectedError(
                        "Unsigned JWTs are not accepted. Set auth.allow_unsigned_jwt=true for local development."
                    )

                claims = jwt.decode(
                    token,
                    algorithms=["none"],
                    options={
                        "verify_signature": False,
                        "verify_exp": True,
                        "verify_iat": True,
                        "verify_nbf": True,
                        "verify_aud": False,
                        "verify_iss": False,
                        "require": ["sub", "exp", "iat"],
                    },
                )
                return self._extract_token_claims(claims)

            jwks_client = await self._get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Only validate audience when explicitly configured.
            # When audience is not set, skip the check so tokens from any
            # audience are accepted (the issuer + signature checks are still
            # enforced).
            audience = [self.config.oidc.audience] if self.config.oidc.audience else None

            # Build list of allowed issuers
            allowed_issuers = [self.config.oidc.issuer] + self.config.oidc.additional_issuers

            # Decode and validate token (validate issuer manually to support multiple)
            decode_options: dict = {"require": ["exp", "iat", "sub"]}
            if audience is None:
                decode_options["verify_aud"] = False
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=audience,
                options=decode_options,
            )

            # Validate issuer manually (PyJWT only supports single issuer)
            token_issuer = claims.get("iss", "")
            if token_issuer not in allowed_issuers:
                logger.warning(f"Invalid token issuer: {token_issuer} not in {allowed_issuers}")
                return None
            return self._extract_token_claims(claims)

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except UnsignedJWTRejectedError:
            raise
        except jwt.InvalidAudienceError:
            logger.warning("Invalid token audience")
            return None
        except jwt.InvalidIssuerError:
            logger.warning("Invalid token issuer")
            return None
        except jwt.PyJWTError as e:
            logger.warning(f"Token validation failed: {e}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            return None
