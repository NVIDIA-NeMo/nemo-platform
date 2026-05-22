# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""InsightTrace CRUD route tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

from nemo_insights_plugin.entities import InsightTrace, InsightTraceRole
from nemo_platform_plugin.entity_client import NemoEntityConflictError, NemoEntityNotFoundError

NOW = datetime.now(timezone.utc)


def stamp(entity):
    entity._id = f"{entity.__entity_type__}-{entity.name}-id"
    entity._created_at = NOW
    entity._updated_at = NOW
    return entity


def _make(insight: str = "ins-1", trace_id: str = "trace-abc", workspace: str = "default", **fields) -> InsightTrace:
    name = f"{insight}--{trace_id}"
    return stamp(InsightTrace(name=name, workspace=workspace, insight=insight, trace_id=trace_id, **fields))


class TestCreate:
    def test_composes_name_from_insight_and_trace_id(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.return_value = _make("ins-1", "trace-abc")
        resp = client.post(
            "/v2/workspaces/default/insight_traces",
            json={"insight": "ins-1", "trace_id": "trace-abc"},
        )
        assert resp.status_code == 201
        sent = mock_entity_client.create.call_args.args[0]
        assert sent.name == "ins-1--trace-abc"

    def test_default_role_is_evidence(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.return_value = _make("ins-1", "trace-abc")
        client.post(
            "/v2/workspaces/default/insight_traces",
            json={"insight": "ins-1", "trace_id": "trace-abc"},
        )
        sent = mock_entity_client.create.call_args.args[0]
        assert sent.role == InsightTraceRole.EVIDENCE

    def test_explicit_role(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.return_value = _make(
            "ins-1", "trace-abc", role=InsightTraceRole.REGRESSION_TEST_CANDIDATE
        )
        client.post(
            "/v2/workspaces/default/insight_traces",
            json={"insight": "ins-1", "trace_id": "trace-abc", "role": "regression_test_candidate"},
        )
        sent = mock_entity_client.create.call_args.args[0]
        assert sent.role == InsightTraceRole.REGRESSION_TEST_CANDIDATE

    def test_409_on_duplicate_link(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.create.side_effect = NemoEntityConflictError("conflict")
        resp = client.post(
            "/v2/workspaces/default/insight_traces",
            json={"insight": "ins-1", "trace_id": "trace-abc"},
        )
        assert resp.status_code == 409
        assert "already attached" in resp.json()["detail"]


class TestGet:
    def test_404(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.get.side_effect = NemoEntityNotFoundError("nope")
        resp = client.get("/v2/workspaces/default/insight_traces/missing--trace")
        assert resp.status_code == 404


class TestUpdate:
    def test_role_change(self, client, mock_entity_client: AsyncMock) -> None:
        existing = _make("ins-1", "trace-abc")
        mock_entity_client.get.return_value = existing
        mock_entity_client.update.return_value = existing
        resp = client.patch(
            "/v2/workspaces/default/insight_traces/ins-1--trace-abc",
            json={"role": "regression_test_candidate"},
        )
        assert resp.status_code == 200
        updated = mock_entity_client.update.call_args.args[0]
        assert updated.role == InsightTraceRole.REGRESSION_TEST_CANDIDATE


class TestDelete:
    def test_204(self, client, mock_entity_client: AsyncMock) -> None:
        mock_entity_client.delete.return_value = None
        resp = client.delete("/v2/workspaces/default/insight_traces/ins-1--trace-abc")
        assert resp.status_code == 204
