# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the auditor plugin service wiring."""

from __future__ import annotations

from fastapi.routing import APIRoute
from nemo_auditor.jobs.audit import AuditJob
from nemo_auditor.service import AuditorPluginService
from nemo_platform_plugin.scheduler import submit_path_for


def _mounted_post_paths() -> set[str]:
    service = AuditorPluginService()
    paths: set[str] = set()
    for spec in service.get_routers():
        for route in spec.router.routes:
            if isinstance(route, APIRoute) and "POST" in route.methods:
                paths.add(f"/apis/auditor{spec.prefix}{route.path}")
    return paths


def test_audit_job_submit_route_is_mounted() -> None:
    assert submit_path_for(AuditJob, workspace="{workspace}") in _mounted_post_paths()
