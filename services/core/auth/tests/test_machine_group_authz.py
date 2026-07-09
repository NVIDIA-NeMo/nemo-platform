# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Group-based authorization for a MACHINE principal.

Proves that a machine principal (service-account-style id, no email) is
authorized via group -> role, exactly how an OIDC client-credentials token from
authentik would be handled:

  * principal id looks like a service account ("svc-nemo-ci")
  * no email
  * carries groups ["nemo-editors"]

A role binding mapping the GROUP "nemo-editors" -> Editor in workspace "default"
must grant access; without that binding the same principal is denied.

The role binding flows through the real bundle-build path
(``_build_authorization_data_internal``), which is what turns a stored
RoleBindingEntity whose ``principal`` is a group name into
``authz.principals["nemo-editors"].workspaces["default"] = ["Editor"]``. The
embedded WASM PDP then treats each entry of ``principal_groups`` as an
applicable principal (see ``policies/common.rego: get_applicable_principals``).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nmp.core.auth.app.bundle import _build_authorization_data_internal
from nmp.core.auth.app.embedded_pdp import evaluate, set_policy_data

# Machine principal: service-account-style id, NO email, group membership only.
# The id deliberately has no "service:" prefix, so it does NOT hit the
# service-principal bypass — authorization must come purely from the group.
MACHINE_PRINCIPAL_ID = "svc-nemo-ci"
MACHINE_GROUP = "nemo-editors"
WORKSPACE = "default"

# Editor-only endpoint: POST /apis/models/v2/workspaces/{workspace}/models
# requires the "models.create" permission, which Editor has and Viewer does not.
EDITOR_ONLY_REQUEST = {
    "principal_id": MACHINE_PRINCIPAL_ID,
    # No principal_email — mirrors a client-credentials machine token.
    "principal_groups": [MACHINE_GROUP],
    "method": "POST",
    "path": f"/apis/models/v2/workspaces/{WORKSPACE}/models",
}


@pytest.fixture(autouse=True)
def reset_policy():
    """Reset the PDP policy singleton between tests."""
    import nmp.core.auth.app.embedded_pdp.engine as pe

    pe._policy = None
    pe._policy_data = {}
    yield
    pe._policy = None
    pe._policy_data = {}


def _entities_client_with_group_binding():
    """Mock entity client returning one active group->Editor role binding.

    The build loop in ``_build_authorization_data_internal`` only reads
    ``.principal``, ``.workspace``, ``.role`` and ``.revoked_at`` off each
    binding, so a SimpleNamespace is sufficient and avoids RoleBindingEntity
    required-field coupling.
    """
    binding = SimpleNamespace(
        principal=MACHINE_GROUP,  # binding is on the GROUP, not the machine id
        workspace=WORKSPACE,
        role="Editor",
        revoked_at=None,
    )
    page = SimpleNamespace(data=[binding])
    client = SimpleNamespace(list=AsyncMock(return_value=page))
    return client


@pytest.mark.asyncio
async def test_machine_principal_allowed_via_group_binding():
    """ALLOW: group binding nemo-editors -> Editor grants the machine access."""
    data = await _build_authorization_data_internal(
        entities_client=_entities_client_with_group_binding()  # type: ignore[arg-type]
    )

    # The group binding became a group-keyed principal entry.
    assert data["authz"]["principals"][MACHINE_GROUP]["workspaces"][WORKSPACE] == ["Editor"]
    # The machine id itself was never granted anything directly.
    assert MACHINE_PRINCIPAL_ID not in data["authz"]["principals"]

    set_policy_data(data)
    result = evaluate("allow", EDITOR_ONLY_REQUEST)
    assert result["allowed"] is True


@pytest.mark.asyncio
async def test_machine_principal_denied_without_group_binding():
    """DENY: no role binding -> the same machine principal is rejected."""
    data = await _build_authorization_data_internal(entities_client=None)

    # No binding means no group-keyed principal entry.
    assert MACHINE_GROUP not in data["authz"]["principals"]
    assert MACHINE_PRINCIPAL_ID not in data["authz"]["principals"]

    set_policy_data(data)
    result = evaluate("allow", EDITOR_ONLY_REQUEST)
    assert result["allowed"] is False


@pytest.mark.asyncio
async def test_machine_principal_has_editor_permission_via_group():
    """has_permissions entrypoint: the group grants the Editor-only permission."""
    data = await _build_authorization_data_internal(
        entities_client=_entities_client_with_group_binding()  # type: ignore[arg-type]
    )
    set_policy_data(data)

    result = evaluate(
        "has_permissions",
        {
            "principal_id": MACHINE_PRINCIPAL_ID,
            "principal_groups": [MACHINE_GROUP],
            "workspace": WORKSPACE,
            "permissions": ["models.create"],  # Editor-only (not in Viewer)
        },
    )
    assert result["allowed"] is True
