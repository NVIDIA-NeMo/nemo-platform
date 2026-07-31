# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for workspace access helpers in api/v2/utils.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from nmp.common.auth.dependencies import auth_client_context
from nmp.common.auth.models import Principal
from nmp.core.entities.api.v2 import utils
from nmp.core.entities.api.v2.utils import _applicable_principal_strings


def test_applicable_principal_strings_id_only() -> None:
    p = Principal(id="172d75ab-0866-4d10-b3ab-c42e37bf20b4", email=None, groups=[])
    assert _applicable_principal_strings(p) == ["172d75ab-0866-4d10-b3ab-c42e37bf20b4"]


def test_applicable_principal_strings_id_and_distinct_email() -> None:
    p = Principal(
        id="172d75ab-0866-4d10-b3ab-c42e37bf20b4",
        email="user@example.com",
        groups=[],
    )
    assert _applicable_principal_strings(p) == [
        "172d75ab-0866-4d10-b3ab-c42e37bf20b4",
        "user@example.com",
    ]


def test_applicable_principal_strings_dedupes_when_id_is_email_shaped() -> None:
    """If Principal-Id is already the email, do not duplicate."""
    p = Principal(id="same@example.com", email="same@example.com", groups=[])
    assert _applicable_principal_strings(p) == ["same@example.com"]


def test_applicable_principal_strings_includes_groups() -> None:
    p = Principal(
        id="sub-1",
        email="u@example.com",
        groups=["group-a", "group-b"],
    )
    assert _applicable_principal_strings(p) == ["sub-1", "u@example.com", "group-a", "group-b"]


def test_applicable_principal_strings_group_dedupes_against_id() -> None:
    p = Principal(id="dup", email=None, groups=["dup", "other"])
    assert _applicable_principal_strings(p) == ["dup", "other"]


@pytest.mark.asyncio
async def test_delegated_accessible_workspaces_require_export_outside_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal(
        id="service:models",
        on_behalf_of="editor@example.com",
        on_behalf_of_email="editor@example.com",
    )
    auth_client = MagicMock(
        auth_enabled=True,
        principal=principal,
        origin_workspace="origin-ws",
    )
    auth_client.has_permissions = AsyncMock(side_effect=lambda workspace, _permissions: workspace == "exported-ws")

    bindings = []
    for index, workspace in enumerate(("origin-ws", "exported-ws", "viewer-only-ws")):
        binding = MagicMock(
            id=f"binding-{index}",
            workspace=workspace,
            data={"workspace": workspace, "role": "Viewer"},
        )
        bindings.append(binding)

    async def fetch_bindings(_repository: object, principal_id: str):
        return bindings if principal_id == "editor@example.com" else []

    monkeypatch.setattr(utils, "_fetch_bindings_for_principal", fetch_bindings)
    token = auth_client_context.set(auth_client)
    try:
        accessible = await utils.get_accessible_workspaces(MagicMock())
    finally:
        auth_client_context.reset(token)

    assert accessible == {"origin-ws", "exported-ws"}
    assert {call.args[0] for call in auth_client.has_permissions.await_args_list} == {
        "exported-ws",
        "viewer-only-ws",
    }
    for call in auth_client.has_permissions.await_args_list:
        assert call.args[1] == ["entities.export"]


@pytest.mark.asyncio
async def test_delegated_export_checks_use_bounded_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    principal = Principal(id="service:models", on_behalf_of="editor@example.com")
    auth_client = MagicMock(auth_enabled=True, principal=principal, origin_workspace="origin-ws")
    active = 0
    peak = 0

    async def has_permissions(_workspace: str, _permissions: list[str]) -> bool:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return True

    auth_client.has_permissions = AsyncMock(side_effect=has_permissions)
    bindings = [
        MagicMock(
            id=f"binding-{index}",
            workspace=workspace,
            data={"workspace": workspace, "role": "Viewer"},
        )
        for index, workspace in enumerate(["origin-ws", *(f"workspace-{index}" for index in range(50))])
    ]

    async def fetch_bindings(_repository: object, principal_id: str):
        return bindings if principal_id == "editor@example.com" else []

    monkeypatch.setattr(utils, "_fetch_bindings_for_principal", fetch_bindings)
    token = auth_client_context.set(auth_client)
    try:
        await utils.get_accessible_workspaces(MagicMock())
    finally:
        auth_client_context.reset(token)

    assert peak <= utils.MAX_EXPORT_PERMISSION_CHECK_CONCURRENCY
