# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import uuid

import httpx
from nmp.testing import grant_workspace_role

from tests.auth_idp.authentik_live import AUTHENTIK_DOCKER_PYTESTMARK

pytestmark = AUTHENTIK_DOCKER_PYTESTMARK


def _jwt_claims(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def test_authentik_gateway_rejects_unauthenticated_requests(authentik_stack):
    response = httpx.get(f"{authentik_stack.gateway_base_url}/apis/entities/v2/workspaces", timeout=10.0)
    assert response.status_code in {401, 403}


def test_authentik_gateway_rejects_spoofed_principal_headers(authentik_stack, machine_token: str):
    workspace_name = f"spoof-check-{uuid.uuid4().hex[:8]}"
    claims = _jwt_claims(machine_token)
    authenticated_principal_id = str(claims["sub"])
    expected_binding_principal = authenticated_principal_id
    headers = {
        "Authorization": f"Bearer {machine_token}",
        "X-NMP-Principal-Id": "service:bootstrap",
        "X-NMP-Principal-Email": "attacker@example.com",
    }

    try:
        create_response = httpx.post(
            f"{authentik_stack.gateway_base_url}/apis/entities/v2/workspaces",
            json={"name": workspace_name, "description": "Spoofed header check"},
            headers=headers,
            timeout=10.0,
        )
        create_response.raise_for_status()
        assert create_response.json()["created_by"] == authenticated_principal_id

        members_response = httpx.get(
            f"{authentik_stack.gateway_base_url}/apis/entities/v2/workspaces/{workspace_name}/members",
            headers=headers,
            timeout=10.0,
        )
        members_response.raise_for_status()
        admin_member = next(member for member in members_response.json()["data"] if "Admin" in member["roles"])

        assert admin_member["granted_by"] == authenticated_principal_id
        assert admin_member["principal"] == expected_binding_principal
        assert admin_member["principal"] not in {"service:bootstrap", "attacker@example.com"}
    finally:
        httpx.delete(
            f"{authentik_stack.gateway_base_url}/apis/entities/v2/workspaces/{workspace_name}",
            headers=headers,
            timeout=10.0,
        )


def test_authentik_gateway_forwards_workload_groups(
    authentik_stack,
    authentik_human_sdk,
    authentik_workspace,
    authentik_provider,
    machine_token: str,
):
    claims = _jwt_claims(machine_token)
    claim_groups = claims.get("groups")
    assert isinstance(claim_groups, str)
    token_groups = {group.strip() for group in claim_groups.split(",") if group.strip()}
    bound_group = authentik_provider.workload_expected_groups[0]
    assert bound_group in token_groups

    grant_workspace_role(authentik_human_sdk, workspace=authentik_workspace, principal=bound_group, roles=["Viewer"])

    headers = {"Authorization": f"Bearer {machine_token}"}

    response = httpx.get(
        f"{authentik_stack.gateway_base_url}/apis/entities/v2/workspaces/{authentik_workspace}",
        headers=headers,
        timeout=10.0,
    )

    assert response.status_code == 200
    assert response.json()["name"] == authentik_workspace
