# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os

import pytest
from nemo_platform import APIStatusError
from nmp.testing import grant_workspace_role
from nmp.testing.e2e import wait_for_job_logs, wait_for_platform_job

from tests.auth_idp.authentik_live import AUTHENTIK_DOCKER_PYTESTMARK

pytestmark = AUTHENTIK_DOCKER_PYTESTMARK


def _nmp_api_image() -> str:
    registry = os.environ.get("IMAGE_REGISTRY", "my-registry")
    tag = os.environ.get("BAKE_TAG", "local")
    return f"{registry}/nmp-api:{tag}"


def test_authentik_workload_token_is_real(machine_token: str, authentik_provider):
    assert machine_token
    assert authentik_provider.token_endpoint


def test_authentik_workload_identity_is_denied_before_binding(machine_sdk, authentik_workspace):
    with pytest.raises(APIStatusError) as exc_info:
        machine_sdk.workspaces.retrieve(authentik_workspace)
    assert exc_info.value.status_code == 403


def test_authentik_workload_identity_is_allowed_after_binding(
    authentik_human_sdk,
    machine_sdk,
    authentik_workspace,
    authentik_provider,
):
    for group in authentik_provider.workload_expected_groups:
        grant_workspace_role(authentik_human_sdk, workspace=authentik_workspace, principal=group, roles=["Viewer"])

    retrieved = machine_sdk.workspaces.retrieve(authentik_workspace)
    assert retrieved.name == authentik_workspace


def test_authentik_workload_identity_returns_to_denied_after_revoke(
    authentik_human_sdk,
    machine_sdk,
    authentik_workspace,
    authentik_provider,
):
    for group in authentik_provider.workload_expected_groups:
        grant_workspace_role(
            authentik_human_sdk,
            workspace=authentik_workspace,
            principal=group,
            roles=["Viewer"],
        )
        authentik_human_sdk.workspaces.members.delete(
            group,
            workspace=authentik_workspace,
            wait_role_propagation=True,
        )

    with pytest.raises(APIStatusError) as exc_info:
        machine_sdk.workspaces.retrieve(authentik_workspace)
    assert exc_info.value.status_code == 403


def test_authentik_workload_job_runs_via_docker_profile(
    authentik_human_sdk,
    authentik_workspace,
    authentik_provider,
    machine_token: str,
):
    for group in authentik_provider.workload_expected_groups:
        grant_workspace_role(
            authentik_human_sdk,
            workspace=authentik_workspace,
            principal=group,
            roles=["Viewer", "JobRunner"],
        )

    job = authentik_human_sdk.jobs.create(
        workspace=authentik_workspace,
        source="authentik-live-workload-job",
        spec={"test": "workload-job"},
        platform_spec={
            "steps": [
                {
                    "name": "workload-workspace-get",
                    "executor": {
                        "provider": "cpu",
                        "profile": "workload",
                        "container": {
                            "image": _nmp_api_image(),
                            "entrypoint": ["sh", "-c"],
                            "command": ["nemo-platform run task --task nmp.hello_world.tasks.workload_workspace_get"],
                        },
                    },
                    "environment": [
                        {
                            "name": "NEMO_WORKLOAD_TOKEN",
                            "value": machine_token,
                        }
                    ],
                    "config": {
                        "workspace": authentik_workspace,
                    },
                }
            ]
        },
    )

    completed_job = wait_for_platform_job(authentik_human_sdk, job.name, authentik_workspace, timeout=240)
    assert completed_job.status == "completed"

    step_logs = wait_for_job_logs(authentik_human_sdk, job.name, authentik_workspace, min_log_count=1, timeout=240)
    assert any("Successfully retrieved workspace" in log.message for log in step_logs.data)
