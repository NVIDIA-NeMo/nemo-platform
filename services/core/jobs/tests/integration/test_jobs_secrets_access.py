# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for job creation with secret references and user-scoped SDK.

Validates that when creating a job that references platform secrets:
- If the user has access to the secret (same workspace or other workspace they can access),
  job creation succeeds.
- If the user does not have access to the secret (e.g. secret in another workspace they
  are not a member of), job creation fails with a clear error.

The jobs API uses the request-scoped (user) SDK for secret validation so that only
secrets the user can access are allowed in the job spec.
"""

from typing import Generator

import pytest
from nemo_platform import NeMoPlatform
from nmp.core.files.service import FilesService
from nmp.core.jobs.service import JobsService
from nmp.core.secrets.service import SecretsService
from nmp.testing import (
    TEST_ADMIN_EMAIL,
    as_user,
    create_test_client,
    short_unique_name,
    unique_email,
)


@pytest.fixture(scope="module")
def sdk() -> Generator[NeMoPlatform, None, None]:
    """SDK client with JobsService, FilesService, and SecretsService (auth enabled)."""
    with create_test_client(
        JobsService,
        FilesService,
        SecretsService,
        auth_enabled=True,
    ) as sdk:
        yield sdk


def _platform_spec_with_secret(secret_ref: str, env_var_name: str = "MY_SECRET") -> dict:
    """Build platform_spec with one step that references a secret."""
    return {
        "steps": [
            {
                "name": "step-with-secret",
                "executor": {
                    "provider": "cpu",
                    "profile": "default",
                    "container": {
                        "image": "busybox:latest",
                        "entrypoint": ["entrypoint"],
                        "command": ["command"],
                    },
                },
                "environment": [
                    {"name": env_var_name, "from_secret": {"name": secret_ref}},
                ],
            },
        ],
    }


@pytest.mark.integration
class TestJobCreationWithSecretsAccess:
    """Job creation with secret references: allowed when user has access, denied when not."""

    def test_create_job_with_secret_user_has_access_succeeds(self, sdk: NeMoPlatform):
        """When the user has access to the secret, job creation succeeds."""
        workspace = "default"
        secret_name = short_unique_name("job-secret")
        job_name = short_unique_name("job-with-secret")
        user_email = unique_email("editor")

        admin_sdk = as_user(sdk, TEST_ADMIN_EMAIL)
        admin_sdk.secrets.create(
            workspace=workspace,
            name=secret_name,
            value="secret-value-for-job",
        )
        admin_sdk.members.create(
            workspace=workspace,
            principal=user_email,
            roles=["Editor"],
            wait_role_propagation=True,
        )

        user_sdk = as_user(sdk, user_email)
        job = user_sdk.jobs.create(
            workspace=workspace,
            name=job_name,
            source="integration-test",
            spec={},
            platform_spec=_platform_spec_with_secret(secret_name),
        )

        assert job.id is not None
        assert job.name == job_name
        assert job.workspace == workspace

    def test_create_job_with_secret_user_lacks_access_fails(self, sdk: NeMoPlatform):
        """When the user does not have access to the secret (other workspace), job creation fails."""
        workspace_own = short_unique_name("user-ws")
        workspace_other = short_unique_name("other-ws")
        secret_name = short_unique_name("other-secret")
        job_name = short_unique_name("job-denied-secret")
        user_email = unique_email("user")

        admin_sdk = as_user(sdk, TEST_ADMIN_EMAIL)
        admin_sdk.workspaces.create(name=workspace_own)
        admin_sdk.workspaces.create(name=workspace_other)
        admin_sdk.members.create(
            workspace=workspace_own,
            principal=user_email,
            roles=["Editor"],
            wait_role_propagation=True,
        )
        # Secret only in workspace_other; user is not a member of workspace_other
        admin_sdk.secrets.create(
            workspace=workspace_other,
            name=secret_name,
            value="secret-in-other-ws",
        )

        user_sdk = as_user(sdk, user_email)
        # Reference secret in workspace user cannot access (workspace_other/secret_name)
        secret_ref = f"{workspace_other}/{secret_name}"

        with pytest.raises(Exception) as exc_info:
            user_sdk.jobs.create(
                workspace=workspace_own,
                name=job_name,
                source="integration-test",
                spec={},
                platform_spec=_platform_spec_with_secret(secret_ref),
            )

        msg = str(exc_info.value).lower()
        assert "secret" in msg and ("not found" in msg or "access" in msg or "403" in msg)

    def test_create_job_with_nonexistent_secret_fails(self, sdk: NeMoPlatform):
        """When the referenced secret does not exist, job creation fails."""
        workspace = "default"
        job_name = short_unique_name("job-missing-secret")
        user_email = unique_email("user")

        admin_sdk = as_user(sdk, TEST_ADMIN_EMAIL)
        admin_sdk.members.create(
            workspace=workspace,
            principal=user_email,
            roles=["Editor"],
            wait_role_propagation=True,
        )

        user_sdk = as_user(sdk, user_email)
        with pytest.raises(Exception) as exc_info:
            user_sdk.jobs.create(
                workspace=workspace,
                name=job_name,
                source="integration-test",
                spec={},
                platform_spec=_platform_spec_with_secret("nonexistent-secret-name"),
            )

        msg = str(exc_info.value).lower()
        assert "secret" in msg and "not found" in msg
