# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import uuid

import httpx
from nemo_platform_ext.auth.helpers import discover_nmp_config

from tests.auth_idp.authentik_live import AUTHENTIK_DOCKER_PYTESTMARK

pytestmark = AUTHENTIK_DOCKER_PYTESTMARK


def _jwt_claims(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _delete_workspace_for_cleanup(base_url: str, workspace_name: str, headers: dict[str, str]) -> None:
    response = httpx.delete(
        f"{base_url}/apis/entities/v2/workspaces/{workspace_name}",
        headers=headers,
        timeout=10.0,
    )
    response.raise_for_status()


def test_authentik_discovery_exposes_gateway_reachable_device_flow(authentik_stack):
    oidc = discover_nmp_config(authentik_stack.gateway_base_url)

    assert oidc.auth_enabled is True
    assert oidc.client_id == "nemo-platform-cli"
    assert oidc.token_endpoint == "http://127.0.0.1:38080/application/o/token/"
    assert oidc.device_authorization_endpoint == "http://127.0.0.1:38080/application/o/device/"
    assert oidc.default_scopes == "openid email offline_access groups"

    response = httpx.post(
        oidc.device_authorization_endpoint,
        data={
            "client_id": oidc.client_id,
            "scope": oidc.default_scopes,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()

    assert body["verification_uri"] == "http://127.0.0.1:38080/device"
    assert body["verification_uri_complete"].startswith("http://127.0.0.1:38080/device?code=")
    assert body["device_code"]
    assert body["user_code"]


def test_authentik_cli_provider_token_is_accepted_by_gateway(authentik_stack):
    token_response = httpx.post(
        authentik_stack.token_endpoint,
        data={
            "grant_type": "password",
            "client_id": "nemo-platform-cli",
            "username": "nemo-user",
            "password": "nemo-user-token-secret-dev",
            "scope": "openid email offline_access groups",
        },
        timeout=30.0,
    )
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]
    claims = _jwt_claims(access_token)
    workspace_name = f"cli-audience-check-{uuid.uuid4().hex[:8]}"
    headers = {"Authorization": f"Bearer {access_token}"}

    assert claims["aud"] == "nemo-platform-cli"

    try:
        create_response = httpx.post(
            f"{authentik_stack.gateway_base_url}/apis/entities/v2/workspaces",
            json={"name": workspace_name, "description": "CLI audience check"},
            headers=headers,
            timeout=10.0,
        )
        create_response.raise_for_status()
        assert create_response.json()["created_by"] == "nemo-user"
    finally:
        _delete_workspace_for_cleanup(authentik_stack.gateway_base_url, workspace_name, headers)
