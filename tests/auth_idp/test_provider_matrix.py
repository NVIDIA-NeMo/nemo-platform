# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_platform import APIStatusError
from nemo_platform_ext.auth.helpers import generate_unsigned_jwt
from nmp.testing import TEST_ADMIN_EMAIL, grant_workspace_role, unique_email

# This module remains generic auth/authz contract coverage for providers whose
# real token acquisition path is not wired yet. Authentik real OIDC validation
# lives in test_authentik_real_oidc.py.
pytestmark = [pytest.mark.e2e_config("e2e/configs/local-subprocess.yaml", {"auth": {"enabled": True}})]
pytestmark.append(pytest.mark.auth_idp)


def _bearer_headers(*, principal_id: str, email: str, groups: list[str] | None = None) -> dict[str, str]:
    token = generate_unsigned_jwt(principal_id=principal_id, email=email, groups=groups)
    return {"Authorization": f"Bearer {token}"}


def _sdk_as_bearer_user(sdk, *, principal_id: str, email: str, groups: list[str] | None = None):
    return sdk.with_options(set_default_headers=_bearer_headers(principal_id=principal_id, email=email, groups=groups))


def test_machine_identity_principal_id_is_not_treated_as_internal_service(idp_provider):
    assert idp_provider.machine_principal_id
    assert not idp_provider.machine_principal_id.startswith("service:")


def test_machine_identity_group_binding_contract_is_declared(idp_provider, provider_machine_groups):
    assert provider_machine_groups


def test_unsigned_machine_identity_header_shape_matches_contract(idp_provider):
    headers = _bearer_headers(
        principal_id=idp_provider.machine_principal_id,
        email="machine@example.com",
        groups=idp_provider.machine_expected_groups,
    )
    assert "Authorization" in headers


def test_human_oidc_identity_can_access_bound_workspace(sdk, workspace):
    human_email = unique_email("idp-human")
    admin_sdk = _sdk_as_bearer_user(
        sdk,
        principal_id=TEST_ADMIN_EMAIL,
        email=TEST_ADMIN_EMAIL,
        groups=["admin"],
    )
    grant_workspace_role(admin_sdk, workspace=workspace, principal=human_email, roles=["Viewer"])

    human_sdk = _sdk_as_bearer_user(sdk, principal_id=human_email, email=human_email)
    retrieved_workspace = human_sdk.workspaces.retrieve(workspace)
    assert retrieved_workspace.name == workspace


def test_machine_identity_is_denied_before_binding(sdk, workspace, idp_provider):
    machine_sdk = _sdk_as_bearer_user(
        sdk,
        principal_id=idp_provider.machine_principal_id,
        email=f"{idp_provider.machine_principal_id}@example.com",
        groups=[],
    )

    with pytest.raises(APIStatusError):
        machine_sdk.workspaces.retrieve(workspace)


def test_machine_identity_is_allowed_after_binding(sdk, workspace, idp_provider):
    admin_sdk = _sdk_as_bearer_user(
        sdk,
        principal_id=TEST_ADMIN_EMAIL,
        email=TEST_ADMIN_EMAIL,
        groups=["admin"],
    )
    for group in idp_provider.machine_expected_groups:
        grant_workspace_role(admin_sdk, workspace=workspace, principal=group, roles=["Viewer"])

    machine_sdk = _sdk_as_bearer_user(
        sdk,
        principal_id=idp_provider.machine_principal_id,
        email=f"{idp_provider.machine_principal_id}@example.com",
        groups=idp_provider.machine_expected_groups,
    )
    retrieved_workspace = machine_sdk.workspaces.retrieve(workspace)
    assert retrieved_workspace.name == workspace


def test_machine_identity_returns_to_denied_after_revoke(sdk, workspace, idp_provider):
    admin_sdk = _sdk_as_bearer_user(
        sdk,
        principal_id=TEST_ADMIN_EMAIL,
        email=TEST_ADMIN_EMAIL,
        groups=["admin"],
    )
    for group in idp_provider.machine_expected_groups:
        grant_workspace_role(admin_sdk, workspace=workspace, principal=group, roles=["Viewer"])
        admin_sdk.workspaces.members.delete(group, workspace=workspace, wait_role_propagation=True)

    machine_sdk = _sdk_as_bearer_user(
        sdk,
        principal_id=idp_provider.machine_principal_id,
        email=f"{idp_provider.machine_principal_id}@example.com",
        groups=idp_provider.machine_expected_groups,
    )

    with pytest.raises(APIStatusError):
        machine_sdk.workspaces.retrieve(workspace)
