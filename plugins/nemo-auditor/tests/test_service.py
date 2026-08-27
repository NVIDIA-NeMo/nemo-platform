# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the auditor plugin service wiring."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import APIRouter
from fastapi.routing import APIRoute
from nemo_auditor.jobs.audit import AuditJob
from nemo_auditor.service import AuditorPluginService
from nemo_platform_plugin.scheduler import submit_path_for


def _mounted_post_paths() -> set[str]:
    service = AuditorPluginService()
    paths: set[str] = set()
    for spec in service.get_routers():
        for route in spec.router.routes:
            if isinstance(route, APIRoute) and route.methods is not None and "POST" in route.methods:
                paths.add(f"/apis/auditor{spec.prefix}{route.path}")
    return paths


def test_audit_job_submit_route_is_mounted() -> None:
    assert submit_path_for(AuditJob, workspace="{workspace}") in _mounted_post_paths()


def test_audit_job_routes_default_to_auditor_profile() -> None:
    """Jobs submitted without an explicit --profile land on the "auditor" profile,
    not the platform-wide "default" one."""
    with patch("nemo_auditor.service.add_job_routes") as mock_add_job_routes:
        mock_add_job_routes.return_value = APIRouter()
        AuditorPluginService().get_routers()

    mock_add_job_routes.assert_called_once()
    assert mock_add_job_routes.call_args.kwargs["default_profile"] == "auditor"
