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
from nmp.core.auth.app.access_keys import AccessKeyNotFoundError, AccessKeyStateConflictError, get_access_key_registry


class InMemoryAccessKeyRegistry:
    def __init__(self):
        self.keys = {}
        self.revoked = set()
        self.suspended = set()

    async def add(self, key):
        self.keys[key.jti] = key

    def _status(self, jti, key):
        if jti in self.revoked:
            return "REVOKED"
        if key.expires_at is not None and key.expires_at <= datetime.now(tz=UTC) - timedelta(seconds=30):
            return "EXPIRED"
        if jti in self.suspended:
            return "SUSPENDED"
        return key.status

    async def list_for_principal(self, principal, *, page, page_size):
        from nemo_platform_plugin.auth.access_keys.types import AccessKeyListResponse, AccessKeyMetadataResponse

        # Sort newest-first then by jti to match the real registry's `sort="-issued_at"`.
        owned = sorted(
            [(jti, key) for jti, key in self.keys.items() if key.principal == principal],
            key=lambda item: (-item[1].created_at.timestamp(), item[0]),
        )
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
        self.suspended.discard(jti)
        return revoked

    async def suspend(self, jti, principal):
        key = self.keys.get(jti)
        if key is None or key.principal != principal:
            raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found")
        if jti in self.revoked:
            raise AccessKeyStateConflictError(f"Revoked Scoped Access Key {jti} cannot be suspended")
        if key.expires_at is not None and key.expires_at <= datetime.now(tz=UTC):
            return False, "EXPIRED"
        changed = jti not in self.suspended
        self.suspended.add(jti)
        return changed, self._status(jti, key)

    async def unsuspend(self, jti, principal):
        key = self.keys.get(jti)
        if key is None or key.principal != principal:
            raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found")
        if jti in self.revoked:
            raise AccessKeyStateConflictError(f"Revoked Scoped Access Key {jti} cannot be unsuspended")
        if key.expires_at is not None and key.expires_at <= datetime.now(tz=UTC):
            return False, "EXPIRED"
        changed = jti in self.suspended
        self.suspended.discard(jti)
        return changed, self._status(jti, key)

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
            "name": "ci-intake",
            "description": "CI intake automation",
            "expires_in_seconds": 3600,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jti"].startswith("ak_")
    assert body["name"] == "ci-intake"
    assert body["description"] == "CI intake automation"
    assert body["token_type"] == "Bearer"
    assert body["principal"] == "alice@example.com"
    assert body["expires_at"] is not None
    assert body["token"].count(".") == 2


def test_create_and_revoke_emit_actor_aware_audit_logs(client, caplog):
    with caplog.at_level(logging.INFO, logger="nmp.core.auth.app.access_keys"):
        created = client.post(
            "/v2/access-keys",
            json={"name": "ci-intake", "description": "CI intake automation"},
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
    assert "CI intake automation" not in caplog.text


def test_suspend_and_unsuspend_emit_actor_aware_audit_logs(client, caplog):
    created = client.post("/v2/access-keys", json={"name": "ci-intake"}).json()
    jti = created["jti"]

    with caplog.at_level(logging.INFO, logger="nmp.core.auth.app.access_keys"):
        client.post(f"/v2/access-keys/{jti}/suspend")
        client.post(f"/v2/access-keys/{jti}/suspend")
        client.post(f"/v2/access-keys/{jti}/unsuspend")
        client.post(f"/v2/access-keys/{jti}/unsuspend")

    events = {record.audit_event: record for record in caplog.records if hasattr(record, "audit_event")}
    assert set(events) >= {
        "access_key.suspended",
        "access_key.suspend_noop",
        "access_key.unsuspended",
        "access_key.unsuspend_noop",
    }
    for event in events.values():
        assert event.actor_principal == "alice@example.com"
        assert event.access_key_jti == jti
    assert events["access_key.suspended"].access_key_state_changed
    assert not events["access_key.suspend_noop"].access_key_state_changed
    assert events["access_key.unsuspended"].access_key_state_changed
    assert not events["access_key.unsuspend_noop"].access_key_state_changed


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
    response = client.post("/v2/access-keys", json={"name": "ci-intake"})

    assert response.status_code == 200
    body = response.json()
    assert body["jti"].startswith("ak_")
    assert body["name"] == "ci-intake"
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
    body = response.json()
    assert body["detail"] == "Scoped Access Keys are not enabled"
    assert body["code"] == "access_keys_disabled"


def test_create_access_key_is_explicitly_not_implemented(client):
    class NotImplementedIssuer:
        async def create_async(self, request):
            raise AccessKeyOperationNotImplementedError("Scoped Access Key creation is not implemented")

    client.app.dependency_overrides[get_access_key_issuer] = lambda: NotImplementedIssuer()
    try:
        response = client.post("/v2/access-keys", json={"name": "ci-intake"})
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 501
    assert response.json()["detail"] == "Scoped Access Key creation is not implemented"


def test_create_access_key_does_not_misclassify_unexpected_runtime_error(client):
    class BrokenIssuer:
        async def create_async(self, request):
            raise RuntimeError("entity storage unavailable")

    client.app.dependency_overrides[get_access_key_issuer] = lambda: BrokenIssuer()
    try:
        with pytest.raises(RuntimeError, match="entity storage unavailable"):
            client.post("/v2/access-keys", json={})
    finally:
        client.app.dependency_overrides.clear()


def test_list_access_keys_is_disabled_by_default(disabled_client):
    response = disabled_client.get("/v2/access-keys")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Scoped Access Keys are not enabled"
    assert body["code"] == "access_keys_disabled"


def test_revoke_access_key_is_disabled_by_default(disabled_client):
    response = disabled_client.delete("/v2/access-keys/ak_" + "a" * 32)

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Scoped Access Keys are not enabled"
    assert body["code"] == "access_keys_disabled"


@pytest.mark.parametrize("action", ["suspend", "unsuspend"])
def test_suspension_actions_are_disabled_by_default(disabled_client, action):
    response = disabled_client.post(f"/v2/access-keys/ak_{'a' * 32}/{action}")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Scoped Access Keys are not enabled",
        "code": "access_keys_disabled",
    }


def test_access_key_specific_jwks_route_does_not_accept_get(client):
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
    assert create_responses["409"]["description"] == "Concurrent access-key update conflict"
    assert create_responses["409"]["content"]["application/json"]["schema"] == {
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
    assert openapi["components"]["schemas"]["AccessKeyMetadataResponse"]["properties"]["status"]["enum"] == [
        "ACTIVE",
        "EXPIRED",
        "REVOKED",
        "SUSPENDED",
    ]
    status_change_schema = openapi["components"]["schemas"]["AccessKeyStatusChangeResponse"]
    assert set(status_change_schema["required"]) == {"jti", "status", "changed"}
    assert status_change_schema["properties"]["status"]["enum"] == ["ACTIVE", "EXPIRED", "SUSPENDED"]
    error_code_schema = openapi["components"]["schemas"]["AccessKeyErrorResponse"]["properties"]["code"]
    assert error_code_schema["nullable"] is True
    assert error_code_schema["anyOf"][0]["const"] == "access_keys_disabled"
    assert error_code_schema["description"] == (
        "Set to access_keys_disabled when the Scoped Access Key feature is disabled."
    )

    list_operation = openapi["paths"]["/v2/access-keys"]["get"]
    list_parameters = {parameter["name"]: parameter for parameter in list_operation["parameters"]}
    assert list_parameters["page"]["schema"] == {
        "type": "integer",
        "minimum": 1,
        "default": 1,
        "title": "Page",
        "description": "Page number to retrieve.",
    }
    assert list_parameters["page_size"]["schema"] == {
        "type": "integer",
        "maximum": 100,
        "minimum": 1,
        "default": 100,
        "title": "Page Size",
        "description": "Number of keys to retrieve per page.",
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

    for action in ["suspend", "unsuspend"]:
        responses = openapi["paths"][f"/v2/access-keys/{{jti}}/{action}"]["post"]["responses"]
        assert responses["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/AccessKeyStatusChangeResponse"
        }
        assert responses["404"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/AccessKeyErrorResponse"
        }
        assert responses["409"]["description"] == "Invalid or concurrent access-key state transition"
        assert responses["409"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/AccessKeyErrorResponse"
        }

    revoke_operation = openapi["paths"]["/v2/access-keys/{jti}"]["delete"]
    jti_parameter = next(parameter for parameter in revoke_operation["parameters"] if parameter["name"] == "jti")
    assert jti_parameter["schema"]["pattern"] == "^ak_[0-9a-f]{32}$"
    assert jti_parameter["description"] == "Stable JWT ID of the Scoped Access Key for the lifecycle operation."
    revoke_responses = revoke_operation["responses"]
    assert revoke_responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyRevokeResponse"
    }
    assert revoke_responses["404"]["description"] == "Scoped Access Keys are not enabled or the key was not found"
    assert revoke_responses["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyErrorResponse"
    }
    assert revoke_responses["409"]["description"] == "Concurrent access-key update conflict"
    assert revoke_responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyErrorResponse"
    }
    assert revoke_responses["501"]["description"] == "Not Implemented"
    assert revoke_responses["501"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AccessKeyNotImplementedErrorResponse"
    }


def test_list_access_keys_returns_current_principals_persisted_keys(client):
    created = client.post(
        "/v2/access-keys",
        json={"name": "ci-intake", "description": "CI intake automation"},
    ).json()

    response = client.get("/v2/access-keys")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "jti": created["jti"],
            "name": "ci-intake",
            "principal": "alice@example.com",
            "created_at": created["created_at"],
            "expires_at": created["expires_at"],
            "description": "CI intake automation",
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
    assert len(first_page.json()["data"]) == 1
    assert first_page.json()["has_more"] is True
    assert second_page.status_code == 200
    assert len(second_page.json()["data"]) == 1
    assert second_page.json()["has_more"] is False
    # Both keys appear exactly once across the two pages (order depends on issued_at).
    all_jtis = {
        key["jti"] for page_data in [first_page.json()["data"], second_page.json()["data"]] for key in page_data
    }
    assert all_jtis == {first["jti"], second["jti"]}


def test_revoke_access_key_marks_key_revoked_in_listing(client):
    created = client.post("/v2/access-keys", json={"name": "ci-intake"}).json()

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
    unknown_jti = "ak_" + "0" * 32
    response = client.delete(f"/v2/access-keys/{unknown_jti}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Scoped Access Key {unknown_jti} was not found"


def test_revoke_access_key_rejects_malformed_jti(client):
    response = client.delete("/v2/access-keys/ak_tooshort")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["type"] == "string_pattern_mismatch"


def test_suspend_and_unsuspend_access_key(client):
    created = client.post("/v2/access-keys", json={"name": "ci-intake"}).json()
    jti = created["jti"]

    suspended = client.post(f"/v2/access-keys/{jti}/suspend")
    repeated_suspend = client.post(f"/v2/access-keys/{jti}/suspend")

    assert suspended.status_code == 200
    assert suspended.json() == {"jti": jti, "status": "SUSPENDED", "changed": True}
    assert repeated_suspend.json() == {"jti": jti, "status": "SUSPENDED", "changed": False}
    assert client.get("/v2/access-keys").json()["data"][0]["status"] == "SUSPENDED"

    unsuspended = client.post(f"/v2/access-keys/{jti}/unsuspend")
    repeated_unsuspend = client.post(f"/v2/access-keys/{jti}/unsuspend")

    assert unsuspended.status_code == 200
    assert unsuspended.json() == {"jti": jti, "status": "ACTIVE", "changed": True}
    assert repeated_unsuspend.json() == {"jti": jti, "status": "ACTIVE", "changed": False}
    assert client.get("/v2/access-keys").json()["data"][0]["status"] == "ACTIVE"


def test_unsuspend_reports_expired_status_for_key_that_expired_while_suspended(client):
    created = client.post("/v2/access-keys", json={"name": "ci-intake", "expires_in_seconds": 3600}).json()
    jti = created["jti"]
    assert client.post(f"/v2/access-keys/{jti}/suspend").status_code == 200

    registry = client.app.dependency_overrides[get_access_key_registry]()
    registry.keys[jti].expires_at = datetime.now(tz=UTC) - timedelta(hours=1)

    unsuspended = client.post(f"/v2/access-keys/{jti}/unsuspend")

    assert unsuspended.status_code == 200
    assert unsuspended.json() == {"jti": jti, "status": "EXPIRED", "changed": False}
    assert client.get("/v2/access-keys").json()["data"][0]["status"] == "EXPIRED"


@pytest.mark.parametrize("action", ["suspend", "unsuspend"])
def test_suspension_transition_reports_expired_at_expiration_boundary(client, action):
    created = client.post("/v2/access-keys", json={"name": "ci-intake", "expires_in_seconds": 3600}).json()
    jti = created["jti"]
    if action == "unsuspend":
        assert client.post(f"/v2/access-keys/{jti}/suspend").status_code == 200

    registry = client.app.dependency_overrides[get_access_key_registry]()
    registry.keys[jti].expires_at = datetime.now(tz=UTC)

    response = client.post(f"/v2/access-keys/{jti}/{action}")

    assert response.status_code == 200
    assert response.json() == {"jti": jti, "status": "EXPIRED", "changed": False}


@pytest.mark.parametrize("action", ["suspend", "unsuspend"])
def test_revoked_access_key_cannot_be_suspended_or_unsuspended(client, action):
    created = client.post("/v2/access-keys", json={}).json()
    jti = created["jti"]
    assert client.delete(f"/v2/access-keys/{jti}").status_code == 200

    response = client.post(f"/v2/access-keys/{jti}/{action}")

    assert response.status_code == 409
    assert response.json()["detail"] == f"Revoked Scoped Access Key {jti} cannot be {action}ed"


@pytest.mark.parametrize("action", ["suspend", "unsuspend"])
def test_suspension_action_returns_not_found_for_unknown_key(client, action):
    unknown_jti = "ak_" + "0" * 32

    response = client.post(f"/v2/access-keys/{unknown_jti}/{action}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Scoped Access Key {unknown_jti} was not found"
