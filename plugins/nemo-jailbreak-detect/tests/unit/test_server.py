# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the standalone model server's NIM-compatible contract."""

from __future__ import annotations

from fastapi.testclient import TestClient
from nemo_jailbreak_detect.model import server


class _FakeClassifier:
    def __call__(self, text: str) -> tuple[bool, float]:
        return (True, 0.87) if "dan" in text.lower() else (False, -0.95)


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(server, "_classifier", _FakeClassifier())
    return TestClient(server.app)


def test_health_ready(monkeypatch):
    resp = _client(monkeypatch).get("/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"object": "health-response", "message": "ready"}


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
