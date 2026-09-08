# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for persisted agent-session lifecycle helpers."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from nemo_agents_plugin.entities import AgentSession
from nemo_agents_plugin.session_lifecycle import session_expiration_is_due


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (datetime(2026, 8, 31, 16, 59, tzinfo=UTC), False),
        (datetime(2026, 8, 31, 17, 0, tzinfo=UTC), True),
    ],
)
def test_session_expiration_normalizes_non_utc_deadline(at: datetime, expected: bool) -> None:
    session = AgentSession(
        name="session-one",
        workspace="default",
        deployment_id="deployment-id",
        expires_at=datetime(2026, 8, 31, 12, 0, tzinfo=timezone(-timedelta(hours=5))),
    )

    assert session_expiration_is_due(session, at=at) is expected
