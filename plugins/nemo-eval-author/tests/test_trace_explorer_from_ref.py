# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for TraceExplorer.from_ref intake:// URI parsing.

Trial/eval traces are persisted as ``intake://traces/<id>`` while Eval Author traces
attached to an Insight use the bare ``intake://<id>`` form. ``from_ref`` must resolve both to the
raw ``<id>`` that Intake filters on — otherwise trial traces query ClickHouse
with a ``traces/<id>`` id that never matches and are silently skipped, even once
the platform client/workspace are correctly plumbed in.
"""

from typing import Any, cast

import pytest
from nemo_eval_author_plugin.evaluator.models import ResourceRef
from nemo_eval_author_plugin.trace_explorer import TraceExplorer


@pytest.fixture
def capture_from_intake(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace TraceExplorer.from_intake with a recorder; return the call log."""
    calls: list[dict[str, Any]] = []

    async def _fake_from_intake(cls: Any, client: Any, trace_id: str, *, workspace: str, **kwargs: Any) -> str:
        calls.append({"client": client, "trace_id": trace_id, "workspace": workspace})
        return "sentinel-trace-explorer"

    monkeypatch.setattr(TraceExplorer, "from_intake", classmethod(_fake_from_intake))
    return calls


@pytest.mark.asyncio
async def test_from_ref_strips_traces_prefix_for_trial_traces(
    capture_from_intake: list[dict[str, Any]],
) -> None:
    """``intake://traces/<id>`` (trial-trace format) resolves to the bare <id>."""
    client = cast(Any, object())
    ref = ResourceRef(uri="intake://traces/abc123")

    result = await TraceExplorer.from_ref(ref, client, "ws-1")

    assert result == "sentinel-trace-explorer"
    assert capture_from_intake == [{"client": client, "trace_id": "abc123", "workspace": "ws-1"}]


@pytest.mark.asyncio
async def test_from_ref_handles_bare_intake_uri_for_eval_author_traces(
    capture_from_intake: list[dict[str, Any]],
) -> None:
    """``intake://<id>`` (Eval Author Insight format) still resolves to <id>."""
    client = cast(Any, object())
    ref = ResourceRef(uri="intake://abc123")

    await TraceExplorer.from_ref(ref, client, "ws-1")

    assert capture_from_intake == [{"client": client, "trace_id": "abc123", "workspace": "ws-1"}]


@pytest.mark.asyncio
async def test_from_ref_requires_client_and_workspace(
    capture_from_intake: list[dict[str, Any]],
) -> None:
    """Without client/workspace, intake refs raise rather than being silently skipped."""
    ref = ResourceRef(uri="intake://traces/abc123")

    with pytest.raises(ValueError, match="missing client/workspace"):
        await TraceExplorer.from_ref(ref, None, None)

    assert capture_from_intake == []
