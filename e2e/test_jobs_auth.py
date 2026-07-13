"""E2E tests for jobs with auth enabled.

Local E2E runs translate ``cpu/default`` container steps to the subprocess
backend, so these tests intentionally omit ``container.image`` and rely only on
the command shape that subprocess consumes.
"""

import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

import pytest
from nemo_platform import NeMoPlatform
from nemo_platform_ext.auth.helpers import generate_unsigned_jwt
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient
from nemo_platform_plugin.files.types import CreateFilesetRequest
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    PlatformJobSpec,
    PlatformJobStep,
)
from nmp.common.entities import ALL_WORKSPACES
from nmp.core.jobs.controllers.diagnostics import collect_job_diagnostics
from nmp.testing import TEST_ADMIN_EMAIL, grant_workspace_role, short_unique_name, unique_email
from nmp.testing.e2e import wait_for_platform_job

JOB_SOURCE = "e2e-auth-test"
logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.subprocess_only,
    pytest.mark.e2e_config("e2e/configs/local-subprocess.yaml", {"auth": {"enabled": True}}),
]


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


def _log_auth_job_diagnostics(
    sdk: NeMoPlatform,
    *,
    workspace: str,
    job_name: str,
    step_name: str,
    context: str,
) -> None:
    logger.error(
        "Auth job diagnostics",
        extra={
            "diagnostic_context": context,
            "workspace": workspace,
            "job_name": job_name,
            "step_name": step_name,
            "job_diagnostics": collect_job_diagnostics(
                sdk,
                workspace=workspace,
                job_name=job_name,
                step_name=step_name,
                context=context,
            ),
        },
    )


@contextmanager
def _managed_admin_workspace(admin_sdk: NeMoPlatform, workspace_name: str) -> Iterator[str]:
    admin_sdk.workspaces.create(name=workspace_name)
    try:
        yield workspace_name
    finally:
        admin_sdk.workspaces.delete(workspace_name)


def _job_exists_in_pages(jobs_page: object, job_name: str) -> bool:
    return any(item.name == job_name for page in jobs_page.iter_pages() for item in page.data)


def test_job_principal_propagation(sdk: NeMoPlatform):
    admin_sdk = _as_bearer_user(sdk, TEST_ADMIN_EMAIL, groups=["admin"])
    user_email = unique_email("job-creator")
    workspace_name = short_unique_name("job-auth-test")

    with _managed_admin_workspace(admin_sdk, workspace_name):
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
        files = client_from_platform(user_sdk, FilesClient)
        fileset = files.get_fileset(workspace=workspace_name, name=fileset_name).data()
        assert fileset is not None

        file_content = user_sdk.files.download_content(
            remote_path="message.txt",
            fileset=fileset_name,
            workspace=workspace_name,
        )
        assert file_content == b"auth propagation test"


def test_job_cannot_access_unauthorized_workspace(sdk: NeMoPlatform):
    admin_sdk = _as_bearer_user(sdk, TEST_ADMIN_EMAIL, groups=["admin"])
    owner_email = unique_email("owner")
    other_email = unique_email("other")

    restricted_workspace = short_unique_name("restricted")
    runner_workspace = short_unique_name("runner")

    with ExitStack() as stack:
        stack.enter_context(_managed_admin_workspace(admin_sdk, restricted_workspace))
        stack.enter_context(_managed_admin_workspace(admin_sdk, runner_workspace))
        grant_workspace_role(admin_sdk, workspace=restricted_workspace, principal=owner_email, roles=["Editor"])
        grant_workspace_role(admin_sdk, workspace=runner_workspace, principal=other_email, roles=["Editor"])

        owner_sdk = _as_bearer_user(sdk, owner_email)
        other_sdk = _as_bearer_user(sdk, other_email)

        fileset_name = "private-data"
        files = client_from_platform(owner_sdk, FilesClient)
        files.create_fileset(workspace=restricted_workspace, body=CreateFilesetRequest(name=fileset_name))

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
        if completed_job.status != "error":
            _log_auth_job_diagnostics(
                other_sdk,
                workspace=runner_workspace,
                job_name=job.name,
                step_name="access-test-step",
                context="expected job to fail with unauthorized workspace access",
            )
        assert completed_job.status == "error"

        tasks_response = other_sdk.jobs.tasks.list("access-test-step", job=job.name, workspace=runner_workspace)
        if not tasks_response.data:
            _log_auth_job_diagnostics(
                other_sdk,
                workspace=runner_workspace,
                job_name=job.name,
                step_name="access-test-step",
                context="expected task list to include failed access task",
            )
        assert tasks_response.data
        task = tasks_response.data[0]
        if not task.error_stack or "403" not in task.error_stack or "Forbidden" not in task.error_stack:
            _log_auth_job_diagnostics(
                other_sdk,
                workspace=runner_workspace,
                job_name=job.name,
                step_name="access-test-step",
                context="expected task error stack to include 403 forbidden details",
            )
        assert task.error_stack
        assert "403" in task.error_stack and "Forbidden" in task.error_stack


def test_job_admin_can_list_jobs_in_all_workspaces(sdk: NeMoPlatform):
    admin_sdk = _as_bearer_user(sdk, TEST_ADMIN_EMAIL, groups=["admin"])
    user_email = unique_email("member")
    workspace_name = short_unique_name("admin-list-jobs")

    with _managed_admin_workspace(admin_sdk, workspace_name):
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
        assert _job_exists_in_pages(jobs, job.name)
