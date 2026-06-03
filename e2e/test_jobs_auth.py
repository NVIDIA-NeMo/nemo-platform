"""E2E tests for jobs with auth enabled."""

from collections.abc import Callable

import pytest
from nemo_platform import NeMoPlatform
from nemo_platform_ext.auth.helpers import generate_unsigned_jwt
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    PlatformJobSpec,
    PlatformJobStep,
)
from nmp.common.entities import ALL_WORKSPACES
from nmp.testing import TEST_ADMIN_EMAIL, grant_workspace_role, short_unique_name, unique_email
from nmp.testing.e2e import wait_for_platform_job

JOB_SOURCE = "e2e-auth-test"

pytestmark = [pytest.mark.feature("auth")]


def _as_bearer_user(
    sdk: NeMoPlatform,
    email: str,
    *,
    groups: list[str] | None = None,
) -> NeMoPlatform:
    token = generate_unsigned_jwt(
        principal_id=email,
        email=email,
        groups=groups,
    )
    return sdk.with_options(set_default_headers={"Authorization": f"Bearer {token}"})


def test_job_principal_propagation(sdk: NeMoPlatform, image: Callable[[str], str]):
    admin_sdk = _as_bearer_user(sdk, TEST_ADMIN_EMAIL, groups=["admin"])
    user_email = unique_email("job-creator")
    workspace_name = short_unique_name("job-auth-test")

    admin_sdk.workspaces.create(name=workspace_name)
    grant_workspace_role(admin_sdk, workspace=workspace_name, principal=user_email, roles=["Editor"])

    user_sdk = _as_bearer_user(sdk, user_email)
    job = user_sdk.jobs.create(
        workspace=workspace_name,
        source=JOB_SOURCE,
        spec={"test": "auth-propagation"},
        platform_spec=PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="auth-test-step",
                    executor=CPUExecutionProviderSpec(
                        provider="cpu",
                        container=ContainerSpec(
                            image=image("nmp-cpu-tasks"),
                            entrypoint=["nemo-platform"],
                            command=["run", "task", "--task", "nmp.hello_world.tasks.hello_world"],
                        ),
                    ),
                    environment=[EnvironmentVariable(name="BUSY_LOOP_DURATION_SECONDS", value="0")],
                    config={"message": "auth propagation test"},
                )
            ]
        ),
    )

    completed_job = wait_for_platform_job(user_sdk, job.name, workspace_name)
    assert completed_job.status == "completed"

    fileset_name = f"hello-world-{job.name}"
    fileset = user_sdk.files.filesets.retrieve(workspace=workspace_name, name=fileset_name)
    assert fileset is not None

    file_content = user_sdk.files.download_content(
        remote_path="message.txt",
        fileset=fileset_name,
        workspace=workspace_name,
    )
    assert file_content == b"auth propagation test"


def test_job_cannot_access_unauthorized_workspace(sdk: NeMoPlatform, image: Callable[[str], str]):
    admin_sdk = _as_bearer_user(sdk, TEST_ADMIN_EMAIL, groups=["admin"])
    owner_email = unique_email("owner")
    other_email = unique_email("other")

    restricted_workspace = short_unique_name("restricted")
    runner_workspace = short_unique_name("runner")

    admin_sdk.workspaces.create(name=restricted_workspace)
    admin_sdk.workspaces.create(name=runner_workspace)
    grant_workspace_role(admin_sdk, workspace=restricted_workspace, principal=owner_email, roles=["Editor"])
    grant_workspace_role(admin_sdk, workspace=runner_workspace, principal=other_email, roles=["Editor"])

    owner_sdk = _as_bearer_user(sdk, owner_email)
    other_sdk = _as_bearer_user(sdk, other_email)

    fileset_name = "private-data"
    owner_sdk.files.filesets.create(workspace=restricted_workspace, name=fileset_name)

    job = other_sdk.jobs.create(
        workspace=runner_workspace,
        source=JOB_SOURCE,
        spec={"test": "auth-denial"},
        platform_spec=PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="access-test-step",
                    executor=CPUExecutionProviderSpec(
                        provider="cpu",
                        container=ContainerSpec(
                            image=image("nmp-cpu-tasks"),
                            entrypoint=["nemo-platform"],
                            command=["run", "task", "--task", "nmp.hello_world.tasks.access_fileset"],
                        ),
                    ),
                    config={
                        "workspace": restricted_workspace,
                        "fileset": fileset_name,
                    },
                )
            ]
        ),
    )

    completed_job = wait_for_platform_job(other_sdk, job.name, runner_workspace)
    assert completed_job.status == "error"

    tasks_response = other_sdk.jobs.tasks.list("access-test-step", job=job.name, workspace=runner_workspace)
    assert tasks_response.data
    task = tasks_response.data[0]
    assert task.error_stack
    assert "403" in task.error_stack and "Forbidden" in task.error_stack


def test_job_admin_can_list_jobs_in_all_workspaces(sdk: NeMoPlatform, image: Callable[[str], str]):
    admin_sdk = _as_bearer_user(sdk, TEST_ADMIN_EMAIL, groups=["admin"])
    user_email = unique_email("member")
    workspace_name = short_unique_name("admin-list-jobs")

    admin_sdk.workspaces.create(name=workspace_name)
    grant_workspace_role(admin_sdk, workspace=workspace_name, principal=user_email, roles=["Editor"])

    user_sdk = _as_bearer_user(sdk, user_email)
    job = user_sdk.jobs.create(
        workspace=workspace_name,
        source=JOB_SOURCE,
        spec={"test": "admin-list"},
        platform_spec=PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="admin-list-step",
                    executor=CPUExecutionProviderSpec(
                        provider="cpu",
                        container=ContainerSpec(
                            image=image("nmp-cpu-tasks"),
                            command=["echo", "admin list jobs"],
                        ),
                    ),
                )
            ]
        ),
    )

    completed_job = wait_for_platform_job(user_sdk, job.name, workspace_name)
    assert completed_job.status == "completed"

    jobs = admin_sdk.jobs.list(workspace=ALL_WORKSPACES)
    assert jobs.pagination is not None
    assert any(item.name == job.name for item in jobs.data)
