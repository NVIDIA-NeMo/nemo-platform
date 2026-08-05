# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
import nmp.common.auth.access_keys as access_keys_mod
import nmp.common.auth.signing_keys as signing_keys_mod
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from nemo_platform_plugin.auth.access_keys.issuer import AccessKeyFeatureDisabledError
from nemo_platform_plugin.auth.access_keys.types import AccessKeyCreateRequest
from nmp.common import http_clients
from nmp.common.auth.access_keys import (
    ACCESS_KEY_TOKEN_TYPE,
    AccessKeyIssuerService,
    access_key_jwks_uri,
    clear_access_key_signing_key_cache,
    public_jwk_from_private_key_pem,
    public_jwk_from_private_key_pem_async,
    validate_access_key_token,
)
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig
from nmp.common.config.base import AccessKeyConfig, TokenSigningConfig
from pydantic import ValidationError


def test_token_signing_defaults_are_shared_and_access_keys_are_disabled():
    config = AuthConfig()

    assert config.token_signing.issuer is None
    assert config.token_signing.key_id == "nemo-platform-signing"
    assert config.token_signing.private_key_file is None
    assert config.access_keys.enabled is False
    assert config.access_keys.issue_format == "jwt"
    assert config.access_keys.accepted_formats == ["jwt"]
    assert config.access_keys.audience == "nemo-platform-access-key"
    assert config.access_keys.default_expires_in_seconds == 30 * 24 * 60 * 60
    assert config.access_keys.max_expires_in_seconds == 30 * 24 * 60 * 60


def test_access_key_jwks_uri_uses_canonical_auth_jwks_path() -> None:
    jwks_uri = access_key_jwks_uri(AuthConfig())

    assert jwks_uri.endswith("/apis/auth/jwks")
    assert "/access-keys/" not in jwks_uri


def test_token_signing_private_key_file_uses_auth_service_env_override(monkeypatch):
    monkeypatch.setenv(
        "NMP_AUTH_TOKEN_SIGNING__PRIVATE_KEY_FILE",
        "/var/run/secrets/nemo-platform/token-signing/private.pem",
    )

    config = AuthConfig()

    assert config.token_signing.private_key_file == "/var/run/secrets/nemo-platform/token-signing/private.pem"


def test_workload_private_key_file_uses_auth_service_env_override(monkeypatch):
    monkeypatch.setenv(
        "NMP_AUTH_OIDC__WORKLOAD_TOKEN_PRIVATE_KEY_FILE",
        "/var/run/secrets/nemo-platform/workload-token-signing/private-key.pem",
    )

    config = AuthConfig()

    assert (
        config.oidc.workload_token_private_key_file
        == "/var/run/secrets/nemo-platform/workload-token-signing/private-key.pem"
    )


def test_nested_auth_env_vars_use_double_underscore_delimiter(monkeypatch):
    monkeypatch.setenv("NMP_AUTH_TOKEN_SIGNING__KEY_ID", "custom-signing-key")
    monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__ENABLED", "true")

    config = AuthConfig()

    assert config.token_signing.key_id == "custom-signing-key"
    assert config.access_keys.enabled is True


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("jwt", ["jwt"]),
    ],
)
def test_access_key_accepted_formats_uses_auth_service_env_override(monkeypatch, env_value, expected):
    monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__ACCEPTED_FORMATS", env_value)

    config = AuthConfig()

    assert config.access_keys.accepted_formats == expected


@pytest.mark.parametrize("env_value", ["jwt,opaque", "opaque", "jwt,unknown"])
def test_access_key_accepted_formats_env_override_rejects_unsupported_format(monkeypatch, env_value):
    monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__ACCEPTED_FORMATS", env_value)

    with pytest.raises(ValidationError):
        AuthConfig()


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("3600", 3600),
        ("null", None),
        ("none", None),
        ("", None),
    ],
)
def test_access_key_max_expires_in_seconds_uses_auth_service_env_override(monkeypatch, env_value, expected):
    monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__MAX_EXPIRES_IN_SECONDS", env_value)
    if expected is not None and expected < 30 * 24 * 60 * 60:
        monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__DEFAULT_EXPIRES_IN_SECONDS", env_value)

    config = AuthConfig()

    assert config.access_keys.max_expires_in_seconds == expected


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("3600", 3600),
        ("null", None),
        ("none", None),
        ("", None),
    ],
)
def test_access_key_default_expires_in_seconds_uses_auth_service_env_override(monkeypatch, env_value, expected):
    monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__DEFAULT_EXPIRES_IN_SECONDS", env_value)
    if expected is None:
        monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__MAX_EXPIRES_IN_SECONDS", "none")

    config = AuthConfig()

    assert config.access_keys.default_expires_in_seconds == expected


def test_access_key_max_expires_in_seconds_env_override_rejects_zero(monkeypatch):
    monkeypatch.setenv("NMP_AUTH_ACCESS_KEYS__MAX_EXPIRES_IN_SECONDS", "0")

    with pytest.raises(ValidationError):
        AuthConfig()


def test_access_key_default_expiry_must_not_exceed_finite_max() -> None:
    with pytest.raises(ValueError, match="default_expires_in_seconds"):
        AccessKeyConfig(default_expires_in_seconds=3600, max_expires_in_seconds=60)


def test_access_key_default_expiry_can_be_none_when_max_is_finite() -> None:
    config = AccessKeyConfig(default_expires_in_seconds=None, max_expires_in_seconds=60)

    assert config.default_expires_in_seconds is None
    assert config.max_expires_in_seconds == 60


def test_access_key_default_expiry_can_be_none_when_max_is_disabled() -> None:
    config = AccessKeyConfig(default_expires_in_seconds=None, max_expires_in_seconds=None)

    assert config.default_expires_in_seconds is None
    assert config.max_expires_in_seconds is None


def _private_key_pem() -> bytes:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _access_key_config(
    tmp_path,
    *,
    default_expires_in_seconds: int | None = 30 * 24 * 60 * 60,
    max_expires_in_seconds: int | None = 30 * 24 * 60 * 60,
):
    key_path = tmp_path / "access-key-private.pem"
    key_path.write_bytes(_private_key_pem())
    return AuthConfig(
        enabled=True,
        token_signing=TokenSigningConfig(
            issuer="https://nmp.example.test/apis/auth",
            key_id="test-access-key",
            private_key_file=str(key_path),
        ),
        access_keys=AccessKeyConfig(
            enabled=True,
            audience="nemo-platform-access-key",
            default_expires_in_seconds=default_expires_in_seconds,
            max_expires_in_seconds=max_expires_in_seconds,
        ),
    )


def test_access_key_public_jwk_uses_cached_private_key_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key_file = tmp_path / "access-key-private.pem"
    private_key_file.write_bytes(_private_key_pem())
    config = AuthConfig(
        token_signing=TokenSigningConfig(
            key_id="access-key",
            private_key_file=str(private_key_file),
        ),
        access_keys=AccessKeyConfig(enabled=True),
    )
    clear_access_key_signing_key_cache()
    original_load = signing_keys_mod._load_rsa_signing_key_async
    load_count = 0

    async def counted_load(**kwargs: Any) -> signing_keys_mod.RSASigningKey:
        nonlocal load_count
        load_count += 1
        return await original_load(**kwargs)

    monkeypatch.setattr(signing_keys_mod, "_load_rsa_signing_key_async", counted_load)

    first = public_jwk_from_private_key_pem(config)
    second = public_jwk_from_private_key_pem(config)

    assert first == second
    assert first["kid"] == "access-key"
    assert load_count == 1


def test_access_key_private_key_uses_cached_private_key_file_for_token_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key_file = tmp_path / "access-key-private.pem"
    private_key_file.write_bytes(_private_key_pem())
    config = AuthConfig(
        token_signing=TokenSigningConfig(
            issuer="http://testserver/apis/auth",
            key_id="access-key",
            private_key_file=str(private_key_file),
        ),
        access_keys=AccessKeyConfig(enabled=True),
    )
    principal = Principal(id="alice@example.com", email="alice@example.com", groups=[])
    clear_access_key_signing_key_cache()
    original_load = signing_keys_mod._load_rsa_signing_key_async
    load_count = 0

    async def counted_load(**kwargs: Any) -> signing_keys_mod.RSASigningKey:
        nonlocal load_count
        load_count += 1
        return await original_load(**kwargs)

    monkeypatch.setattr(signing_keys_mod, "_load_rsa_signing_key_async", counted_load)

    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1_785_280_000)
    issuer.create(AccessKeyCreateRequest(name="first", expires_in_seconds=600))
    issuer.create(AccessKeyCreateRequest(name="second", expires_in_seconds=600))

    assert load_count == 1


def test_access_key_issuer_service_stamps_current_principal(tmp_path):
    config = _access_key_config(tmp_path)
    principal = Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"])
    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1785280000)

    created = issuer.create(
        AccessKeyCreateRequest(
            name="gtc-intake",
            description="GTC intake automation",
            expires_in_seconds=600,
        )
    )
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    assert created.jti.startswith("ak_")
    assert created.name == "gtc-intake"
    assert created.description == "GTC intake automation"
    assert created.principal == "alice@example.com"
    assert created.expires_at == datetime.fromtimestamp(1785280600, tz=UTC)
    assert unverified["jti"] == created.jti
    assert unverified["sub"] == "alice@example.com"
    assert unverified["email"] == "alice@example.com"
    assert unverified["groups"] == "team-ml"
    assert unverified["aud"] == "nemo-platform-access-key"
    assert unverified["nmp_token_type"] == ACCESS_KEY_TOKEN_TYPE
    assert unverified["nmp_access_key"] == {
        "version": 2,
        "name": "gtc-intake",
    }
    assert unverified["exp"] == 1785280600


def test_access_key_issuer_service_serializes_groups_for_gateway_header(tmp_path):
    config = _access_key_config(tmp_path)
    principal = Principal(
        id="system:serviceaccounts:nemo-authentik",
        groups=["system:serviceaccounts", "system:serviceaccounts:nemo-authentik", "system:authenticated"],
    )
    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1785280000)

    created = issuer.create(AccessKeyCreateRequest(name="kubernetes-workload", expires_in_seconds=600))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    assert unverified["groups"] == "system:serviceaccounts,system:serviceaccounts:nemo-authentik,system:authenticated"


def test_access_key_issuer_service_allows_unnamed_tokens(tmp_path):
    config = _access_key_config(tmp_path)
    principal = Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"])
    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1785280000)

    created = issuer.create(AccessKeyCreateRequest(expires_in_seconds=600))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    assert created.jti.startswith("ak_")
    assert created.name is None
    assert unverified["jti"] == created.jti
    assert unverified["nmp_access_key"] == {"version": 2}
    assert unverified["exp"] == 1785280600


def test_access_key_issuer_service_respects_disabled_config(tmp_path):
    base_config = _access_key_config(tmp_path)
    config = base_config.model_copy(
        update={"access_keys": base_config.access_keys.model_copy(update={"enabled": False})}
    )
    principal = Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"])
    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1785280000)

    with pytest.raises(AccessKeyFeatureDisabledError, match="not enabled"):
        issuer.create(AccessKeyCreateRequest())


def test_access_key_issuer_service_rejects_expiration_above_configured_max(tmp_path):
    config = _access_key_config(tmp_path)
    config = config.model_copy(
        update={"access_keys": config.access_keys.model_copy(update={"max_expires_in_seconds": 60})}
    )
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    with pytest.raises(RuntimeError, match="max_expires_in_seconds"):
        issuer.create(AccessKeyCreateRequest(name="too-long", expires_in_seconds=61))


def test_access_key_issuer_service_defaults_omitted_expiration_to_config_default(tmp_path):
    config = _access_key_config(tmp_path)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    created = issuer.create(AccessKeyCreateRequest(name="default-expiry"))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    expected_exp = 1785280000 + 30 * 24 * 60 * 60
    assert unverified["exp"] == expected_exp
    assert created.expires_at == datetime.fromtimestamp(expected_exp, tz=UTC)


def test_access_key_issuer_service_rejects_explicit_null_expiration_when_max_configured(tmp_path):
    config = _access_key_config(tmp_path)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    with pytest.raises(RuntimeError, match="expires_in_seconds=null requires"):
        issuer.create(AccessKeyCreateRequest(name="unlimited", expires_in_seconds=None))


def test_access_key_issuer_service_defaults_expiration_when_max_disabled(tmp_path):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    created = issuer.create(AccessKeyCreateRequest(name="default-even-without-max"))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    expected_exp = 1785280000 + 30 * 24 * 60 * 60
    assert unverified["exp"] == expected_exp
    assert created.expires_at == datetime.fromtimestamp(expected_exp, tz=UTC)


def test_access_key_issuer_service_allows_explicit_null_expiration_when_max_disabled(tmp_path):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    created = issuer.create(AccessKeyCreateRequest(name="long-lived", expires_in_seconds=None))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    assert created.expires_at is None
    assert "exp" not in unverified


def test_access_key_issuer_service_allows_expiration_above_default_when_max_disabled(tmp_path):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    created = issuer.create(AccessKeyCreateRequest(name="long-lived", expires_in_seconds=31 * 24 * 60 * 60))

    assert created.expires_at == datetime.fromtimestamp(1787958400, tz=UTC)


def test_access_key_issuer_service_requires_expiration_when_default_disabled_and_max_configured(tmp_path):
    config = _access_key_config(tmp_path, default_expires_in_seconds=None, max_expires_in_seconds=60)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    with pytest.raises(RuntimeError, match="expires_in_seconds is required"):
        issuer.create(AccessKeyCreateRequest(name="must-set-expiry"))

    created = issuer.create(AccessKeyCreateRequest(name="finite-expiry", expires_in_seconds=60))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    assert unverified["exp"] == 1785280060
    assert created.expires_at == datetime.fromtimestamp(1785280060, tz=UTC)


def test_access_key_issuer_service_allows_omitted_expiration_when_default_and_max_disabled(tmp_path):
    config = _access_key_config(tmp_path, default_expires_in_seconds=None, max_expires_in_seconds=None)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    created = issuer.create(AccessKeyCreateRequest(name="deployment-default-unlimited"))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    assert created.expires_at is None
    assert "exp" not in unverified


def test_access_key_issuer_service_honors_finite_expiration_when_default_and_max_disabled(tmp_path):
    config = _access_key_config(tmp_path, default_expires_in_seconds=None, max_expires_in_seconds=None)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )

    created = issuer.create(AccessKeyCreateRequest(name="finite-in-unlimited-policy", expires_in_seconds=600))
    unverified = jwt.decode(created.token, options={"verify_signature": False})

    assert unverified["exp"] == 1785280600
    assert created.expires_at == datetime.fromtimestamp(1785280600, tz=UTC)


async def test_validate_access_key_token_returns_token_claims(tmp_path):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    principal = Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"])
    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1785280000)
    created = await issuer.create_async(AccessKeyCreateRequest(name="gtc-intake", expires_in_seconds=None))
    jwks = {"keys": [await public_jwk_from_private_key_pem_async(config)]}

    claims = await validate_access_key_token(config, created.token, jwks_override=jwks)

    assert claims is not None
    assert claims.subject == "alice@example.com"
    assert claims.email == "alice@example.com"
    assert claims.groups == ["team-ml"]
    assert claims.scopes == []


async def test_validate_access_key_token_accepts_legacy_list_groups_claim(tmp_path):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    now = 1785280000
    signing_key = await access_keys_mod._access_key_signing_key_async(config)
    token = jwt.encode(
        {
            "iss": access_keys_mod.access_key_issuer(config),
            "aud": config.access_keys.audience,
            "sub": "alice@example.com",
            "iat": now,
            "nbf": now,
            "jti": "ak_legacy",
            "nmp_token_type": ACCESS_KEY_TOKEN_TYPE,
            "nmp_access_key": {"version": 1},
            "groups": ["team-ml", "team-ai"],
        },
        signing_key.private_key,
        algorithm="RS256",
        headers={"kid": config.token_signing.key_id},
    )
    jwks = {"keys": [await public_jwk_from_private_key_pem_async(config)]}

    claims = await validate_access_key_token(config, token, jwks_override=jwks)

    assert claims is not None
    assert claims.groups == ["team-ml", "team-ai"]


async def test_validate_access_key_token_fetches_remote_jwks_once_with_async_client(tmp_path, monkeypatch):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    principal = Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"])
    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1785280000)
    created = await issuer.create_async(AccessKeyCreateRequest(name="gtc-intake", expires_in_seconds=None))
    jwks = {"keys": [await public_jwk_from_private_key_pem_async(config)]}
    jwks_uri = f"https://auth.example.test/{id(jwks)}/jwks"

    class ForbiddenPyJWKClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Access-key validation should use the shared async HTTP client")

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return jwks

    class FakeAsyncClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get(self, url: str, *, timeout: float) -> FakeResponse:
            assert url == jwks_uri
            assert timeout == 10.0
            self.calls += 1
            return FakeResponse()

    fake_client = FakeAsyncClient()
    monkeypatch.setattr(access_keys_mod, "access_key_jwks_uri", lambda config: jwks_uri)
    monkeypatch.setattr(http_clients, "shared_async_http_client", lambda: fake_client)
    monkeypatch.setattr(access_keys_mod.jwt, "PyJWKClient", ForbiddenPyJWKClient)

    first_claims = await validate_access_key_token(config, created.token)
    second_claims = await validate_access_key_token(config, created.token)

    assert first_claims is not None
    assert second_claims is not None
    assert first_claims.subject == "alice@example.com"
    assert second_claims.subject == "alice@example.com"
    assert fake_client.calls == 1


async def test_validate_access_key_token_propagates_remote_jwks_fetch_failure(tmp_path, monkeypatch):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    principal = Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"])
    issuer = AccessKeyIssuerService(config=config, principal=principal, now=lambda: 1785280000)
    created = await issuer.create_async(AccessKeyCreateRequest(name="gtc-intake", expires_in_seconds=None))
    jwks_uri = "https://auth.example.test/jwks"

    class FakeResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request("GET", jwks_uri)
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("JWKS unavailable", request=request, response=response)

    class FakeAsyncClient:
        async def get(self, url: str, *, timeout: float) -> FakeResponse:
            assert url == jwks_uri
            assert timeout == 10.0
            return FakeResponse()

    monkeypatch.setattr(access_keys_mod, "access_key_jwks_uri", lambda config: jwks_uri)
    monkeypatch.setattr(http_clients, "shared_async_http_client", lambda: FakeAsyncClient())

    with pytest.raises(httpx.HTTPStatusError):
        await validate_access_key_token(config, created.token)


async def test_validate_access_key_token_rejects_wrong_audience(tmp_path):
    config = _access_key_config(tmp_path, max_expires_in_seconds=None)
    wrong_config = config.model_copy(
        update={"access_keys": config.access_keys.model_copy(update={"audience": "different-audience"})}
    )
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )
    created = await issuer.create_async(AccessKeyCreateRequest(name="gtc-intake", expires_in_seconds=None))
    jwks = {"keys": [await public_jwk_from_private_key_pem_async(config)]}

    assert await validate_access_key_token(wrong_config, created.token, jwks_override=jwks) is None


async def test_validate_access_key_token_rejects_service_principal_subject(tmp_path):
    config = _access_key_config(tmp_path)
    issuer = AccessKeyIssuerService(config=config, principal=Principal(id="service:jobs"), now=lambda: 1785280000)

    with pytest.raises(RuntimeError, match="service principals"):
        await issuer.create_async(AccessKeyCreateRequest(name="bad-service-key", expires_in_seconds=600))


async def test_validate_access_key_token_rejects_expired_key(tmp_path):
    config = _access_key_config(tmp_path)
    issuer = AccessKeyIssuerService(
        config=config,
        principal=Principal(id="alice@example.com", email="alice@example.com"),
        now=lambda: 1785280000,
    )
    created = await issuer.create_async(AccessKeyCreateRequest(name="short-lived", expires_in_seconds=60))
    jwks = {"keys": [await public_jwk_from_private_key_pem_async(config)]}

    assert created.expires_at == datetime.fromtimestamp(1785280060, tz=UTC)
    assert await validate_access_key_token(config, created.token, jwks_override=jwks, now=1785280061) is None
