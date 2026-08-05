# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from nmp.common.auth.access_keys import public_jwk_from_private_key_pem, validate_access_key_token
from nmp.common.auth.jwt import TokenClaims
from nmp.common.config import AuthConfig
from nmp.common.config.base import AccessKeyConfig, TokenSigningConfig
from nmp.core.auth.config import AuthServiceConfig
from nmp.testing.client import create_test_client

# Run on a dedicated worker so the inline create_test_client call doesn't share
# the module-level wasmtime singleton with the module-scoped test_client fixture
# used by sibling integration tests (which would violate wasmtime thread affinity).
pytestmark = pytest.mark.xdist_group("auth_scoped_access_keys")

ACCESS_KEYS_PATH = "/apis/auth/v2/access-keys"
IAM_ROLE_BINDINGS_PATH = "/apis/auth/v2/iam/role-bindings"
WORKSPACES_PATH = "/apis/entities/v2/workspaces"
SERVICE_HEADERS = {"X-NMP-Principal-Id": "service:integration-test"}


def _tamper_jwt(token: str) -> str:
    """Return a JWT with its signature bytes changed so validation must fail."""
    parts = token.split(".")
    assert len(parts) == 3
    signature = parts[2]
    replacement = "A" if signature[0] != "A" else "B"
    parts[2] = f"{replacement}{signature[1:]}"
    return ".".join(parts)


def _write_private_key(path: Path) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _auth_configs(private_key_file: str) -> tuple[AuthConfig, AuthServiceConfig]:
    shared_config = AuthConfig(
        enabled=True,
        policy_decision_point_provider="embedded",
        policy_decision_point_base_url="http://testserver",
        propagation_poll_interval_seconds=0.05,
        token_signing=TokenSigningConfig(
            issuer="http://testserver/apis/auth",
            key_id="integration-access-key",
            private_key_file=private_key_file,
        ),
        access_keys=AccessKeyConfig(enabled=True),
    )
    service_config = AuthServiceConfig(
        **shared_config.model_dump(),
        policy_data_refresh_interval=0.2,
        bundle_cache_seconds=0,
        admin_email="admin@example.com",
    )
    return shared_config, service_config


def test_scoped_access_key_created_by_auth_service_authenticates_platform_requests(tmp_path: Path) -> None:
    private_key_file = tmp_path / "access-key-private.pem"
    _write_private_key(private_key_file)
    shared_config, service_config = _auth_configs(str(private_key_file))
    assert shared_config.oidc.workload_token_exchange_enabled is False

    with create_test_client(
        client_type=TestClient,
        auth_enabled=True,
        service_configs={
            AuthConfig: shared_config,
            AuthServiceConfig: service_config,
        },
    ) as client:
        workspace = f"access-key-smoke-{uuid.uuid4().hex[:8]}"
        group = f"access-key-group-{uuid.uuid4().hex[:8]}"
        user = f"access-key-user-{uuid.uuid4().hex[:8]}@example.com"
        user_headers = {
            "X-NMP-Principal-Id": user,
            "X-NMP-Principal-Email": user,
            "X-NMP-Principal-Groups": group,
        }

        create_workspace = client.post(
            WORKSPACES_PATH,
            json={"name": workspace, "description": "Scoped Access Key integration smoke"},
            headers=SERVICE_HEADERS,
        )
        assert create_workspace.status_code in {200, 201}, create_workspace.text

        try:
            create_key = client.post(
                ACCESS_KEYS_PATH,
                json={"name": "integration-smoke"},
                headers=user_headers,
            )
            assert create_key.status_code == 200, create_key.text
            access_key_body = create_key.json()
            access_key = access_key_body["token"]
            access_key_jti = access_key_body["jti"]

            list_keys = client.get(ACCESS_KEYS_PATH, headers=user_headers)
            assert list_keys.status_code == 200, list_keys.text
            assert [key["jti"] for key in list_keys.json()["data"]] == [access_key_jti]

            role_binding = client.post(
                IAM_ROLE_BINDINGS_PATH,
                json={"principal": group, "role": "Viewer", "workspace": workspace},
                headers=SERVICE_HEADERS,
            )
            assert role_binding.status_code in {200, 201}, role_binding.text

            jwks = {"keys": [public_jwk_from_private_key_pem(shared_config)]}

            async def validate_with_local_jwks(config: AuthConfig, token: str) -> TokenClaims | None:
                return await validate_access_key_token(config, token, jwks_override=jwks)

            with patch("nmp.common.auth.access_keys.validate_access_key_token", validate_with_local_jwks):
                response = client.get(
                    f"{WORKSPACES_PATH}/{workspace}",
                    headers={"Authorization": f"Bearer {access_key}"},
                )
                assert response.status_code == 200, response.text
                assert response.json()["name"] == workspace

                authenticate_response = client.get(
                    "/apis/auth/authenticate",
                    headers={"Authorization": f"Bearer {access_key}"},
                )
                invalid_authenticate_response = client.get(
                    "/apis/auth/authenticate",
                    headers={"Authorization": f"Bearer {_tamper_jwt(access_key)}"},
                )
                assert authenticate_response.status_code == 200, authenticate_response.text
                assert authenticate_response.json()["principal"] == user
                assert authenticate_response.json()["token_kind"] == "access_key"
                assert invalid_authenticate_response.status_code == 401, invalid_authenticate_response.text

                invalid_workspace_response = client.get(
                    f"{WORKSPACES_PATH}/{workspace}",
                    headers={"Authorization": f"Bearer {_tamper_jwt(access_key)}"},
                )
                assert invalid_workspace_response.status_code == 401, invalid_workspace_response.text

                revoke_key = client.delete(f"{ACCESS_KEYS_PATH}/{access_key_jti}", headers=user_headers)
                assert revoke_key.status_code == 200, revoke_key.text
                revoked_keys = client.get(ACCESS_KEYS_PATH, headers=user_headers).json()["data"]
                assert len(revoked_keys) == 1
                assert revoked_keys[0]["status"] == "REVOKED"

                revoked_authenticate_response = client.get(
                    "/apis/auth/authenticate",
                    headers={"Authorization": f"Bearer {access_key}"},
                )
                assert revoked_authenticate_response.status_code == 401, revoked_authenticate_response.text

                revoked_workspace_response = client.get(
                    f"{WORKSPACES_PATH}/{workspace}",
                    headers={"Authorization": f"Bearer {access_key}"},
                )
                assert revoked_workspace_response.status_code == 401, revoked_workspace_response.text
        finally:
            client.delete(f"{WORKSPACES_PATH}/{workspace}", headers=SERVICE_HEADERS)
