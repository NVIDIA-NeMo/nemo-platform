# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_platform_plugin.auth.access_keys.issuer import AccessKeyOperationNotImplementedError
from nmp.common.auth.client import AuthClient
from nmp.common.auth.dependencies import auth_client_context
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig
from nmp.common.config.base import AccessKeyConfig, TokenSigningConfig
from nmp.core.auth.api.v2.access_keys.endpoints import get_access_key_issuer, router


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
    response = client.post("/v2/access-keys", json={"name": "gtc-intake", "expires_in_seconds": 3600})

    assert response.status_code == 200
    body = response.json()
    assert body["jti"].startswith("ak_")
    assert body["name"] == "gtc-intake"
    assert body["token_type"] == "Bearer"
    assert body["principal"] == "alice@example.com"
    assert body["expires_at"] is not None
    assert body["token"].count(".") == 2


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

    list_responses = openapi["paths"]["/v2/access-keys"]["get"]["responses"]
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
    assert revoke_responses["200"]["content"]["application/json"]["schema"] == {}
    assert revoke_responses["404"]["description"] == "Scoped Access Keys are not enabled"
    assert revoke_responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyErrorResponse"
    }
    assert revoke_responses["501"]["description"] == "Not Implemented"
    assert revoke_responses["501"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyNotImplementedErrorResponse"
    }


def test_list_access_keys_is_explicitly_not_implemented(client):
    response = client.get("/v2/access-keys")

    assert response.status_code == 501
    assert response.json()["detail"] == "Scoped Access Key listing is not implemented."


def test_revoke_access_key_is_explicitly_not_implemented(client):
    response = client.delete("/v2/access-keys/ak_example")

    assert response.status_code == 501
    assert response.json()["detail"] == "Scoped Access Key revocation for ak_example is not implemented."
