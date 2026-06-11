# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_safe_synthesizer_plugin.service import SafeSynthesizerService
from nmp.common.auth.authz_format import validate_static_authz_data
from nmp.common.auth.authz_merge import merge_authz_contributions


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


def test_service_authz_contribution_matches_legacy_job_policy():
    contribution = SafeSynthesizerService.get_authz_contribution()
    base_authz = {
        "authz": {
            "permissions": {},
            "roles": {
                "Viewer": {"permissions": []},
                "Editor": {"permissions": []},
            },
            "endpoints": {},
        }
    }

    merged = merge_authz_contributions(base_authz, [contribution.to_dict()])

    validate_static_authz_data(merged)
    viewer_permissions = merged["authz"]["roles"]["Viewer"]["permissions"]
    editor_permissions = merged["authz"]["roles"]["Editor"]["permissions"]
    endpoints = merged["authz"]["endpoints"]

    assert "safe-synthesizer.jobs.list" in viewer_permissions
    assert "safe-synthesizer.jobs.read" in viewer_permissions
    assert "safe-synthesizer.jobs.cancel" in editor_permissions
    assert "safe-synthesizer.jobs.create" in editor_permissions
    assert "safe-synthesizer.jobs.delete" in editor_permissions

    jobs_path = "/apis/safe-synthesizer/v2/workspaces/{workspace}/jobs"
    assert endpoints[jobs_path]["get"]["permissions"] == ["safe-synthesizer.jobs.list"]
    assert endpoints[jobs_path]["post"]["scopes"] == ["safe-synthesizer:write", "platform:write"]
    assert endpoints[f"{jobs_path}/{{name}}/cancel"]["post"]["permissions"] == ["safe-synthesizer.jobs.cancel"]
    assert endpoints[f"{jobs_path}/{{job}}/results/synthetic-data/download"]["get"]["permissions"] == [
        "safe-synthesizer.jobs.read"
    ]
