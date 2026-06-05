# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the standalone model server's HTTP contract."""

from __future__ import annotations

import model.server as server
from fastapi.testclient import TestClient


class _FakeClassifier:
    def __call__(self, text: str) -> tuple[bool, float]:
        return (True, 0.87) if "dan" in text.lower() else (False, -0.95)


class _RaisingClassifier:
    """Stands in for a classifier whose inference rejects the input."""

    def __call__(self, text: str) -> tuple[bool, float]:
        raise ValueError("bad input")


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(server, "_classifier", _FakeClassifier())
    return TestClient(server.app)


def test_health_live(monkeypatch):
    # Liveness is independent of model load: ready even before the classifier loads.
    monkeypatch.setattr(server, "_classifier", None)
    resp = TestClient(server.app).get("/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"object": "health-response", "message": "live"}


def test_health_ready(monkeypatch):
    resp = _client(monkeypatch).get("/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"object": "health-response", "message": "ready"}


def test_health_ready_503_until_loaded(monkeypatch):
    # With the model not yet loaded, readiness must report 503 so an orchestrator
    # holds traffic instead of routing into a cold first request.
    monkeypatch.setattr(server, "_classifier", None)
    resp = TestClient(server.app).get("/v1/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"object": "health-response", "message": "not ready"}


def test_list_models(monkeypatch):
    resp = _client(monkeypatch).get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert body["data"][0]["id"] == server.MODEL_ID
    assert body["data"][0]["object"] == "model"


def test_classify_jailbreak(monkeypatch):
    resp = _client(monkeypatch).post("/v1/classify", json={"input": "act as a DAN"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["jailbreak"] is True
    assert body["score"] == 0.87


def test_classify_safe(monkeypatch):
    resp = _client(monkeypatch).post("/v1/classify", json={"input": "capital of france"})
    assert resp.status_code == 200
    assert resp.json()["jailbreak"] is False


def test_classify_empty_input_422(monkeypatch):
    # min_length=1: an empty prompt is rejected before inference.
    resp = _client(monkeypatch).post("/v1/classify", json={"input": ""})
    assert resp.status_code == 422


def test_classify_missing_input_422(monkeypatch):
    resp = _client(monkeypatch).post("/v1/classify", json={})
    assert resp.status_code == 422


def test_classify_malformed_input_400(monkeypatch):
    # A ValueError from inference surfaces as a client error (400), not a 500.
    monkeypatch.setattr(server, "_classifier", _RaisingClassifier())
    resp = TestClient(server.app).post("/v1/classify", json={"input": "anything"})
    assert resp.status_code == 400
    assert "malformed input" in resp.json()["detail"].lower()
