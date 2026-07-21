# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the event relay: durable ``events.jsonl`` history, ingest, and polling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from nemo_iron_swarm_plugin.api.v2 import events
from starlette.testclient import TestClient


def test_history_filters_by_last_seen_id(tmp_path: Path) -> None:
    stream = events._RunStream(tmp_path / "events.jsonl")
    for i in range(3):
        stream.publish({"event": f"e{i}", "payload": {}})
    assert [seq for seq, _ in stream.history(after_id=0)] == [1, 2, 3]
    assert [seq for seq, _ in stream.history(after_id=2)] == [3]


def test_publish_persists_and_a_fresh_stream_replays(tmp_path: Path) -> None:
    # Durability: events written by one stream survive on disk and replay from a brand-new stream on the
    # same file (as after a service restart), with ids continuing monotonically from the file's line count.
    path = tmp_path / "events.jsonl"
    first = events._RunStream(path)
    first.publish({"event": "agent_exchange", "payload": {"agent_name": "Direct Prompt Attacker"}})
    first.publish({"event": "agent_completed", "payload": {"agent_name": "Direct Prompt Attacker"}})

    assert path.exists()
    assert [json.loads(line)["event"] for line in path.read_text().splitlines()] == [
        "agent_exchange",
        "agent_completed",
    ]

    reopened = events._RunStream(path)
    assert [seq for seq, _ in reopened.history(after_id=0)] == [1, 2]
    reopened.publish({"event": "round_completed", "payload": {}})  # id continues from the persisted count
    assert reopened.history(after_id=2)[0][0] == 3


def test_ingest_endpoint_publishes_to_hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "hub", events.EventHub())
    monkeypatch.setattr(events, "_events_path", lambda ws, name: tmp_path / f"{ws}-{name}.jsonl")
    app = FastAPI()
    app.include_router(events.router, prefix="/v2/workspaces/{workspace}")
    with TestClient(app) as client:
        resp = client.post(
            "/v2/workspaces/default/runs/run-42/events",
            json={"event": "FINAL_VERDICT", "payload": {"passed": True}},
        )
    assert resp.status_code == 204
    persisted = events.hub.stream("default", "run-42").history(after_id=0)
    assert persisted[-1][1] == {"event": "FINAL_VERDICT", "payload": {"passed": True}}


def test_get_events_endpoint_returns_events_after_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "hub", events.EventHub())
    monkeypatch.setattr(events, "_events_path", lambda ws, name: tmp_path / f"{ws}-{name}.jsonl")
    app = FastAPI()
    app.include_router(events.router, prefix="/v2/workspaces/{workspace}")
    with TestClient(app) as client:
        for i in range(3):
            client.post(
                "/v2/workspaces/default/runs/run-1/events",
                json={"event": f"e{i}", "payload": {"i": i}},
            )
        resp = client.get("/v2/workspaces/default/runs/run-1/events?after=1")
    assert resp.status_code == 200
    body = resp.json()
    assert [e["id"] for e in body["events"]] == [2, 3]
    assert body["events"][0]["event"] == "e1"
    assert body["events"][1]["event"] == "e2"
