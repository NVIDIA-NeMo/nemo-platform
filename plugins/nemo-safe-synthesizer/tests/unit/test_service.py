# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_safe_synthesizer_plugin.service import SafeSynthesizerService


def test_service_metadata_preserves_public_name():
    service = SafeSynthesizerService()

    assert service.name == "safe-synthesizer"
    assert service.dependencies == ["entities", "auth", "jobs", "secrets", "files"]


def test_service_routes_include_safe_synthesizer_jobs_path():
    pytest.importorskip("nemo_safe_synthesizer.config.job")

    service = SafeSynthesizerService()
    app = FastAPI()
    for spec in service.get_routers():
        app.include_router(spec.router, prefix=spec.prefix)

    client = TestClient(app)
    spec = client.get("/openapi.json").json()

    assert "/v2/workspaces/{workspace}/jobs" in spec["paths"]
    assert "/v2/workspaces/{workspace}/jobs/{job}/results/adapter/download" in spec["paths"]
    assert "SafeSynthesizerJobRequest" in spec["components"]["schemas"]
