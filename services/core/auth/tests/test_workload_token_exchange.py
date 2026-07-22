# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.common.config import AuthConfig, Configuration
from nmp.common.config.base import OIDCConfig
from nmp.core.auth.api.v2 import workload_token_exchange as exchange


@pytest.fixture(autouse=True)
def _clear_config_overrides():
    yield
    Configuration.clear_overrides()


@pytest.fixture
def exchange_service() -> exchange.WorkloadTokenExchangeService:
    return exchange.WorkloadTokenExchangeService()


@pytest.fixture
def workload_signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _private_key_pem(private_key: rsa.RSAPrivateKey) -> str:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def exchange_config(workload_signing_key: rsa.RSAPrivateKey, tmp_path) -> AuthConfig:
    private_key_file = tmp_path / "workload-token-private-key.pem"
    private_key_file.write_text(_private_key_pem(workload_signing_key), encoding="utf-8")
    return AuthConfig(
        enabled=True,
        oidc=OIDCConfig(
            enabled=True,
            issuer="https://idp.example.com/application/o/nemo-cli/",
            additional_issuers=["https://idp.example.com/application/o/nemo/"],
            client_id="nemo-platform-cli",
            workload_token_exchange_enabled=True,
            workload_client_id="nemo-platform-workload",
            workload_audience="nemo-platform",
            workload_scope="openid email groups",
            workload_subject_jwks_uri="https://idp.example.com/application/o/nemo-workload/jwks/",
            workload_subject_issuers=["https://idp.example.com/application/o/nemo-workload/"],
            workload_token_private_key_file=str(private_key_file),
        ),
    )


@pytest.fixture
def client(exchange_config: AuthConfig, exchange_service: exchange.WorkloadTokenExchangeService) -> TestClient:
    Configuration.set_override(exchange_config)
    app = FastAPI()
    app.dependency_overrides[exchange.get_workload_token_exchange_service] = lambda: exchange_service
    app.include_router(exchange.router)
    return TestClient(app, raise_server_exceptions=False)


def test_jwks_publishes_workload_exchange_signing_key(client: TestClient) -> None:
    response = client.get("/jwks")

    assert response.status_code == 200
    keys = response.json()["keys"]
    assert keys[0]["kid"] == "nemo-workload-exchange"
    assert keys[0]["use"] == "sig"
    assert keys[0]["alg"] == "RS256"


def test_jwks_openapi_documents_jwks_response(client: TestClient) -> None:
    openapi = client.app.openapi()
    operation = openapi["paths"]["/jwks"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/JsonWebKeySetResponse"
    }
    jwks_schema = openapi["components"]["schemas"]["JsonWebKeySetResponse"]
    assert jwks_schema["required"] == ["keys"]
    assert jwks_schema["properties"]["keys"]["type"] == "array"
    assert jwks_schema["properties"]["keys"]["items"] == {"$ref": "#/components/schemas/JsonWebKey"}
    assert openapi["components"]["schemas"]["JsonWebKey"] == {
        "additionalProperties": True,
        "properties": {},
        "type": "object",
        "title": "JsonWebKey",
        "description": "JSON Web Key object.",
    }


def test_token_exchange_openapi_documents_form_request_and_token_response(client: TestClient) -> None:
    openapi = client.app.openapi()
    operation = openapi["paths"]["/token"]["post"]

    request_schema = operation["requestBody"]["content"]["application/x-www-form-urlencoded"]["schema"]
    if "$ref" in request_schema:
        request_schema = openapi["components"]["schemas"][request_schema["$ref"].rsplit("/", 1)[-1]]

    assert {
        "grant_type",
        "client_id",
        "subject_token",
        "subject_token_type",
        "requested_token_type",
        "audience",
        "scope",
    } <= set(request_schema["properties"])
    assert set(operation["responses"]) == {"200", "400", "401"}
    assert operation["responses"]["200"]["description"] == "Successful Response"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkloadTokenExchangeResponse"
    }
    assert operation["responses"]["400"]["description"] == "RFC 8693 token exchange error"
    assert operation["responses"]["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkloadTokenExchangeErrorResponse"
    }
    assert operation["responses"]["401"]["description"] == "OAuth 2.0 invalid_client error"
    assert operation["responses"]["401"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkloadTokenExchangeErrorResponse"
    }
    error_schema = openapi["components"]["schemas"]["WorkloadTokenExchangeErrorResponse"]
    assert error_schema["properties"]["error"]["type"] == "string"
    error_description = error_schema["properties"]["error"]["description"]
    for error_code in ("invalid_client", "invalid_request", "invalid_grant", "invalid_scope", "invalid_target"):
        assert error_code in error_description
    response_schema = openapi["components"]["schemas"]["WorkloadTokenExchangeResponse"]
    assert {
        "access_token",
        "issued_token_type",
        "token_type",
        "expires_in",
        "scope",
    } == set(response_schema["properties"])
    assert response_schema["required"] == [
        "access_token",
        "issued_token_type",
        "token_type",
        "expires_in",
    ]


def test_token_exchange_rejects_subject_token_without_subject(
    client: TestClient,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def decode_subject_token(config: AuthConfig, subject_token: str, audience: str) -> dict[str, str]:
        return {"email": "svc@example.com"}

    monkeypatch.setattr(exchange_service, "decode_subject_token", decode_subject_token)

    response = client.post(
        "/token",
        data={
            "grant_type": exchange.TOKEN_EXCHANGE_GRANT_TYPE,
            "client_id": "nemo-platform-workload",
            "subject_token": "subject-token",
            "subject_token_type": exchange.JWT_TOKEN_TYPE,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_request",
        "error_description": "Could not validate subject token",
    }


def test_token_exchange_rejects_disallowed_audience_before_subject_validation(
    client: TestClient,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def decode_subject_token(config: AuthConfig, subject_token: str, audience: str) -> dict[str, str]:
        raise AssertionError("disallowed audience should be rejected before subject token validation")

    monkeypatch.setattr(exchange_service, "decode_subject_token", decode_subject_token)

    response = client.post(
        "/token",
        data={
            "grant_type": exchange.TOKEN_EXCHANGE_GRANT_TYPE,
            "client_id": "nemo-platform-workload",
            "subject_token": "subject-token",
            "subject_token_type": exchange.JWT_TOKEN_TYPE,
            "audience": "unexpected-audience",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_target",
        "error_description": "Requested audience is not allowed",
    }


def test_token_exchange_mints_access_token_signed_by_configured_key(
    client: TestClient,
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def decode_subject_token(config: AuthConfig, subject_token: str, audience: str) -> dict[str, Any]:
        captured["subject_audience"] = audience
        return {
            "sub": "workload-subject",
            "email": "svc@example.com",
            "groups": ["svc-group", "system:serviceaccounts"],
        }

    monkeypatch.setattr(exchange_service, "decode_subject_token", decode_subject_token)

    response = client.post(
        "/token",
        data={
            "grant_type": exchange.TOKEN_EXCHANGE_GRANT_TYPE,
            "client_id": "nemo-platform-workload",
            "subject_token": "subject-token",
            "subject_token_type": exchange.JWT_TOKEN_TYPE,
        },
    )

    assert response.status_code == 200
    access_token = response.json()["access_token"]
    signing_key = exchange_service.workload_signing_key(exchange_config)
    assert exchange.jwt.get_unverified_header(access_token)["kid"] == signing_key.kid
    claims = exchange.jwt.decode(access_token, signing_key.public_key, algorithms=["RS256"], audience="nemo-platform")
    assert captured["subject_audience"] == "nemo-platform-workload"
    assert claims["sub"] == "workload-subject"
    assert claims["email"] == "svc@example.com"
    assert claims["groups"] == "svc-group,system:serviceaccounts"


def test_validated_audience_accepts_configured_allowlist(exchange_config: AuthConfig) -> None:
    exchange_config.oidc.workload_allowed_audiences.append("extra-audience")

    assert exchange._validated_audience(exchange_config, "extra-audience") == "extra-audience"


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _signed_subject_token(
    config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    *,
    audience: str,
    issuer: str | None = None,
    private_key: rsa.RSAPrivateKey | None = None,
    key_id: str | None = None,
) -> str:
    token_issuer = issuer or config.oidc.workload_subject_issuers[0]
    signing_key = exchange_service.workload_signing_key(config)
    return exchange.jwt.encode(
        {
            "iss": token_issuer,
            "sub": "authentik-user",
            "aud": audience,
            "exp": int(exchange.time.time()) + 300,
        },
        private_key or signing_key.private_key,
        algorithm="RS256",
        headers={"kid": key_id or signing_key.kid},
    )


def _public_jwk_for_key(private_key: rsa.RSAPrivateKey, *, key_id: str) -> dict[str, Any]:
    jwk = json.loads(exchange.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": key_id, "use": "sig", "alg": "RS256"})
    return jwk


def _mock_subject_jwks_client(
    config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    captured: dict[str, Any] = {"request_count": 0}

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get(self, url: str) -> _FakeResponse:
            captured["request_count"] += 1
            captured["url"] = url
            return _FakeResponse({"keys": [exchange_service.public_jwk(config)]})

    monkeypatch.setattr(exchange.httpx, "AsyncClient", FakeAsyncClient)
    return captured


def test_jwt_subject_token_decoder_fetches_configured_jwks(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _mock_subject_jwks_client(exchange_config, exchange_service, monkeypatch)
    subject_token = _signed_subject_token(exchange_config, exchange_service, audience="nemo-platform-workload")

    claims = asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))

    assert claims["sub"] == "authentik-user"
    assert captured == {
        "request_count": 1,
        "timeout": 30.0,
        "url": "https://idp.example.com/application/o/nemo-workload/jwks/",
    }


def test_jwt_subject_token_decoder_caches_configured_jwks(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _mock_subject_jwks_client(exchange_config, exchange_service, monkeypatch)
    subject_token = _signed_subject_token(exchange_config, exchange_service, audience="nemo-platform-workload")

    asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))
    asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))

    assert captured["request_count"] == 1


def test_jwt_subject_token_decoder_does_not_cache_invalid_jwks(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jwks_responses = [
        {},
        {"keys": [exchange_service.public_jwk(exchange_config)]},
    ]
    captured: dict[str, Any] = {"request_count": 0}

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get(self, url: str) -> _FakeResponse:
            captured["request_count"] += 1
            captured["url"] = url
            return _FakeResponse(jwks_responses.pop(0))

    monkeypatch.setattr(exchange.httpx, "AsyncClient", FakeAsyncClient)
    subject_token = _signed_subject_token(exchange_config, exchange_service, audience="nemo-platform-workload")

    with pytest.raises(exchange.jwt.InvalidTokenError, match="valid JWKS"):
        asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))

    claims = asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))

    assert claims["sub"] == "authentik-user"
    assert captured["request_count"] == 2


def test_jwt_subject_token_decoder_refreshes_cached_jwks_on_unknown_kid(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rotated_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject_token = _signed_subject_token(
        exchange_config,
        exchange_service,
        audience="nemo-platform-workload",
        private_key=rotated_key,
        key_id="rotated-key",
    )
    jwks_responses = [
        {"keys": [exchange_service.public_jwk(exchange_config)]},
        {"keys": [_public_jwk_for_key(rotated_key, key_id="rotated-key")]},
    ]
    captured: dict[str, Any] = {"request_count": 0}

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get(self, url: str) -> _FakeResponse:
            captured["request_count"] += 1
            captured["url"] = url
            return _FakeResponse(jwks_responses.pop(0))

    monkeypatch.setattr(exchange.httpx, "AsyncClient", FakeAsyncClient)

    claims = asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))

    assert claims["sub"] == "authentik-user"
    assert captured["request_count"] == 2


def test_jwt_subject_token_decoder_rejects_wrong_audience(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_subject_jwks_client(exchange_config, exchange_service, monkeypatch)
    subject_token = _signed_subject_token(exchange_config, exchange_service, audience="some-other-client")

    with pytest.raises(exchange.jwt.InvalidAudienceError):
        asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))


def test_jwt_subject_token_decoder_rejects_unexpected_issuer(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_subject_jwks_client(exchange_config, exchange_service, monkeypatch)
    subject_token = _signed_subject_token(
        exchange_config,
        exchange_service,
        audience="nemo-platform-workload",
        issuer="https://idp.example.com/application/o/other/",
    )

    with pytest.raises(exchange.jwt.InvalidIssuerError):
        asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))


def test_jwt_subject_token_decoder_requires_explicit_workload_subject_issuers(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_subject_jwks_client(exchange_config, exchange_service, monkeypatch)
    exchange_config.oidc.workload_subject_issuers = []
    subject_token = _signed_subject_token(
        exchange_config,
        exchange_service,
        audience="nemo-platform-workload",
        issuer=exchange_config.oidc.additional_issuers[0],
    )

    with pytest.raises(exchange.jwt.InvalidIssuerError):
        asyncio.run(exchange_service.decode_jwt_subject_token(exchange_config, subject_token))


def test_subject_token_decoder_reports_all_validation_failures(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject_token = _signed_subject_token(exchange_config, exchange_service, audience="nemo-platform-workload")
    exchange_config.oidc.workload_subject_jwks_uri = None
    exchange_config.oidc.workload_kubernetes_token_review_enabled = True
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)

    with pytest.raises(exchange.jwt.InvalidTokenError) as exc_info:
        asyncio.run(exchange_service.decode_subject_token(exchange_config, subject_token, "nemo-platform"))

    assert str(exc_info.value) == (
        "JWT subject token: JWT subject token validation is disabled; "
        "Kubernetes TokenReview subject token: Kubernetes service environment is unavailable"
    )


def test_subject_token_decoder_does_not_mask_unexpected_decoder_errors(
    exchange_config: AuthConfig,
    exchange_service: exchange.WorkloadTokenExchangeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_jwt_subject_token(config: AuthConfig, subject_token: str) -> dict[str, Any]:
        raise exchange.jwt.InvalidTokenError("JWT rejected")

    async def broken_kubernetes_subject_token(
        config: AuthConfig,
        subject_token: str,
        audience: str,
    ) -> dict[str, Any]:
        raise RuntimeError("Kubernetes decoder broke")

    monkeypatch.setattr(exchange_service, "decode_jwt_subject_token", reject_jwt_subject_token)
    monkeypatch.setattr(exchange, "_decode_kubernetes_subject_token", broken_kubernetes_subject_token)

    with pytest.raises(RuntimeError, match="Kubernetes decoder broke"):
        asyncio.run(exchange_service.decode_subject_token(exchange_config, "subject-token", "nemo-platform"))


def test_kubernetes_subject_token_decoder_posts_token_review_with_async_client(
    exchange_config: AuthConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    exchange_config.oidc.workload_kubernetes_token_review_enabled = True
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    monkeypatch.setenv("KUBERNETES_SERVICE_PORT", "443")
    monkeypatch.setattr(exchange, "_kubernetes_reviewer_credentials", lambda: ("reviewer-token", "/tmp/ca.crt"))

    class FakeAsyncClient:
        def __init__(self, *, timeout: float, verify: str) -> None:
            captured["timeout"] = timeout
            captured["verify"] = verify

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, url: str, **kwargs) -> _FakeResponse:
            captured["url"] = url
            captured["json"] = kwargs["json"]
            captured["headers"] = kwargs["headers"]
            return _FakeResponse(
                {
                    "status": {
                        "authenticated": True,
                        "user": {
                            "username": "system:serviceaccount:default:nemo",
                            "groups": ["system:serviceaccounts"],
                        },
                    }
                }
            )

    monkeypatch.setattr(exchange.httpx, "AsyncClient", FakeAsyncClient)

    claims = asyncio.run(
        exchange._decode_kubernetes_subject_token(exchange_config, "kubernetes-subject-token", "nemo-platform")
    )

    assert claims == {
        "sub": "system:serviceaccount:default:nemo",
        "groups": ["system:serviceaccounts"],
    }
    assert captured == {
        "timeout": 10.0,
        "verify": "/tmp/ca.crt",
        "url": "https://kubernetes.default.svc:443/apis/authentication.k8s.io/v1/tokenreviews",
        "json": {
            "apiVersion": "authentication.k8s.io/v1",
            "kind": "TokenReview",
            "spec": {
                "token": "kubernetes-subject-token",
                "audiences": ["nemo-platform"],
            },
        },
        "headers": {
            "Authorization": "Bearer reviewer-token",
            "Content-Type": "application/json",
        },
    }
