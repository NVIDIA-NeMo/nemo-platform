# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_platform_plugin.authz_format import validate_static_authz_data
from nemo_platform_plugin.authz_merge import merge_authz_contributions


def test_merge_adds_endpoints_and_role_permissions() -> None:
    base = {
        "authz": {
            "permissions": {},
            "roles": {"Editor": {"permissions": ["jobs.read"]}, "Viewer": {"permissions": []}},
            "endpoints": {},
        }
    }
    overlay = [
        {
            "permissions": {
                "customization.automodel.jobs.create": "Create automodel jobs",
                "customization.automodel.jobs.read": "Read automodel jobs",
                "customization.automodel.jobs.export": "Export automodel jobs",
            },
            "role_permissions": {"Exporter": ["customization.automodel.jobs.export"]},
            "endpoints": {
                "/apis/customization/v2/workspaces/{workspace}/automodel/jobs": {
                    "post": {
                        "permissions": ["customization.automodel.jobs.create"],
                        "scopes": ["customization:write", "platform:write"],
                    },
                },
            },
        }
    ]
    merged = merge_authz_contributions(base, overlay)
    validate_static_authz_data(merged)
    endpoints = merged["authz"]["endpoints"]
    assert "post" in endpoints["/apis/customization/v2/workspaces/{workspace}/automodel/jobs"]
    editor_perms = merged["authz"]["roles"]["Editor"]["permissions"]
    assert "customization.automodel.jobs.create" in editor_perms
    viewer_perms = merged["authz"]["roles"]["Viewer"]["permissions"]
    assert "customization.automodel.jobs.read" in viewer_perms
    export_permission = "customization.automodel.jobs.export"
    assert export_permission in merged["authz"]["roles"]["Exporter"]["permissions"]
    # Admin inherits export permissions from Exporter via includes[] at OPA eval time,
    # so the merge does not need to add them directly to the Admin role.
    assert "Admin" not in merged["authz"]["roles"]
    assert export_permission not in editor_perms


def test_merge_does_not_make_read_permissions_exportable_implicitly() -> None:
    base = {
        "authz": {
            "permissions": {},
            "roles": {"Editor": {"permissions": []}, "Viewer": {"permissions": []}},
            "endpoints": {},
        }
    }

    merged = merge_authz_contributions(
        base,
        [{"permissions": {"sensitive.records.read": "Read sensitive records"}}],
    )

    assert "Exporter" not in merged["authz"]["roles"]
    assert "export" not in merged["authz"]["permissions"]["sensitive"]["records"]
