# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for task-side auth propagation via ``NMP_PRINCIPAL``.

These tests cover the runtime half of the jobs auth propagation story:

- the task receives ``NMP_PRINCIPAL``
- ``get_task_sdk(as_service=...)`` converts that into service + on-behalf-of headers
- downstream services authorize based on the delegated user's permissions
"""

from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType

import pytest
from nemo_platform import PermissionDeniedError
from nmp.core.secrets.service import SecretsService
from nmp.testing import (
    TEST_ADMIN_EMAIL,
    ClientContext,
    as_user,
    create_test_client,
    grant_workspace_role,
    short_unique_name,
    unique_email,
)


def _secret_access_task_module() -> ModuleType:
    module = ModuleType("task_auth_runtime_test_module")

    def run(*, http_client) -> int:
        from nmp.common.sdk_factory import get_task_sdk

        workspace = os.environ["NEMO_JOB_WORKSPACE"]
        secret_name = os.environ["NEMO_TEST_SECRET_NAME"]

        result = get_task_sdk(as_service="jobs", http_client=http_client).secrets.access(
            workspace=workspace,
            name=secret_name,
        )
        print(result.value)
        return 0

    module.run = run
    return module


class TestTaskRuntimeAuthPropagation:
    def test_task_sdk_accesses_secret_on_behalf_of_creator(self):
        workspace = short_unique_name("task-obo")
        secret_name = short_unique_name("secret")
        secret_value = "task-visible-secret"
        creator_email = unique_email("creator")

        with create_test_client(
            SecretsService,
            auth_enabled=True,
            access_log=True,
            client_type=ClientContext,
            workspaces=[workspace],
        ) as ctx:
            admin_sdk = as_user(ctx.sdk, TEST_ADMIN_EMAIL)
            admin_sdk.secrets.create(workspace=workspace, name=secret_name, value=secret_value)
            grant_workspace_role(
                admin_sdk,
                workspace=workspace,
                principal=creator_email,
                roles=["Viewer"],
            )

            ctx.access_log.clear()
            stdout = StringIO()
            with (
                redirect_stdout(stdout),
                pytest.MonkeyPatch.context() as monkeypatch,
            ):
                monkeypatch.setenv("NEMO_JOB_WORKSPACE", workspace)
                monkeypatch.setenv("NEMO_TEST_SECRET_NAME", secret_name)
                monkeypatch.setenv(
                    "NMP_PRINCIPAL",
                    json.dumps(
                        {
                            "id": creator_email,
                            "email": creator_email,
                            "groups": [],
                        }
                    ),
                )
                exit_code = _secret_access_task_module().run(http_client=ctx.test_client)

            assert exit_code == 0
            assert secret_value in stdout.getvalue()

            request = ctx.access_log.assert_has_request(
                method="GET",
                path_contains=f"/apis/secrets/v2/workspaces/{workspace}/secrets/{secret_name}/access",
                principal_id="service:jobs",
            )
            assert request.on_behalf_of == creator_email

    def test_task_sdk_denies_secret_access_when_creator_lacks_permission(self):
        workspace = short_unique_name("task-deny")
        secret_name = short_unique_name("secret")
        creator_email = unique_email("creator")

        with create_test_client(
            SecretsService,
            auth_enabled=True,
            access_log=True,
            client_type=ClientContext,
            workspaces=[workspace],
        ) as ctx:
            admin_sdk = as_user(ctx.sdk, TEST_ADMIN_EMAIL)
            admin_sdk.secrets.create(workspace=workspace, name=secret_name, value="secret-value")

            ctx.access_log.clear()
            with (
                pytest.MonkeyPatch.context() as monkeypatch,
                pytest.raises(PermissionDeniedError),
            ):
                monkeypatch.setenv("NEMO_JOB_WORKSPACE", workspace)
                monkeypatch.setenv("NEMO_TEST_SECRET_NAME", secret_name)
                monkeypatch.setenv(
                    "NMP_PRINCIPAL",
                    json.dumps(
                        {
                            "id": creator_email,
                            "email": creator_email,
                            "groups": [],
                        }
                    ),
                )
                _secret_access_task_module().run(http_client=ctx.test_client)

            request = ctx.access_log.assert_has_request(
                method="GET",
                path_contains=f"/apis/secrets/v2/workspaces/{workspace}/secrets/{secret_name}/access",
                principal_id="service:jobs",
            )
            assert request.on_behalf_of == creator_email
