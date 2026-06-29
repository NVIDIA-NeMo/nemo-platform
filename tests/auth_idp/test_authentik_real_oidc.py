# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_platform import APIStatusError
from nmp.testing import grant_workspace_role

from tests.auth_idp.authentik_live import AUTHENTIK_DOCKER_PYTESTMARK

pytestmark = AUTHENTIK_DOCKER_PYTESTMARK


def test_authentik_machine_token_is_real(machine_token: str, authentik_provider):
    assert machine_token
    assert authentik_provider.token_endpoint


def test_authentik_machine_identity_is_denied_before_binding(machine_sdk, workspace):
    with pytest.raises(APIStatusError) as exc_info:
        machine_sdk.workspaces.retrieve(workspace)
    assert exc_info.value.status_code == 403


def test_authentik_machine_identity_is_allowed_after_binding(sdk, machine_sdk, workspace, authentik_provider):
    for group in authentik_provider.machine_expected_groups:
        grant_workspace_role(sdk, workspace=workspace, principal=group, roles=["Viewer"])

    retrieved = machine_sdk.workspaces.retrieve(workspace)
    assert retrieved.name == workspace


def test_authentik_machine_identity_returns_to_denied_after_revoke(sdk, machine_sdk, workspace, authentik_provider):
    for group in authentik_provider.machine_expected_groups:
        grant_workspace_role(sdk, workspace=workspace, principal=group, roles=["Viewer"])
        sdk.workspaces.members.delete(group, workspace=workspace, wait_role_propagation=True)

    with pytest.raises(APIStatusError) as exc_info:
        machine_sdk.workspaces.retrieve(workspace)
    assert exc_info.value.status_code == 403
