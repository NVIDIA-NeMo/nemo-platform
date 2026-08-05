# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_platform_plugin.auth.access_keys.issuer import AccessKeyOperationNotImplementedError
from nemo_platform_plugin.auth.access_keys.types import AccessKeyCreateResponse
from nmp.common.auth.client import AuthClient
from nmp.common.auth.dependencies import auth_client_context
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig
from nmp.common.config.base import AccessKeyConfig, TokenSigningConfig
from nmp.core.auth.api.v2.access_keys.endpoints import get_access_key_issuer, router
from nmp.core.auth.app.access_keys import AccessKeyNotFoundError, get_access_key_registry


class InMemoryAccessKeyRegistry:
    def __init__(self):
        self.keys = {}
        self.revoked = set()

    async def add(self, key):
        self.keys[key.jti] = key

    def _status(self, jti, key):
        if jti in self.revoked:
            return "REVOKED"
        if key.expires_at is not None and key.expires_at <= datetime.now(tz=UTC):
            return "EXPIRED"
        return key.status

    async def list_for_principal(self, principal, *, page, page_size):
        from nemo_platform_plugin.auth.access_keys.types import AccessKeyListResponse, AccessKeyMetadataResponse

        owned = [(jti, key) for jti, key in self.keys.items() if key.principal == principal]
        start = (page - 1) * page_size
        selected = owned[start : start + page_size]
        return AccessKeyListResponse(
            data=[
                AccessKeyMetadataResponse.model_validate(
                    key.model_dump(exclude={"token", "token_type"}) | {"status": self._status(jti, key)}
                )
                for jti, key in selected
            ],
            has_more=start + page_size < len(owned),
        )

    async def revoke(self, jti, principal):
        key = self.keys.get(jti)
        if key is None or key.principal != principal:
            raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found")
        revoked = jti not in self.revoked
        self.revoked.add(jti)
        return revoked

    async def is_active(self, jti, principal, **kwargs):
        key = self.keys.get(jti)
        return key is not None and key.principal == principal and self._status(jti, key) == "ACTIVE"


@pytest.fixture
def client(tmp_path):
    config = AuthConfig(
        enabled=True,
        token_signing=TokenSigningConfig(
            issuer="http://testserver/apis/auth",
            key_id="test-access-key",
            private_key_file=str(tmp_path / "private.pem"),
        ),
        access_keys=AccessKeyConfig(
            enabled=True,
            audience="nemo-platform-access-key",
        ),
    )

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (tmp_path / "private.pem").write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    app = FastAPI()
    app.include_router(router)
    registry = InMemoryAccessKeyRegistry()
    app.dependency_overrides[get_access_key_registry] = lambda: registry

    token = auth_client_context.set(
        AuthClient(
            principal=Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"]),
            config=config,
        )
    )
    with patch("nmp.core.auth.api.v2.access_keys.endpoints.get_auth_config", return_value=config):
        yield TestClient(app)
    auth_client_context.reset(token)


@pytest.fixture
def disabled_client():
    config = AuthConfig(enabled=True, access_keys=AccessKeyConfig())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_access_key_registry] = lambda: InMemoryAccessKeyRegistry()
    token = auth_client_context.set(
        AuthClient(
            principal=Principal(id="alice@example.com", email="alice@example.com", groups=["team-ml"]),
            config=config,
        )
    )
    with patch("nmp.core.auth.api.v2.access_keys.endpoints.get_auth_config", return_value=config):
        yield TestClient(app)
    auth_client_context.reset(token)


def test_create_access_key_returns_token_for_current_principal(client):
    response = client.post(
        "/v2/access-keys",
        json={
            "name": "gtc-intake",
            "description": "GTC intake automation",
            "expires_in_seconds": 3600,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jti"].startswith("ak_")
    assert body["name"] == "gtc-intake"
    assert body["description"] == "GTC intake automation"
    assert body["token_type"] == "Bearer"
    assert body["principal"] == "alice@example.com"
    assert body["expires_at"] is not None
    assert body["token"].count(".") == 2


def test_create_and_revoke_emit_actor_aware_audit_logs(client, caplog):
    with caplog.at_level(logging.INFO, logger="nmp.core.auth.app.access_keys"):
        created = client.post(
            "/v2/access-keys",
            json={"name": "gtc-intake", "description": "GTC intake automation"},
        ).json()
        response = client.delete(f"/v2/access-keys/{created['jti']}")
        repeat_response = client.delete(f"/v2/access-keys/{created['jti']}")

    assert response.status_code == 200
    assert repeat_response.status_code == 200
    events = {record.audit_event: record for record in caplog.records if hasattr(record, "audit_event")}
    assert events["access_key.created"].actor_principal == "alice@example.com"
    assert events["access_key.created"].access_key_jti == created["jti"]
    assert events["access_key.revoked"].actor_principal == "alice@example.com"
    assert events["access_key.revoked"].access_key_jti == created["jti"]
    assert not events["access_key.revoked"].access_key_already_revoked
    assert events["access_key.revoke_noop"].actor_principal == "alice@example.com"
    assert events["access_key.revoke_noop"].access_key_jti == created["jti"]
    assert events["access_key.revoke_noop"].access_key_already_revoked
    assert created["token"] not in caplog.text
    assert "GTC intake automation" not in caplog.text


@pytest.mark.asyncio
async def test_in_memory_access_key_registry_reports_expired_status() -> None:
    registry = InMemoryAccessKeyRegistry()
    await registry.add(
        AccessKeyCreateResponse(
            jti="ak_expired",
            name="expired-key",
            token="signed.jwt.token",
            token_type="Bearer",
            principal="alice@example.com",
            created_at=datetime.now(tz=UTC) - timedelta(hours=2),
            expires_at=datetime.now(tz=UTC) - timedelta(hours=1),
            description=None,
            status="ACTIVE",
            issuer="http://testserver/apis/auth",
            audiences=["nemo-platform-access-key"],
        )
    )

    result = await registry.list_for_principal("alice@example.com", page=1, page_size=100)

    assert result.data[0].status == "EXPIRED"
    assert not await registry.is_active("ak_expired", "alice@example.com")


def test_create_access_key_allows_unnamed_tokens(client):
    response = client.post("/v2/access-keys", json={"expires_in_seconds": 3600})

    assert response.status_code == 200
    body = response.json()
    assert body["jti"].startswith("ak_")
    assert body["name"] is None
    assert body["token"].count(".") == 2


def test_create_access_key_defaults_expiration_when_omitted(client):
    response = client.post("/v2/access-keys", json={"name": "gtc-intake"})

    assert response.status_code == 200
    body = response.json()
    assert body["jti"].startswith("ak_")
    assert body["name"] == "gtc-intake"
    assert body["expires_at"] is not None
    assert body["token"].count(".") == 2


def test_create_access_key_rejects_explicit_null_expiration_when_max_configured(client):
    response = client.post(
        "/v2/access-keys",
        json={"name": "bad-request", "expires_in_seconds": None},
    )

    assert response.status_code == 400
    assert "expires_in_seconds=null requires auth.access_keys.max_expires_in_seconds" in response.json()["detail"]


def test_create_access_key_accepts_optional_expiration(client):
    response = client.post("/v2/access-keys", json={"name": "short-lived", "expires_in_seconds": 60})

    assert response.status_code == 200
    assert response.json()["expires_at"] is not None


def test_create_access_key_is_disabled_by_default(disabled_client):
    response = disabled_client.post("/v2/access-keys", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "Scoped Access Keys are not enabled"


def test_create_access_key_is_explicitly_not_implemented(client):
    class NotImplementedIssuer:
        async def create_async(self, request):
            raise AccessKeyOperationNotImplementedError("Scoped Access Key creation is not implemented")

    client.app.dependency_overrides[get_access_key_issuer] = lambda: NotImplementedIssuer()
    try:
        response = client.post("/v2/access-keys", json={"name": "gtc-intake"})
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 501
    assert response.json()["detail"] == "Scoped Access Key creation is not implemented"


def test_list_access_keys_is_disabled_by_default(disabled_client):
    response = disabled_client.get("/v2/access-keys")

    assert response.status_code == 404
    assert response.json()["detail"] == "Scoped Access Keys are not enabled"


def test_revoke_access_key_is_disabled_by_default(disabled_client):
    response = disabled_client.delete("/v2/access-keys/ak_example")

    assert response.status_code == 404
    assert response.json()["detail"] == "Scoped Access Keys are not enabled"


def test_access_key_specific_jwks_route_is_removed(client):
    response = client.get("/v2/access-keys/jwks")

    assert response.status_code == 405
    assert "DELETE" in response.headers["allow"]


def test_access_key_specific_jwks_route_is_not_in_openapi(client):
    assert "/v2/access-keys/jwks" not in client.app.openapi()["paths"]


def test_access_key_lifecycle_openapi_documents_error_responses(client):
    openapi = client.app.openapi()

    create_responses = openapi["paths"]["/v2/access-keys"]["post"]["responses"]
    assert create_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyCreateResponse"
    }
    assert create_responses["400"]["description"] == "Scoped Access Key creation error"
    assert create_responses["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyErrorResponse"
    }
    assert create_responses["404"]["description"] == "Scoped Access Keys are not enabled"
    assert create_responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyErrorResponse"
    }
    assert create_responses["501"]["description"] == "Not Implemented"
    assert create_responses["501"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyNotImplementedErrorResponse"
    }
    request_schema = openapi["components"]["schemas"]["AccessKeyCreateRequest"]
    assert request_schema["properties"]["name"]["nullable"] is True
    assert request_schema["properties"]["description"]["nullable"] is True
    assert request_schema["properties"]["expires_in_seconds"]["nullable"] is True
    metadata_schema = openapi["components"]["schemas"]["AccessKeyMetadataResponse"]
    assert metadata_schema["properties"]["name"]["nullable"] is True
    assert metadata_schema["properties"]["description"]["nullable"] is True
    assert metadata_schema["properties"]["audiences"]["uniqueItems"] is True
    assert metadata_schema["properties"]["expires_at"]["nullable"] is True
    create_response_schema = openapi["components"]["schemas"]["AccessKeyCreateResponse"]
    assert create_response_schema["properties"]["audiences"]["uniqueItems"] is True
    list_schema = openapi["components"]["schemas"]["AccessKeyListResponse"]
    assert list_schema["properties"]["has_more"]["default"] is False
    revoke_schema = openapi["components"]["schemas"]["AccessKeyRevokeResponse"]
    assert set(revoke_schema["required"]) == {"jti", "revoked"}

    list_operation = openapi["paths"]["/v2/access-keys"]["get"]
    list_parameters = {parameter["name"]: parameter for parameter in list_operation["parameters"]}
    assert list_parameters["page"]["schema"] == {"type": "integer", "minimum": 1, "default": 1, "title": "Page"}
    assert list_parameters["page_size"]["schema"] == {
        "type": "integer",
        "maximum": 100,
        "minimum": 1,
        "default": 100,
        "title": "Page Size",
    }
    list_responses = list_operation["responses"]
    assert list_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyListResponse"
    }
    assert list_responses["404"]["description"] == "Scoped Access Keys are not enabled"
    assert list_responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyErrorResponse"
    }
    assert list_responses["501"]["description"] == "Not Implemented"
    assert list_responses["501"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyNotImplementedErrorResponse"
    }

    revoke_responses = openapi["paths"]["/v2/access-keys/{jti}"]["delete"]["responses"]
    assert revoke_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyRevokeResponse"
    }
    assert revoke_responses["404"]["description"] == "Scoped Access Keys are not enabled or the key was not found"
    assert revoke_responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyErrorResponse"
    }
    assert revoke_responses["501"]["description"] == "Not Implemented"
    assert revoke_responses["501"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyNotImplementedErrorResponse"
    }


def test_list_access_keys_returns_current_principals_persisted_keys(client):
    created = client.post(
        "/v2/access-keys",
        json={"name": "gtc-intake", "description": "GTC intake automation"},
    ).json()

    response = client.get("/v2/access-keys")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "jti": created["jti"],
            "name": "gtc-intake",
            "principal": "alice@example.com",
            "created_at": created["created_at"],
            "expires_at": created["expires_at"],
            "description": "GTC intake automation",
            "status": "ACTIVE",
            "issuer": "http://testserver/apis/auth",
            "audiences": ["nemo-platform-access-key"],
        }
    ]
    assert response.json()["has_more"] is False


def test_list_access_keys_supports_pagination(client):
    first = client.post("/v2/access-keys", json={"name": "first"}).json()
    second = client.post("/v2/access-keys", json={"name": "second"}).json()

    first_page = client.get("/v2/access-keys", params={"page": 1, "page_size": 1})
    second_page = client.get("/v2/access-keys", params={"page": 2, "page_size": 1})

    assert first_page.status_code == 200
    assert [key["jti"] for key in first_page.json()["data"]] == [first["jti"]]
    assert first_page.json()["has_more"] is True
    assert second_page.status_code == 200
    assert [key["jti"] for key in second_page.json()["data"]] == [second["jti"]]
    assert second_page.json()["has_more"] is False


def test_revoke_access_key_marks_key_revoked_in_listing(client):
    created = client.post("/v2/access-keys", json={"name": "gtc-intake"}).json()

    response = client.delete(f"/v2/access-keys/{created['jti']}")

    assert response.status_code == 200
    assert response.json() == {"jti": created["jti"], "revoked": True}
    listed = client.get("/v2/access-keys").json()["data"]
    assert len(listed) == 1
    assert listed[0]["jti"] == created["jti"]
    assert listed[0]["status"] == "REVOKED"

    repeat_response = client.delete(f"/v2/access-keys/{created['jti']}")

    assert repeat_response.status_code == 200
    assert repeat_response.json() == {"jti": created["jti"], "revoked": False}


def test_revoke_access_key_returns_not_found_for_unknown_key(client):
    response = client.delete("/v2/access-keys/ak_unknown")

    assert response.status_code == 404
    assert response.json()["detail"] == "Scoped Access Key ak_unknown was not found"
