# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ownership resolution after the in-plugin identity provider was removed."""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from scaled_evals.api.auth import CurrentPrincipal, current_principal
from scaled_evals.api.settings import settings


def _request(**state: object) -> Request:
    """A Request carrying only what current_principal reads off request.state."""
    request = Request({"type": "http", "headers": []})
    for key, value in state.items():
        setattr(request.state, key, value)
    return request


def test_principal_defaults_to_the_shared_owner_and_fails_closed_when_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both halves of the seam matter, for opposite reasons.

    Unset, every caller must land on owner ``dev`` with source ``disabled``:
    that exact string is what seven call sites read to skip owner filtering, so
    drifting it silently hides rows written before ownership existed.

    Gated, there is no identity provider left to consult, so the only safe
    answer is 401. Returning the shared owner instead would hand one caller
    another caller's tasks.
    """
    monkeypatch.setattr(settings, "control_plane_auth_enabled", False)
    principal = current_principal(_request())
    assert (principal.owner_id, principal.owner_type, principal.source) == ("dev", "DEV", "disabled")

    monkeypatch.setattr(settings, "control_plane_auth_enabled", True)
    with pytest.raises(HTTPException) as raised:
        current_principal(_request())
    assert raised.value.status_code == 401

    # An upstream that does bridge identity still wins over both branches.
    bridged = CurrentPrincipal(owner_type="USER", owner_id="usr_1", source="platform")
    assert current_principal(_request(principal=bridged)) is bridged
