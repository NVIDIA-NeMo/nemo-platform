# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_intake_plugin.spans.api.dependencies import get_created_by


def test_get_created_by_reads_validated_principal_header() -> None:
    app = FastAPI()
    app.get("/")(get_created_by)

    response = TestClient(app).get("/", headers={"X-NMP-Principal-Id": "user@example.com"})

    assert response.status_code == 200
    assert response.json() == "user@example.com"


def test_get_created_by_returns_none_without_principal_header() -> None:
    app = FastAPI()
    app.get("/")(get_created_by)

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json() is None
