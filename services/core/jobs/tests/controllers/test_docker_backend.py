# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime
import json
import uuid
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from docker.errors import APIError, NotFound
from nemo_platform.types.shared import AuthContext as SdkAuthContext
from nmp.common.auth import NMP_PRINCIPAL_ENVVAR, AuthContext, Principal
from nmp.common.docker.gpu_pool import DockerGPUPool
from nmp.common.jobs.constants import (
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    NEMO_JOB_FILESET_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.core.jobs.api.v2.jobs.schemas import PlatformJobStepWithContext
from nmp.core.jobs.app.constants import (
    JOB_CONTROLLER_INSTANCE_ID_LABEL,
    JOB_EXECUTION_BACKEND_LABEL,
    JOB_EXECUTION_PROFILE_LABEL,
    JOB_ID_LABEL,
    JOB_MANAGED_BY_JOBS_CONTROLLER,
    JOB_MANAGED_BY_LABEL,
    JOB_STEP_ID_LABEL,
    JOB_STEP_NAME_LABEL,
    JOB_TASK_ID_LABEL,
    JOB_TYPE_JOB,
    JOB_TYPE_LABEL,
    JOB_TYPE_STORAGE_CLEANUP,
    JOB_USES_PERSISTENT_STORAGE_LABEL,
    JOB_WORKSPACE_ID_LABEL,
)
from nmp.core.jobs.app.providers import (
    ComputeResources,
    ComputeResourceSpec,
    ContainerSpec,
    CPUExecutionProvider,
    GPUExecutionProvider,
)
from nmp.core.jobs.app.schemas import (
    PlatformJobEnvironmentVariable,
    PlatformJobSecretEnvironmentVariableRef,
    PlatformJobStepSpec,
)
from nmp.core.jobs.controllers.backends.docker import (
    DEFAULT_VOLUME_PERMISSIONS_IMAGE,
    DOCKER_CONTAINER_START_WORKERS,
    CPUDockerJobBackend,
    DockerJobExecutionProfileConfig,
    DockerJobStorageConfig,
    DockerVolumeMount,
    GPUDockerJobBackend,
)
from nmp.core.jobs.controllers.backends.exceptions import (
    FailedToScheduleError,
    ResourceAllocationError,
    SchedulingDeferred,
)
from pydantic import ValidationError

from services.core.jobs.tests.controllers.client_mocks import data_response

TEST_JOBS_CONTROLLER_INSTANCE_ID = "test-owner"


@pytest.fixture(autouse=True)
def docker_owner_id(monkeypatch):
    monkeypatch.setenv("NMP_JOBS_DOCKER_OWNER_ID", TEST_JOBS_CONTROLLER_INSTANCE_ID)


def owned_container_labels(labels: dict) -> dict:
    return {
        **labels,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }


@pytest.fixture
def docker_client_mock(monkeypatch):
    """Mock docker client for testing."""

    # Needed so we can look up the current container's docker network.
    monkeypatch.setenv("HOSTNAME", "docker123")
    mock_container = MagicMock()
    mock_container.attrs = {"NetworkSettings": {"Networks": {"mock_network": "network_settings"}}}

    with patch("docker.from_env") as mock_docker_client:
        client = MagicMock()
        mock_docker_client.return_value = client

        # Set up containers.get behavior: return current container for hostname lookup,
        # but raise NotFound for job containers (so they get created in schedule tests)
        # However, allow tests to override this behavior by setting return_value
        def get_container_side_effect(name):
            if name == "docker123":  # hostname lookup
                return mock_container
            else:  # job containers
                raise NotFound("Container not found")

        client.containers.get.side_effect = get_container_side_effect
        client.containers.get._original_side_effect = get_container_side_effect

        mock_volume = MagicMock()
        client.volumes.get.return_value = mock_volume
        client.volumes.create.return_value = mock_volume

        # Patch containers.create to return a mock with .wait() returning success by default
        def create_container_mock(*args, **kwargs):
            container = MagicMock()
            container.id = kwargs.get("name", "mock-container-id")
            container.labels = kwargs.get("labels", {})
            # By default, .wait() returns success
            container.wait.return_value = {"StatusCode": 0}
            container.put_archive.return_value = None
            container.start.return_value = None
            container.remove.return_value = None
            return container

        client.containers.create.side_effect = create_container_mock

        yield client


@pytest.fixture
def docker_job(mock_nmp_client, docker_client_mock, mock_platform_config) -> Iterator[CPUDockerJobBackend]:
    """Create a DockerJobBackend instance with mocked docker client."""
    with patch("nmp.core.jobs.controllers.backends.docker.get_platform_config", return_value=mock_platform_config):
        docker_job = CPUDockerJobBackend(
            mock_nmp_client,
            DockerJobExecutionProfileConfig(storage=DockerJobStorageConfig(volume_name="test_jobs_storage")),
            profile_name="default",
        )
        docker_job._client = docker_client_mock
        yield docker_job


@pytest.fixture
def test_job_step():
    """Create a test job step for testing."""
    return PlatformJobStepWithContext(
        id="test-step-id",
        job="job-test-job-id",
        attempt_id="test-job-attempt-id",
        fileset="test-logs-fileset",
        workspace="default",
        name="test-step",
        step_spec=PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(
                provider="cpu",
                profile="default",
                container=ContainerSpec(image="test-image"),
                resources=ComputeResources(
                    limits=ComputeResourceSpec(
                        cpu="5",
                        memory="2Gi",
                    )
                ),
            ),
            config={"test_param": "value"},
            environment=[
                PlatformJobEnvironmentVariable(name="ENV_VAR", value="test_value"),
                PlatformJobEnvironmentVariable(name=EPHEMERAL_TASK_STORAGE_PATH_ENVVAR, value="/var/tmp"),
            ],
        ),
        status=PlatformJobStatus.PENDING,
    )


@pytest.fixture
def test_job_step_with_persistence():
    """Create a test job step for testing."""
    return PlatformJobStepWithContext(
        id="test-step-id",
        job="job-test-job-id",
        attempt_id="test-job-attempt-id",
        fileset="test-logs-fileset",
        name="test-step",
        workspace="default",
        step_spec=PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(
                provider="cpu",
                profile="default",
                container=ContainerSpec(image="test-image"),
                resources=ComputeResources(
                    limits=ComputeResourceSpec(
                        cpu="5",
                        memory="2Gi",
                    )
                ),
            ),
            config={"test_param": "value"},
            environment=[
                PlatformJobEnvironmentVariable(name="ENV_VAR", value="test_value"),
                PlatformJobEnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value="/var/test"),
                PlatformJobEnvironmentVariable(name=EPHEMERAL_TASK_STORAGE_PATH_ENVVAR, value="/var/tmp"),
            ],
        ),
        status=PlatformJobStatus.PENDING,
    )


def test_docker_job_schedule(docker_job, docker_client_mock, test_job_step):
    """Test that the schedule method calls docker client correctly."""
    # Setup
    step_spec = test_job_step.step_spec
    executor_config = step_spec.executor

    # Track created containers
    created_containers = []
    original_create_side_effect = docker_client_mock.containers.create.side_effect

    def track_create(*args, **kwargs):
        container = original_create_side_effect(*args, **kwargs)
        created_containers.append(container)
        return container

    docker_client_mock.containers.create.side_effect = track_create

    # Execute
    docker_job.schedule(executor_config, test_job_step)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Assert - should call containers.create twice: once for job-init container, once for job container
    assert docker_client_mock.containers.run.call_count == 0
    assert docker_client_mock.containers.create.call_count == 2

    # Get the job container call arguments (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    kwargs = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    # Verify container configuration
    assert kwargs["name"] == "job-test-job-id-test-step"
    assert kwargs["image"] == "test-image"
    assert kwargs["detach"] is True

    # Verify execution profile labels on job container
    assert "labels" in kwargs
    assert kwargs["labels"][JOB_CONTROLLER_INSTANCE_ID_LABEL] == TEST_JOBS_CONTROLLER_INSTANCE_ID
    assert kwargs["labels"][JOB_EXECUTION_BACKEND_LABEL] == "docker"
    assert kwargs["labels"][JOB_EXECUTION_PROFILE_LABEL] == "default"

    # Verify environment variables
    env = kwargs["environment"]
    assert NEMO_JOB_ID_ENVVAR in env
    assert NEMO_JOB_WORKSPACE_ENVVAR in env
    assert NEMO_JOB_FILESET_ENVVAR in env
    assert env[NEMO_JOB_FILESET_ENVVAR] == "test-logs-fileset"
    assert "ENV_VAR" in env
    assert env["ENV_VAR"] == "test_value"
    assert PERSISTENT_JOB_STORAGE_PATH_ENVVAR not in env
    assert env[EPHEMERAL_TASK_STORAGE_PATH_ENVVAR] == "/var/tmp"

    # Assert that config warnings are disabled
    assert env["NMP_CONFIG_WARNINGS_DISABLED"] == "1"

    # Verify resource constraints
    assert kwargs["mem_limit"] == "2g"
    assert kwargs["cpu_count"] == 5

    # Verify mounts are used instead of volumes
    assert "mounts" in kwargs

    # Verify container.start was called on both containers (init container and job container)
    assert len(created_containers) == 2
    # First container is job-init, second is the actual job container
    created_containers[0].start.assert_called_once()  # job-init container
    created_containers[1].start.assert_called_once()  # job container


def test_docker_job_with_persistence_schedule(docker_job, docker_client_mock, test_job_step_with_persistence):
    """Test that the schedule method calls docker client correctly."""
    # Setup
    step_spec = test_job_step_with_persistence.step_spec
    executor_config = step_spec.executor

    # Track created containers
    created_containers = []
    original_create_side_effect = docker_client_mock.containers.create.side_effect

    def track_create(*args, **kwargs):
        container = original_create_side_effect(*args, **kwargs)
        created_containers.append(container)
        return container

    docker_client_mock.containers.create.side_effect = track_create

    # Execute
    docker_job.schedule(executor_config, test_job_step_with_persistence)
    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Assert - should call containers.create twice: once for job-init container, once for job container
    assert docker_client_mock.containers.run.call_count == 0
    assert docker_client_mock.containers.create.call_count == 2

    # Get the job container call arguments (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    kwargs = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    # Verify container configuration
    assert kwargs["name"] == "job-test-job-id-test-step"
    assert kwargs["image"] == "test-image"
    assert kwargs["detach"] is True

    # Verify execution profile labels on job container
    assert "labels" in kwargs
    assert kwargs["labels"][JOB_CONTROLLER_INSTANCE_ID_LABEL] == TEST_JOBS_CONTROLLER_INSTANCE_ID
    assert kwargs["labels"][JOB_EXECUTION_BACKEND_LABEL] == "docker"
    assert kwargs["labels"][JOB_EXECUTION_PROFILE_LABEL] == "default"

    # Verify environment variables
    env = kwargs["environment"]
    assert NEMO_JOB_ID_ENVVAR in env
    assert NEMO_JOB_WORKSPACE_ENVVAR in env
    assert NEMO_JOB_FILESET_ENVVAR in env
    assert env[NEMO_JOB_FILESET_ENVVAR] == "test-logs-fileset"
    assert "ENV_VAR" in env
    assert env["ENV_VAR"] == "test_value"
    assert env[PERSISTENT_JOB_STORAGE_PATH_ENVVAR] == "/var/test"
    assert env[EPHEMERAL_TASK_STORAGE_PATH_ENVVAR] == "/var/tmp"

    # Assert that config warnings are disabled
    assert env["NMP_CONFIG_WARNINGS_DISABLED"] == "1"

    # Verify resource constraints
    assert kwargs["mem_limit"] == "2g"
    assert kwargs["cpu_count"] == 5

    # Verify mounts are used instead of volumes
    assert "mounts" in kwargs

    # Verify container.start was called on both containers (init container and job container)
    assert len(created_containers) == 2
    created_containers[0].start.assert_called_once()  # job-init container
    created_containers[1].start.assert_called_once()  # job container


def test_docker_job_sync(docker_job, docker_client_mock, test_job_step):
    """Test that the sync method correctly interprets container status."""
    # Setup container mock with "running" status
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.status = "running"
    container_mock.attrs = {"State": {"ExitCode": 0}}
    task_id = uuid.uuid4().hex
    container_mock.labels = {
        JOB_WORKSPACE_ID_LABEL: test_job_step.workspace,
        JOB_ID_LABEL: test_job_step.job,
        JOB_STEP_NAME_LABEL: test_job_step.name,
        JOB_TASK_ID_LABEL: task_id,
    }
    # Error-path status derivation reads container.logs(...).decode() for error_stack.
    container_mock.logs.return_value = b"boom"
    # Clear side_effect so return_value takes precedence
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Test sync with running container
    update = docker_job.sync(test_job_step)
    assert update.status == "active"
    docker_client_mock.containers.get.assert_called_with("job-test-job-id-test-step")
    container_mock.remove.assert_not_called()
    # Volume should not be removed for running container
    docker_client_mock.volumes.get.return_value.remove.assert_not_called()

    # Reset call count
    docker_client_mock.containers.get.reset_mock()

    # Test sync with exited container (success)
    container_mock.status = "exited"
    update = docker_job.sync(test_job_step)
    assert update.status == "completed"
    # Container removed as part of cleanup_steps
    container_mock.remove.assert_not_called()

    # Reset for next test
    container_mock.remove.reset_mock()
    docker_client_mock.volumes.get.reset_mock()
    docker_client_mock.volumes.get.return_value.remove.reset_mock()

    # Test sync with exited container (failure)
    docker_client_mock.containers.get.reset_mock()
    container_mock.attrs = {"State": {"ExitCode": 1}}
    update = docker_job.sync(test_job_step)
    assert update.status == "error"
    container_mock.remove.assert_not_called()
    docker_client_mock.volumes.get.assert_not_called()

    # Test sync with container not found
    docker_client_mock.containers.get.side_effect = NotFound("Container not found")
    update = docker_job.sync(test_job_step)
    assert update.status == "pending"

    # Test sync with container not found and job not in pending state
    test_job_step.status = PlatformJobStatus.ACTIVE
    update = docker_job.sync(test_job_step)
    assert update.status == "error"


def test_docker_job_sync_pausing_sigterm(docker_job, docker_client_mock, test_job_step):
    """Test that the cancel method stops the container."""

    test_job_step.status = PlatformJobStatus.PAUSING
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.status = "exited"
    container_mock.attrs = {"State": {"ExitCode": 0}}  # SIGTERM will set exit code 0 if exited gracefully
    task_id = uuid.uuid4().hex
    container_mock.labels = owned_container_labels(
        {
            JOB_WORKSPACE_ID_LABEL: test_job_step.workspace,
            JOB_ID_LABEL: test_job_step.job,
            JOB_STEP_NAME_LABEL: test_job_step.name,
            JOB_TASK_ID_LABEL: task_id,
        }
    )
    # Clear side_effect so return_value takes precedence
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Test sync with running container
    update = docker_job.sync(test_job_step)
    assert update.status == "paused"
    docker_client_mock.containers.get.assert_called_with("job-test-job-id-test-step")
    container_mock.remove.assert_not_called()


def test_docker_job_sync_cancelling_sigterm(docker_job, docker_client_mock, test_job_step):
    """Test that the cancel method stops the container."""

    test_job_step.status = PlatformJobStatus.CANCELLING
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.status = "exited"
    container_mock.attrs = {"State": {"ExitCode": 0}}  # SIGTERM will set exit code 0 if exited gracefully
    task_id = uuid.uuid4().hex
    container_mock.labels = owned_container_labels(
        {
            JOB_WORKSPACE_ID_LABEL: test_job_step.workspace,
            JOB_ID_LABEL: test_job_step.job,
            JOB_STEP_NAME_LABEL: test_job_step.name,
            JOB_TASK_ID_LABEL: task_id,
        }
    )
    # Clear side_effect so return_value takes precedence
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Test sync with running container
    update = docker_job.sync(test_job_step)
    assert update.status == "cancelled"
    docker_client_mock.containers.get.assert_called_with("job-test-job-id-test-step")
    # Container removed as part of cleanup_steps
    container_mock.remove.assert_not_called()


def test_docker_job_sync_cancelling_sigkill(docker_job, docker_client_mock, test_job_step):
    """Test that the cancel method stops the container."""

    test_job_step.status = PlatformJobStatus.CANCELLING
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.status = "exited"
    container_mock.attrs = {"State": {"ExitCode": 137}}  # SIGKILL will set exit code 137
    task_id = uuid.uuid4().hex
    container_mock.labels = owned_container_labels(
        {
            JOB_WORKSPACE_ID_LABEL: test_job_step.workspace,
            JOB_ID_LABEL: test_job_step.job,
            JOB_STEP_NAME_LABEL: test_job_step.name,
            JOB_TASK_ID_LABEL: task_id,
        }
    )
    # Clear side_effect so return_value takes precedence
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Test sync with running container
    update = docker_job.sync(test_job_step)
    assert update.status == "cancelled"
    docker_client_mock.containers.get.assert_called_with("job-test-job-id-test-step")
    # Container removed as part of cleanup_steps
    container_mock.remove.assert_not_called()


def test_docker_job_schedule_no_resources(docker_job, docker_client_mock):
    """Test that scheduling works with providers that don't have resources attribute."""
    # Create a provider without resources attribute
    provider = CPUExecutionProvider(container=ContainerSpec(image="test-image:latest"))

    test_job_step = PlatformJobStepWithContext(
        id="test-step-id",
        job="job-test-job-id",
        attempt_id="test-job-attempt-id",
        workspace="default",
        fileset="test-logs-fileset",
        name="test-step",
        step_spec=PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(
                provider="cpu",
                profile="default",
                container=ContainerSpec(image="test-image"),
            ),
            config={"test_param": "value"},
            environment=[PlatformJobEnvironmentVariable(name="ENV_VAR", value="test_value")],
        ),
        status=PlatformJobStatus.PENDING,
    )

    # Should not raise an AttributeError
    docker_job.schedule(provider, test_job_step)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify that containers were created (init + job)
    assert docker_client_mock.containers.run.call_count == 0
    assert docker_client_mock.containers.create.call_count == 2  # Init container + job container

    # Get the job container call arguments (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    container_args = (
        create_call_args[1] if create_call_args[1] else create_call_args[0][0] if create_call_args[0] else {}
    )

    assert "network" in container_args

    # Should not have mem_limit or cpu_count since no resources were specified
    assert "mem_limit" not in container_args
    assert "cpu_count" not in container_args


def test_docker_job_schedule_with_secrets(docker_job, docker_client_mock):
    """Test that scheduling works when secrets are provided."""
    # Create a provider without resources attribute
    provider = CPUExecutionProvider(container=ContainerSpec(image="test-image:latest"))

    test_job_step = PlatformJobStepWithContext(
        id="test-step-id",
        job="job-test-job-id",
        attempt_id="test-job-attempt-id",
        fileset="test-logs-fileset",
        workspace="default",
        name="test-step",
        step_spec=PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(
                provider="cpu",
                profile="default",
                container=ContainerSpec(image="test-image"),
            ),
            config={"test_param": "value"},
            environment=[
                PlatformJobEnvironmentVariable(name="ENV_VAR", value="test_value"),
                PlatformJobEnvironmentVariable(
                    name="SECRET_ENV_VAR",
                    from_secret=PlatformJobSecretEnvironmentVariableRef(
                        name="test-secret",
                    ),
                ),
            ],
        ),
        status=PlatformJobStatus.PENDING,
    )

    # Should not raise an AttributeError
    docker_job.schedule(provider, test_job_step)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify that containers were created (init + job)
    assert docker_client_mock.containers.run.call_count == 0
    assert docker_client_mock.containers.create.call_count == 2  # Init container + job container

    # Get the job container call arguments (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    container_args = (
        create_call_args[1] if create_call_args[1] else create_call_args[0][0] if create_call_args[0] else {}
    )

    # Ensure environment variables include the secret content
    env_vars = container_args.get("environment", {})
    assert "NEMO_JOB_SECRETS" in env_vars
    assert "SECRET_ENV_VAR=default/test-secret" in env_vars["NEMO_JOB_SECRETS"]


def test_docker_job_nemo_job_secrets_format_same_and_cross_workspace(docker_job, docker_client_mock):
    """NEMO_JOB_SECRETS is correctly formatted for same-workspace and cross-workspace secret refs.

    Jobs can reference secrets from other workspaces when the user has permissions.
    Format must be ENV_VAR=workspace/secret_name per SECRETS.md; cross-workspace refs
    use the explicit workspace/secret_name from from_secret.name.
    """
    provider = CPUExecutionProvider(container=ContainerSpec(image="test-image:latest"))
    # Step in workspace "default"; one secret in same workspace, one in other workspace
    test_job_step = PlatformJobStepWithContext(
        id="test-step-id",
        job="job-test-job-id",
        attempt_id="test-job-attempt-id",
        fileset="test-logs-fileset",
        workspace="default",
        name="test-step",
        step_spec=PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(
                provider="cpu",
                profile="default",
                container=ContainerSpec(image="test-image"),
            ),
            config={},
            environment=[
                PlatformJobEnvironmentVariable(
                    name="LOCAL_SECRET",
                    from_secret=PlatformJobSecretEnvironmentVariableRef(name="local-secret"),
                ),
                PlatformJobEnvironmentVariable(
                    name="CROSS_WORKSPACE_SECRET",
                    from_secret=PlatformJobSecretEnvironmentVariableRef(name="other-ws/shared-secret"),
                ),
            ],
        ),
        status=PlatformJobStatus.PENDING,
    )

    docker_job.schedule(provider, test_job_step)
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()

    create_call_args = docker_client_mock.containers.create.call_args
    container_args = (
        create_call_args[1] if create_call_args[1] else create_call_args[0][0] if create_call_args[0] else {}
    )
    env_vars = container_args.get("environment", {})
    nemo_secrets = env_vars.get("NEMO_JOB_SECRETS", "")

    # Same-workspace ref (no "/" in name) uses step workspace: default/local-secret
    assert "LOCAL_SECRET=default/local-secret" in nemo_secrets
    # Cross-workspace ref ("other-ws/shared-secret") is passed through as other-ws/shared-secret
    assert "CROSS_WORKSPACE_SECRET=other-ws/shared-secret" in nemo_secrets
    # Comma-separated, order may vary
    parts = [p.strip() for p in nemo_secrets.split(",")]
    assert len(parts) == 2
    assert set(parts) == {
        "LOCAL_SECRET=default/local-secret",
        "CROSS_WORKSPACE_SECRET=other-ws/shared-secret",
    }


def test_docker_job_profile_environment_applied(mock_nmp_client, docker_client_mock, mock_platform_config):
    """Profile environment (e.g. HOME=/tmp) is applied to scheduled job containers."""
    provider = CPUExecutionProvider(container=ContainerSpec(image="test-image:latest"))
    config = DockerJobExecutionProfileConfig(
        storage=DockerJobStorageConfig(volume_name="test_jobs_storage"),
        env={"HOME": "/tmp"},
    )
    with patch("nmp.core.jobs.controllers.backends.docker.get_platform_config", return_value=mock_platform_config):
        backend = CPUDockerJobBackend(mock_nmp_client, config, profile_name="default")
        backend._client = docker_client_mock

    test_job_step = PlatformJobStepWithContext(
        id="test-step-id",
        job="job-test-job-id",
        attempt_id="test-job-attempt-id",
        workspace="default",
        fileset="test-logs-fileset",
        name="test-step",
        step_spec=PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(
                provider="cpu",
                profile="default",
                container=ContainerSpec(image="test-image"),
            ),
            config={},
            environment=[PlatformJobEnvironmentVariable(name="ENV_VAR", value="test_value")],
        ),
        status=PlatformJobStatus.PENDING,
    )

    backend.schedule(provider, test_job_step)
    backend._container_run_threadpool.shutdown(wait=True)
    backend._container_run_threadpool = MagicMock()

    create_call_args = docker_client_mock.containers.create.call_args
    container_args = (
        create_call_args[1] if create_call_args[1] else create_call_args[0][0] if create_call_args[0] else {}
    )
    env_vars = container_args.get("environment", {})
    assert env_vars.get("HOME") == "/tmp"
    assert env_vars.get("ENV_VAR") == "test_value"


def test_docker_job_execution_profile_config_rejects_reserved_env_vars():
    """DockerJobExecutionProfileConfig raises when environment contains reserved names."""
    with pytest.raises(ValidationError) as exc_info:
        DockerJobExecutionProfileConfig(
            storage=DockerJobStorageConfig(volume_name="test_jobs_storage"),
            env={"NEMO_JOB_ID": "x"},
        )
    assert "NEMO_JOB_ID" in str(exc_info.value)
    assert "reserved" in str(exc_info.value).lower()


def test_schedule_docker_gpu(mock_nmp_client, docker_client_mock):
    """Test successful job scheduling."""

    gpus = 2
    gpu_executor_config = GPUExecutionProvider.model_validate(
        {
            "provider": "gpu",
            "profile": "default",
            "container": {
                "image": "hello-world:latest",
                "entrypoint": ["c1"],
            },
            "resources": {
                "num_gpus": gpus,
            },
            "config": {},
        }
    )

    step = PlatformJobStepWithContext.model_validate(
        {
            "id": "test-step-id",
            "job": "job-test-job-id",
            "attempt_id": "test-job-attempt-id",
            "name": "test-step",
            "fileset": "test-logs-fileset",
            "workspace": "default",
            "step_spec": {
                "name": "test-step",
                "executor": gpu_executor_config.model_dump(),
                "config": {},
                "environment": [{"name": "ENV_VAR", "value": "test_value"}],
            },
            "status": "created",
        }
    )
    assert step is not None

    step_two = PlatformJobStepWithContext.model_validate(
        {
            "id": "test-step-two-id",
            "job": "job-test-job-id",
            "attempt_id": "test-job-attempt-id",
            "name": "test-step-two",
            "fileset": "test-logs-fileset",
            "workspace": "default",
            "step_spec": {
                "name": "test-step",
                "executor": gpu_executor_config.model_dump(),
                "config": {},
                "environment": [{"name": "ENV_VAR", "value": "test_value"}],
            },
            "status": "created",
        }
    )
    assert step_two is not None

    step_three = PlatformJobStepWithContext.model_validate(
        {
            "id": "test-step-three-id",
            "job": "job-test-job-id",
            "attempt_id": "test-job-attempt-id",
            "name": "test-step-three",
            "fileset": "test-logs-fileset",
            "workspace": "default",
            "step_spec": {
                "name": "test-step",
                "executor": gpu_executor_config.model_dump(),
                "config": {},
                "environment": [{"name": "ENV_VAR", "value": "test_value"}],
            },
            "status": "created",
        }
    )
    assert step_three is not None

    # Mock SharedResourceManager to provide GPU pool
    with patch("nmp.core.jobs.controllers.backends.docker.SharedResourceManager") as mock_srm:
        # Each step will request 2 GPUs. Make the third one fail.
        mock_pool = DockerGPUPool(reserved_gpu_device_ids=[0, 2, 3, 6, 7])
        mock_srm.get_instance.return_value.get_gpu_pool.return_value = mock_pool

        executor = GPUDockerJobBackend(
            nmp_sdk=mock_nmp_client,
            execution_profile_config=DockerJobExecutionProfileConfig(
                storage=DockerJobStorageConfig(volume_name="test_jobs_storage"),
            ),
            profile_name="default",
        )
        executor._client = docker_client_mock

    # whichever one is the third will fail
    with pytest.raises(ResourceAllocationError):
        executor.schedule(executor_config=gpu_executor_config, step=step)
        executor.schedule(executor_config=gpu_executor_config, step=step_two)
        executor.schedule(executor_config=gpu_executor_config, step=step_three)

    # Wait for background thread to complete
    executor._container_run_threadpool.shutdown(wait=True)
    executor._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Should call containers.create for init + job for each successful step, plus init for failed step
    # Step 1: init + job (2), Step 2: init + job (2), Step 3: init only (1) before GPU check fails
    assert docker_client_mock.containers.run.call_count == 0
    assert docker_client_mock.containers.create.call_count == 5

    # Find the job containers (they have the hello-world image and entrypoint)
    all_create_calls = docker_client_mock.containers.create.call_args_list
    job_containers = []
    for call in all_create_calls:
        kwargs = call[1] if call[1] else call[0][0]
        if kwargs.get("image") == "hello-world:latest":
            job_containers.append(kwargs)

    # Should have 2 job containers (one for each step)
    assert len(job_containers) == 2

    assert job_containers[0]["entrypoint"] == ["c1"]
    assert job_containers[0]["shm_size"] == "2g"
    device_requests_0 = job_containers[0]["device_requests"]
    assert len(device_requests_0) == 1
    assert len(device_requests_0[0]["DeviceIDs"]) == 2

    assert job_containers[1]["entrypoint"] == ["c1"]
    assert job_containers[1]["shm_size"] == "2g"
    device_requests_1 = job_containers[1]["device_requests"]
    assert len(device_requests_1) == 1
    assert len(device_requests_1[0]["DeviceIDs"]) == 2

    assert set(device_requests_0[0]["DeviceIDs"]).intersection(set(device_requests_1[0]["DeviceIDs"])) == set()

    assert set(executor.gpu_pool.gpu_to_workload_id.keys()) == {0, 2, 3, 6, 7}

    all_steps = {"test-step-id", "test-step-two-id", "test-step-three-id"}
    pool_values = set(executor.gpu_pool.gpu_to_workload_id.values())
    assert len(pool_values.intersection(all_steps)) == 2
    assert len([v for v in executor.gpu_pool.gpu_to_workload_id.values() if v is None]) == 1


def test_gpu_cleanup_on_job_completion(mock_nmp_client, docker_client_mock):
    """Test that GPU resources are released when a job completes successfully."""

    gpu_executor_config = GPUExecutionProvider.model_validate(
        {
            "provider": "gpu",
            "profile": "default",
            "container": {
                "image": "test-gpu-image:latest",
            },
            "resources": {
                "num_gpus": 1,
            },
            "config": {},
        }
    )

    step = PlatformJobStepWithContext.model_validate(
        {
            "id": "test-step-id",
            "job": "job-gpu-cleanup-test",
            "attempt_id": "test-job-attempt-id",
            "name": "gpu-test-step",
            "fileset": "test-logs-fileset",
            "workspace": "default",
            "step_spec": {
                "name": "gpu-test-step",
                "executor": gpu_executor_config.model_dump(),
                "config": {},
                "environment": [{"name": "ENV_VAR", "value": "test_value"}],
            },
            "status": "created",
        }
    )

    # Mock SharedResourceManager to provide GPU pool
    with patch("nmp.core.jobs.controllers.backends.docker.SharedResourceManager") as mock_srm:
        mock_pool = DockerGPUPool(reserved_gpu_device_ids=[0])
        mock_srm.get_instance.return_value.get_gpu_pool.return_value = mock_pool

        executor = GPUDockerJobBackend(
            nmp_sdk=mock_nmp_client,
            execution_profile_config=DockerJobExecutionProfileConfig(
                storage=DockerJobStorageConfig(volume_name="test_jobs_storage"),
            ),
            profile_name="default",
        )
        executor._client = docker_client_mock

    # Schedule the job - this should allocate GPU 0
    executor.schedule(executor_config=gpu_executor_config, step=step)

    # Wait for background thread to complete
    executor._container_run_threadpool.shutdown(wait=True)
    executor._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify GPU is allocated
    assert executor.gpu_pool.gpu_to_workload_id[0] == "test-step-id"

    # Setup container mock for sync - job completed successfully
    container_mock = MagicMock()
    container_mock.id = "test-container-id"
    container_mock.status = "exited"
    container_mock.attrs = {"State": {"ExitCode": 0}}
    task_id = uuid.uuid4().hex
    container_mock.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: step.job,
        JOB_STEP_NAME_LABEL: step.name,
        JOB_STEP_ID_LABEL: step.id,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Clear side_effect so return_value takes precedence
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock
    docker_client_mock.containers.list.side_effect = None
    docker_client_mock.containers.list.return_value = [container_mock]

    # Update step status to ACTIVE (as scheduler would do)
    step.status = PlatformJobStatus.ACTIVE

    # Sync the job
    update = executor.sync(step)

    # Verify job completed successfully
    assert update.status == "completed"

    # Mock the check_step_is_terminal method to return True for all containers
    # This allows the cleanup to proceed
    executor.check_step_is_terminal = MagicMock(side_effect=None, return_value=True)

    # Call cleanup_steps and verify GPU was released back to the pool.
    executor.cleanup_steps()
    assert set(executor.gpu_pool.gpu_to_workload_id.keys()) == {0}
    assert executor.gpu_pool.gpu_to_workload_id[0] is None


def test_gpu_cleanup_on_job_error(mock_nmp_client, docker_client_mock):
    """Test that GPU resources are released when a job fails with an error."""

    gpu_executor_config = GPUExecutionProvider.model_validate(
        {
            "provider": "gpu",
            "profile": "default",
            "container": {
                "image": "test-gpu-image:latest",
            },
            "resources": {
                "num_gpus": 1,
            },
            "config": {},
        }
    )

    step = PlatformJobStepWithContext.model_validate(
        {
            "id": "test-step-id",
            "job": "job-gpu-error-test",
            "attempt_id": "test-job-attempt-id",
            "name": "gpu-error-step",
            "fileset": "test-logs-fileset",
            "workspace": "default",
            "step_spec": {
                "name": "gpu-error-step",
                "executor": gpu_executor_config.model_dump(),
                "config": {},
                "environment": [{"name": "ENV_VAR", "value": "test_value"}],
            },
            "status": "created",
        }
    )

    # Mock SharedResourceManager to provide GPU pool
    with patch("nmp.core.jobs.controllers.backends.docker.SharedResourceManager") as mock_srm:
        mock_pool = DockerGPUPool(reserved_gpu_device_ids=[0])
        mock_srm.get_instance.return_value.get_gpu_pool.return_value = mock_pool

        executor = GPUDockerJobBackend(
            nmp_sdk=mock_nmp_client,
            execution_profile_config=DockerJobExecutionProfileConfig(
                storage=DockerJobStorageConfig(volume_name="test_jobs_storage"),
            ),
            profile_name="default",
        )
        executor._client = docker_client_mock

    # Schedule the job - this should allocate GPU 0
    executor.schedule(executor_config=gpu_executor_config, step=step)

    # Wait for background thread to complete
    executor._container_run_threadpool.shutdown(wait=True)
    executor._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify GPU is allocated
    assert set(executor.gpu_pool.gpu_to_workload_id.keys()) == {0}
    assert executor.gpu_pool.gpu_to_workload_id[0] == "test-step-id"

    # Setup container mock for sync - job failed with exit code 1
    container_mock = MagicMock()
    container_mock.id = "test-container-id"
    container_mock.status = "exited"
    container_mock.attrs = {"State": {"ExitCode": 1}}  # Non-zero exit code indicates error
    task_id = uuid.uuid4().hex
    container_mock.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: step.job,
        JOB_STEP_NAME_LABEL: step.name,
        JOB_STEP_ID_LABEL: step.id,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }
    # Error-path status derivation reads container.logs(...).decode() for error_stack.
    container_mock.logs.return_value = b"boom"

    # Clear side_effect so return_value takes precedence
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock
    docker_client_mock.containers.list.side_effect = None
    docker_client_mock.containers.list.return_value = [container_mock]

    # Update step status to ACTIVE (as scheduler would do)
    step.status = PlatformJobStatus.ACTIVE

    # Sync the job - this should detect error and release the GPU
    update = executor.sync(step)

    # Verify job failed with error
    assert update.status == "error"

    # Mock the check_step_is_terminal method to return True for all containers
    # This allows the cleanup to proceed
    executor.check_step_is_terminal = MagicMock(side_effect=None, return_value=True)

    # Call cleanup_steps and verify GPU was released back to the pool even though job failed
    executor.cleanup_steps()
    assert set(executor.gpu_pool.gpu_to_workload_id.keys()) == {0}
    assert executor.gpu_pool.gpu_to_workload_id[0] is None


def test_ensure_volume_creates_when_test_missing(docker_job: CPUDockerJobBackend, docker_client_mock, test_job_step):
    """Test that _ensure_job_storage creates a volume when one doesn't exist."""

    # Mock volume doesn't exist (raises NotFound)
    docker_client_mock.volumes.get.side_effect = NotFound("Volume not found")

    # Mock the created volume
    mock_volume = MagicMock()
    docker_client_mock.volumes.create.return_value = mock_volume

    task_id = "test-task-id"

    # Call the method - should not raise an exception
    # Ensure storage config is not None
    docker_job._execution_profile_config.storage = DockerJobStorageConfig(
        volume_name="test_jobs_storage", volume_permissions_image=DEFAULT_VOLUME_PERMISSIONS_IMAGE
    )
    docker_job.ensure_job_storage(
        docker_job._execution_profile_config.storage.volume_name,
        docker_job._execution_profile_config.storage.volume_permissions_image,
        test_job_step.workspace,
        test_job_step.job,
        task_id,
        "{}",  # step_config_json required
    )

    # Verify volume lookup was attempted and volumes were created
    docker_client_mock.volumes.get.assert_called_once_with("test_jobs_storage")
    assert docker_client_mock.volumes.create.call_count == 3
    docker_client_mock.volumes.create.assert_any_call("test_jobs_storage")
    docker_client_mock.volumes.create.assert_any_call(
        f"task-storage-{test_job_step.workspace}-{test_job_step.job}-{task_id}"
    )
    docker_client_mock.volumes.create.assert_any_call(
        f"task-config-{test_job_step.workspace}-{test_job_step.job}-{task_id}"
    )


def test_ensure_volume_creates_job_subdirectories(
    docker_job: CPUDockerJobBackend, docker_client_mock, test_job_step_with_persistence
):
    """Test that _ensure_job_storage creates job-specific subdirectories in existing volume."""

    volume_name = "test_jobs_storage"
    workspace = test_job_step_with_persistence.workspace
    job_id = test_job_step_with_persistence.job
    task_id = "test-task-id"
    task_volume_name = f"task-storage-{workspace}-{job_id}-{task_id}"

    # Ensure storage config is not None
    docker_job._execution_profile_config.storage = DockerJobStorageConfig(
        volume_name=volume_name, volume_permissions_image=DEFAULT_VOLUME_PERMISSIONS_IMAGE
    )
    docker_job.ensure_job_storage(
        docker_job._execution_profile_config.storage.volume_name,
        docker_job._execution_profile_config.storage.volume_permissions_image,
        test_job_step_with_persistence.workspace,
        test_job_step_with_persistence.job,
        task_id,
        "{}",  # step_config_json required
    )

    # Verify volume existence was checked
    docker_client_mock.volumes.get.assert_called_once_with(volume_name)

    # Verify task storage and config volumes were created
    assert docker_client_mock.volumes.create.call_count == 2
    docker_client_mock.volumes.create.assert_any_call(task_volume_name)
    docker_client_mock.volumes.create.assert_any_call(f"task-config-{workspace}-{job_id}-{task_id}")

    # Verify init container was created (not run)
    docker_client_mock.containers.create.assert_called_once()
    call_args = docker_client_mock.containers.create.call_args
    kwargs = call_args[1] if call_args[1] else call_args[0][0]

    # Verify init container specifics
    assert kwargs["image"] == DEFAULT_VOLUME_PERMISSIONS_IMAGE
    assert kwargs["name"] == f"job-init-{workspace}-{job_id}-{task_id}"
    assert kwargs["volumes"] == {
        volume_name: {"bind": "/job-vol", "mode": "rw"},
        task_volume_name: {"bind": "/task-vol", "mode": "rw"},
        f"task-config-{workspace}-{job_id}-{task_id}": {"bind": "/config-vol", "mode": "rw"},
    }


def test_ensure_volume_creates_job_without_persistence(
    docker_job: CPUDockerJobBackend, docker_client_mock, test_job_step
):
    """Test that _ensure_job_storage creates job-specific subdirectories in existing volume."""

    workspace = test_job_step.workspace
    job_id = test_job_step.job
    task_id = "test-task-id"
    task_volume_name = f"task-storage-{workspace}-{job_id}-{task_id}"

    # Ensure storage config is not None
    docker_job._execution_profile_config.storage = DockerJobStorageConfig(
        volume_permissions_image=DEFAULT_VOLUME_PERMISSIONS_IMAGE
    )
    docker_job.ensure_job_storage(
        "",  # Use empty string to simulate no persistent storage volume
        docker_job._execution_profile_config.storage.volume_permissions_image,
        test_job_step.workspace,
        test_job_step.job,
        task_id,
        "{}",  # step_config_json required
    )

    # Verify volume existence was not checked for the persistent storage volume
    docker_client_mock.volumes.get.assert_not_called()

    # Verify task storage and config volumes were created
    assert docker_client_mock.volumes.create.call_count == 2
    docker_client_mock.volumes.create.assert_any_call(task_volume_name)
    docker_client_mock.volumes.create.assert_any_call(f"task-config-{workspace}-{job_id}-{task_id}")

    # Verify init container was created (not run)
    docker_client_mock.containers.create.assert_called_once()
    call_args = docker_client_mock.containers.create.call_args
    kwargs = call_args[1] if call_args[1] else call_args[0][0]

    # Verify init container specifics
    assert kwargs["image"] == DEFAULT_VOLUME_PERMISSIONS_IMAGE
    assert kwargs["name"] == f"job-init-{workspace}-{job_id}-{task_id}"
    assert kwargs["volumes"] == {
        task_volume_name: {"bind": "/task-vol", "mode": "rw"},
        f"task-config-{workspace}-{job_id}-{task_id}": {"bind": "/config-vol", "mode": "rw"},
    }


def test_schedule_with_shared_storage_mounts(
    docker_job: CPUDockerJobBackend, docker_client_mock, test_job_step_with_persistence
):
    """Test that job scheduling uses volume mounts with subpaths for shared storage isolation."""
    step_spec = test_job_step_with_persistence.step_spec
    executor_config = step_spec.executor

    docker_job.schedule(executor_config, test_job_step_with_persistence)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify containers were created: init container + job container
    assert docker_client_mock.containers.run.call_count == 0
    assert docker_client_mock.containers.create.call_count == 2  # Init container + job container

    # Analyze the init container call (first create call)
    init_call_args = docker_client_mock.containers.create.call_args_list[0]
    init_kwargs = init_call_args[1] if init_call_args[1] else init_call_args[0][0]
    assert init_kwargs["image"] == DEFAULT_VOLUME_PERMISSIONS_IMAGE
    assert init_kwargs["name"].startswith(
        f"job-init-{test_job_step_with_persistence.workspace}-{test_job_step_with_persistence.job}-"
    )

    # Analyze the job container call (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    job_container_args = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    assert "mounts" in job_container_args
    mounts = job_container_args["mounts"]

    # Verify the three expected mounts: job storage, task storage, and config storage
    assert len(mounts) == 3

    mount_targets = {m["Target"] for m in mounts}
    assert "/var/test" in mount_targets  # job storage path
    assert "/var/tmp" in mount_targets  # task storage path

    # Verify job storage mount uses subpath for isolation
    storage_mount = next(m for m in mounts if m["Target"] == "/var/test")
    assert storage_mount["Type"] == "volume"
    assert storage_mount["Source"] == "test_jobs_storage"

    # Verify task storage mount uses named volume (not anonymous) and env var path
    task_storage_mount = next(m for m in mounts if m["Target"] == "/var/tmp")
    assert task_storage_mount["Type"] == "volume"
    assert task_storage_mount["Source"].startswith(
        f"task-storage-{test_job_step_with_persistence.workspace}-{test_job_step_with_persistence.job}-"
    )


def test_schedule_with_persistent_storage_adds_label(
    docker_job: CPUDockerJobBackend, docker_client_mock, test_job_step_with_persistence
):
    """Test that containers using persistent storage are labeled with JOB_USES_PERSISTENT_STORAGE_LABEL."""
    step_spec = test_job_step_with_persistence.step_spec
    executor_config = step_spec.executor

    docker_job.schedule(executor_config, test_job_step_with_persistence)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify containers were created: init container + job container
    assert docker_client_mock.containers.create.call_count == 2  # Init container + job container

    # Analyze the job container call (second create call)
    create_call_args = docker_client_mock.containers.create.call_args
    job_container_args = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    # Verify the persistent storage label is set
    assert "labels" in job_container_args
    labels = job_container_args["labels"]
    assert JOB_USES_PERSISTENT_STORAGE_LABEL in labels
    assert labels[JOB_USES_PERSISTENT_STORAGE_LABEL] == "true"


def test_schedule_without_persistent_storage_no_label(
    docker_job: CPUDockerJobBackend, docker_client_mock, test_job_step
):
    """Test that containers NOT using persistent storage have JOB_USES_PERSISTENT_STORAGE_LABEL set to 'false'."""
    step_spec = test_job_step.step_spec
    executor_config = step_spec.executor

    docker_job.schedule(executor_config, test_job_step)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify containers were created: init container + job container
    # Note: init container is always created for task storage and config setup
    assert docker_client_mock.containers.create.call_count == 2  # Init container + job container

    # Analyze the job container call (second create call)
    create_call_args = docker_client_mock.containers.create.call_args
    job_container_args = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    # Verify the persistent storage label is always set; "false" when not using persistent storage
    assert "labels" in job_container_args
    labels = job_container_args["labels"]
    assert JOB_USES_PERSISTENT_STORAGE_LABEL in labels
    assert labels[JOB_USES_PERSISTENT_STORAGE_LABEL] == "false"


def test_schedule_additional_volume_mounts(docker_job: CPUDockerJobBackend, docker_client_mock, test_job_step):
    """Test that job scheduling includes additional volume mounts specified in executor config."""
    step_spec = test_job_step.step_spec

    # Add additional volume mounts to executor config
    docker_job._execution_profile_config.storage = DockerJobStorageConfig(
        volume_name="test_jobs_storage",
        volume_permissions_image=DEFAULT_VOLUME_PERMISSIONS_IMAGE,
        additional_volume_mounts=[
            DockerVolumeMount(
                volume_name="custom-volume",
                mount_path="/container/path/custom",
            ),
        ],
    )

    docker_job.schedule(step_spec.executor, test_job_step)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Verify containers were created: init container + job container
    assert docker_client_mock.containers.run.call_count == 0
    assert docker_client_mock.containers.create.call_count == 2  # Init container + job container

    # Analyze the job container call (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    job_container_args = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    assert "mounts" in job_container_args
    mounts = job_container_args["mounts"]

    # Verify that additional mounts are included
    mount_targets = {m["Target"] for m in mounts}
    assert "/container/path/custom" in mount_targets


@pytest.mark.parametrize(
    "step_status,expected_result,should_update_status,expected_final_status,expected_message",
    [
        # Terminal states - should return True but not update status
        (PlatformJobStatus.CANCELLED, True, False, None, None),
        (PlatformJobStatus.PAUSED, True, False, None, None),
        # Transition states - should return True and update status
        (
            PlatformJobStatus.CANCELLING,
            True,
            True,
            PlatformJobStatus.CANCELLED,
            "Job is cancelled, not creating container",
        ),
        (PlatformJobStatus.PAUSING, True, True, PlatformJobStatus.PAUSED, "Job is paused, not creating container"),
        # Non-cancelling/pausing states - should return False and not update status
        (PlatformJobStatus.ACTIVE, False, False, None, None),
        (PlatformJobStatus.PENDING, False, False, None, None),
        (PlatformJobStatus.COMPLETED, False, False, None, None),
        (PlatformJobStatus.ERROR, False, False, None, None),
    ],
)
def test_cancel_scheduling(
    docker_job,
    mock_jobs_client,
    test_job_step,
    step_status,
    expected_result,
    should_update_status,
    expected_final_status,
    expected_message,
):
    """Test cancel_scheduling behavior for different step statuses."""
    # Mock the retrieved step with the specified status. get_step fetches it via
    # the typed client's get_job_step(...).data().
    mock_refreshed_step = MagicMock()
    mock_refreshed_step.status = step_status.value
    mock_jobs_client.get_job_step.return_value = data_response(mock_refreshed_step)

    result = docker_job.cancel_scheduling(test_job_step)

    # Verify result matches expectation
    assert result is expected_result

    # Verify the step was fetched via the typed client (get_step -> get_job_step)
    mock_jobs_client.get_job_step.assert_called_once_with(
        name=test_job_step.name, workspace=test_job_step.workspace, job=test_job_step.job
    )

    if should_update_status:
        # Verify update_job_step_status was called with the expected status/details in the body.
        mock_jobs_client.update_job_step_status.assert_called_once()
        call = mock_jobs_client.update_job_step_status.call_args
        assert call.kwargs["name"] == test_job_step.name
        assert call.kwargs["workspace"] == test_job_step.workspace
        assert call.kwargs["job"] == test_job_step.job
        assert call.kwargs["body"].status == expected_final_status
        assert call.kwargs["body"].status_details == {"message": expected_message}
    else:
        # Verify update_job_step_status was NOT called
        mock_jobs_client.update_job_step_status.assert_not_called()


@pytest.mark.parametrize("cleanup_completed_jobs_immediately", [True, False])
def test_cleanup_steps_by_ttl(docker_job, docker_client_mock, test_job_step, cleanup_completed_jobs_immediately):
    """Test cleanup_steps removes containers based on exit code and configuration."""
    # Set the cleanup configuration
    docker_job._execution_profile_config.cleanup_completed_jobs_immediately = cleanup_completed_jobs_immediately

    # Use a recent timestamp (5 minutes ago) so TTL-based cleanup doesn't trigger
    recent_time = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)).isoformat()

    # Make an older timestamp (120 minutes ago) so TTL-based cleanup does trigger
    older_time = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=120)).isoformat()

    # Mock the check_step_is_terminal and check_job_is_terminal methods to return True for all containers
    # This allows the cleanup to proceed
    docker_job.check_step_is_terminal = MagicMock(return_value=True)
    docker_job.check_job_is_terminal = MagicMock(return_value=True)

    # Create mock container that exited normally (exit code 0)
    mock_container_success = MagicMock()
    mock_container_success.name = "test-container-success"
    mock_container_success.id = "success-container-id"
    mock_container_success.status = "exited"
    mock_container_success.attrs = {
        "State": {"ExitCode": 0, "FinishedAt": recent_time},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    mock_container_success.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "test-job-id",
        JOB_STEP_NAME_LABEL: "test-step",
        JOB_TASK_ID_LABEL: "task-success",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Create mock container that was killed (exit code 137 - SIGKILL)
    mock_container_killed = MagicMock()
    mock_container_killed.name = "test-container-killed"
    mock_container_killed.id = "killed-container-id"
    mock_container_killed.status = "exited"
    mock_container_killed.attrs = {
        "State": {"ExitCode": 137, "FinishedAt": recent_time},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    mock_container_killed.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "test-job-id",
        JOB_STEP_NAME_LABEL: "test-step",
        JOB_TASK_ID_LABEL: "task-killed",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Create mock container that exited with error (exit code 1)
    mock_container_error = MagicMock()
    mock_container_error.name = "test-container-error"
    mock_container_error.id = "error-container-id"
    mock_container_error.status = "exited"
    mock_container_error.attrs = {
        "State": {"ExitCode": 1, "FinishedAt": recent_time},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    mock_container_error.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "test-job-id",
        JOB_STEP_NAME_LABEL: "test-step",
        JOB_TASK_ID_LABEL: "task-error",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Create mock container that exited with error (exit code 1)
    mock_container_old_error = MagicMock()
    mock_container_old_error.name = "test-container-old-error"
    mock_container_old_error.id = "old-error-container-id"
    mock_container_old_error.status = "exited"
    mock_container_old_error.attrs = {
        "State": {"ExitCode": 1, "FinishedAt": older_time},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    mock_container_old_error.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "test-job-id",
        JOB_STEP_NAME_LABEL: "test-step",
        JOB_TASK_ID_LABEL: "task-old-error",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Create mock container that is still running
    mock_container_running = MagicMock()
    mock_container_running.name = "test-container-running"
    mock_container_running.id = "running-container-id"
    mock_container_running.status = "running"
    mock_container_running.attrs = {"State": {"ExitCode": 0}}
    mock_container_running.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "test-job-id",
        JOB_STEP_NAME_LABEL: "test-step",
        JOB_TASK_ID_LABEL: "task-running",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Mock containers.list to return our test containers
    docker_client_mock.containers.list.return_value = [
        mock_container_success,
        mock_container_killed,
        mock_container_error,
        mock_container_running,
        mock_container_old_error,
    ]

    # Mock the network operations
    mock_network = MagicMock()
    docker_client_mock.networks.get.return_value = mock_network

    # Mock volume operations
    mock_volume = MagicMock()
    docker_client_mock.volumes.get.return_value = mock_volume

    # Run cleanup
    docker_job.cleanup_steps()

    # Verify containers.list was called with owner-scoped filters.
    docker_client_mock.containers.list.assert_called_once_with(
        all=True,
        filters={
            "label": [
                f"{JOB_MANAGED_BY_LABEL}={JOB_MANAGED_BY_JOBS_CONTROLLER}",
                f"{JOB_CONTROLLER_INSTANCE_ID_LABEL}={TEST_JOBS_CONTROLLER_INSTANCE_ID}",
                f"{JOB_EXECUTION_BACKEND_LABEL}=docker",
                f"{JOB_EXECUTION_PROFILE_LABEL}=default",
            ]
        },
        ignore_removed=True,
    )

    if cleanup_completed_jobs_immediately:
        # Should remove containers with exit codes 0 and 137, but not the error container (exit code 1)
        assert mock_container_success.remove.call_count == 1
        mock_container_success.remove.assert_called_with(force=True)

        assert mock_container_killed.remove.call_count == 1
        mock_container_killed.remove.assert_called_with(force=True)

        assert mock_container_old_error.remove.call_count == 1
        mock_container_old_error.remove.assert_called_with(force=True)

        # Container with error exit code should NOT be removed immediately
        mock_container_error.remove.assert_not_called()

        # Running container should NOT be processed at all (not removed)
        mock_container_running.remove.assert_not_called()

        # Verify task storage and config volumes were cleaned up for successful containers (2 volumes per task)
        assert docker_client_mock.volumes.get.call_count == 6
        docker_client_mock.volumes.get.assert_any_call("task-storage-default-test-job-id-task-success")
        docker_client_mock.volumes.get.assert_any_call("task-config-default-test-job-id-task-success")
        docker_client_mock.volumes.get.assert_any_call("task-storage-default-test-job-id-task-killed")
        docker_client_mock.volumes.get.assert_any_call("task-config-default-test-job-id-task-killed")
        docker_client_mock.volumes.get.assert_any_call("task-storage-default-test-job-id-task-old-error")
        docker_client_mock.volumes.get.assert_any_call("task-config-default-test-job-id-task-old-error")
    else:
        # When cleanup_completed_jobs_immediately is False, no containers should be removed
        mock_container_success.remove.assert_not_called()
        mock_container_killed.remove.assert_not_called()
        mock_container_error.remove.assert_not_called()
        mock_container_running.remove.assert_not_called()

        assert mock_container_old_error.remove.call_count == 1
        mock_container_old_error.remove.assert_called_with(force=True)

        assert docker_client_mock.volumes.get.call_count == 2
        docker_client_mock.volumes.get.assert_any_call("task-storage-default-test-job-id-task-old-error")
        docker_client_mock.volumes.get.assert_any_call("task-config-default-test-job-id-task-old-error")

    # Network cleanup should happen for all exited containers regardless of exit code
    assert mock_network.disconnect.call_count == 4  # success, killed, and error containers
    mock_network.disconnect.assert_any_call(mock_container_success)
    mock_network.disconnect.assert_any_call(mock_container_killed)
    mock_network.disconnect.assert_any_call(mock_container_error)
    mock_network.disconnect.assert_any_call(mock_container_old_error)


def test_cleanup_steps_skips_different_owner_container_before_jobs_api_check(docker_job, docker_client_mock):
    other_owner = MagicMock()
    other_owner.name = "other-owner-container"
    other_owner.id = "other-owner-container-id"
    other_owner.status = "exited"
    other_owner.attrs = {
        "State": {"ExitCode": 0, "FinishedAt": datetime.datetime.now(datetime.UTC).isoformat()},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    other_owner.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "other-job",
        JOB_STEP_NAME_LABEL: "other-step",
        JOB_TASK_ID_LABEL: "other-task",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: "other-owner",
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }
    docker_client_mock.containers.list.return_value = [other_owner]
    docker_job.check_step_is_terminal = MagicMock(return_value=True)

    docker_job.cleanup_steps()

    docker_job.check_step_is_terminal.assert_not_called()
    other_owner.remove.assert_not_called()


def test_cleanup_steps_skips_legacy_container_without_owner_label(docker_job, docker_client_mock):
    legacy = MagicMock()
    legacy.name = "legacy-container"
    legacy.id = "legacy-container-id"
    legacy.status = "exited"
    legacy.attrs = {
        "State": {"ExitCode": 0, "FinishedAt": datetime.datetime.now(datetime.UTC).isoformat()},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    legacy.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "legacy-job",
        JOB_STEP_NAME_LABEL: "legacy-step",
        JOB_TASK_ID_LABEL: "legacy-task",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }
    docker_client_mock.containers.list.return_value = [legacy]
    docker_job.check_step_is_terminal = MagicMock(return_value=True)

    docker_job.cleanup_steps()

    docker_job.check_step_is_terminal.assert_not_called()
    legacy.remove.assert_not_called()


def test_cleanup_job_persistent_storage_labels_cleanup_container_owner(docker_job, docker_client_mock):
    docker_job.cleanup_job_persistent_storage("default", "job-owner-test")

    cleanup_args = docker_client_mock.containers.create.call_args[1]
    assert cleanup_args["labels"][JOB_CONTROLLER_INSTANCE_ID_LABEL] == TEST_JOBS_CONTROLLER_INSTANCE_ID
    assert cleanup_args["labels"][JOB_TYPE_LABEL] == JOB_TYPE_STORAGE_CLEANUP


def test_created_step_does_not_ttl_before_backend_acceptance(docker_job, docker_client_mock, test_job_step):
    """CREATED age should not fail a step before the backend accepts it."""
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_before_active
    old_timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 300)
    test_job_step.created_at = old_timestamp
    test_job_step.updated_at = old_timestamp
    test_job_step.status = PlatformJobStatus.CREATED
    executor_config = test_job_step.step_spec.executor
    docker_job._container_run_threadpool = MagicMock()

    try:
        result = docker_job.schedule_single_container(executor_config, test_job_step)
    finally:
        if docker_job._container_run_threadpool.submit.called:
            docker_job._container_start_admission.release()

    assert result.status == PlatformJobStatus.PENDING
    docker_job._container_run_threadpool.submit.assert_called_once()


def test_docker_schedule_defers_when_start_admission_full(docker_job, docker_client_mock, test_job_step):
    """A full Docker start gate leaves the step CREATED and avoids per-attempt Docker setup."""
    acquired = 0
    try:
        for _ in range(DOCKER_CONTAINER_START_WORKERS):
            assert docker_job._container_start_admission.acquire(blocking=False)
            acquired += 1

        with pytest.raises(SchedulingDeferred, match="Docker start worker capacity is full"):
            docker_job.schedule_single_container(test_job_step.step_spec.executor, test_job_step)

        docker_client_mock.containers.create.assert_not_called()
        docker_client_mock.containers.run.assert_not_called()
    finally:
        for _ in range(acquired):
            docker_job._container_start_admission.release()


def test_failed_schedule_logs_status_update_failure_and_releases_admission(docker_job, test_job_step):
    assert docker_job._container_start_admission.acquire(blocking=False)
    docker_job._run_container_in_thread = MagicMock(
        side_effect=FailedToScheduleError("container failed", error_details={"message": "container failed"})
    )
    docker_job._jobs.update_job_step_status.side_effect = RuntimeError("jobs service unavailable")

    with patch("nmp.core.jobs.controllers.backends.docker.logger.exception") as log_exception:
        docker_job.run_container(test_job_step, {})

    log_exception.assert_any_call("Failed to schedule container for job step")
    log_exception.assert_any_call("Failed to persist scheduling error for job step")
    docker_job._jobs.update_job_step_status.assert_called_once()
    assert docker_job._container_start_admission.acquire(blocking=False)
    docker_job._container_start_admission.release()


def test_resuming_step_skips_before_active_ttl_enforcement(docker_job, test_job_step):
    """RESUMING must not apply ttl_seconds_before_active (pause/resume rebasing)."""
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_before_active
    old_created = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 300)
    test_job_step.created_at = old_created
    test_job_step.updated_at = datetime.datetime.now(datetime.timezone.utc)
    test_job_step.status = PlatformJobStatus.RESUMING
    assert docker_job.should_enforce_before_active_ttl(test_job_step) is False


def test_before_active_ttl_uses_latest_of_created_and_updated(docker_job, test_job_step):
    """After resume, updated_at rebases the pending TTL so old created_at alone does not expire."""
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_before_active
    old_created = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 300)
    test_job_step.created_at = old_created
    test_job_step.updated_at = datetime.datetime.now(datetime.timezone.utc)
    test_job_step.status = PlatformJobStatus.PENDING
    assert docker_job.check_step_ttl_before_active(test_job_step, ttl_seconds) is False


def test_cleanup_pending_created_container_by_ttl(docker_job, docker_client_mock, mock_jobs_client, test_job_step):
    """A stale PENDING step with a Docker-created container transitions to ERROR."""
    # Get the TTL configuration (default is 30 minutes)
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_before_active

    # Set the step to PENDING status
    test_job_step.status = PlatformJobStatus.PENDING

    # Create a step with an created_at timestamp that exceeds the TTL (35 minutes ago)
    old_timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 300)
    test_job_step.created_at = old_timestamp
    test_job_step.updated_at = old_timestamp

    # Create a mock container that the sync method will find (with owner labels so we kill it)
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.status = "created"
    task_id = uuid.uuid4().hex
    container_mock.labels = {
        JOB_ID_LABEL: test_job_step.job,
        JOB_STEP_NAME_LABEL: test_job_step.name,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }

    # Mock containers.get to return our container
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Call sync which should detect the TTL timeout
    result = docker_job.sync(test_job_step)

    # Verify that it returns an ERROR status with timeout message
    assert result.status == PlatformJobStatus.ERROR.value
    assert result.status_details == {"message": "Job timed out after reaching max TTL of 1800 seconds"}
    assert result.error_details == {"message": "Job timed out after reaching max TTL of 1800 seconds"}

    # Verify that the container was killed
    container_mock.kill.assert_called_once()

    # Verify that the task was updated via the API
    mock_jobs_client.update_job_step_task.assert_called_once()
    task_call = mock_jobs_client.update_job_step_task.call_args
    assert task_call.kwargs["name"] == task_id
    assert task_call.kwargs["workspace"] == test_job_step.workspace
    assert task_call.kwargs["job"] == test_job_step.job
    assert task_call.kwargs["step"] == test_job_step.name
    assert task_call.kwargs["body"].status == PlatformJobStatus.ERROR
    assert task_call.kwargs["body"].status_details == {
        "message": "Job timed out after reaching max TTL of 1800 seconds"
    }
    assert task_call.kwargs["body"].error_details == {"message": "Job timed out after reaching max TTL of 1800 seconds"}


def test_pending_running_container_preempts_before_active_ttl(docker_job, docker_client_mock, test_job_step):
    """If Docker is running, reconcile PENDING to ACTIVE instead of timing out first."""
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_before_active
    old_timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 300)
    test_job_step.status = PlatformJobStatus.PENDING
    test_job_step.created_at = old_timestamp
    test_job_step.updated_at = old_timestamp

    task_id = uuid.uuid4().hex
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.name = "job-test-job-id-test-step"
    container_mock.status = "running"
    container_mock.labels = {
        JOB_ID_LABEL: test_job_step.job,
        JOB_STEP_NAME_LABEL: test_job_step.name,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }
    container_mock.attrs = {"State": {"Status": "running", "Running": True}, "HostConfig": {}}
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    result = docker_job.sync(test_job_step)

    assert result.status == PlatformJobStatus.ACTIVE.value
    assert result.status_details == {"message": "Job is running"}
    container_mock.kill.assert_not_called()


def test_pending_exited_container_preempts_before_active_ttl(docker_job, docker_client_mock, test_job_step):
    """If Docker already exited successfully, reconcile PENDING to COMPLETED instead of timing out first."""
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_before_active
    old_timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 300)
    test_job_step.status = PlatformJobStatus.PENDING
    test_job_step.created_at = old_timestamp
    test_job_step.updated_at = old_timestamp

    task_id = uuid.uuid4().hex
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.name = "job-test-job-id-test-step"
    container_mock.status = "exited"
    container_mock.labels = {
        JOB_ID_LABEL: test_job_step.job,
        JOB_STEP_NAME_LABEL: test_job_step.name,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }
    container_mock.attrs = {"State": {"Status": "exited", "ExitCode": 0}, "HostConfig": {}}
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    result = docker_job.sync(test_job_step)

    assert result.status == PlatformJobStatus.COMPLETED.value
    assert result.status_details == {"message": "Job completed successfully with exit code 0"}
    container_mock.kill.assert_not_called()


def test_cleanup_active_by_ttl(docker_job, docker_client_mock, mock_jobs_client, test_job_step):
    """Test that sync of an ACTIVE step transitions to an ERROR state when step's created_at exceeds TTL."""
    # Get the TTL configuration for active jobs (default is 24 hours)
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_active

    # Set the step to ACTIVE status
    test_job_step.status = PlatformJobStatus.ACTIVE

    # Create a step with an created_at timestamp that exceeds the TTL (25 hours ago)
    old_timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 3600)
    test_job_step.created_at = old_timestamp

    # Create a mock container that the sync method will find (with owner labels so we kill it)
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.status = "running"
    task_id = uuid.uuid4().hex
    container_mock.labels = {
        JOB_ID_LABEL: test_job_step.job,
        JOB_STEP_NAME_LABEL: test_job_step.name,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }

    # Mock containers.get to return our container
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Call sync which should detect the TTL timeout
    result = docker_job.sync(test_job_step)

    # Verify that it returns an ERROR status with timeout message
    assert result.status == PlatformJobStatus.ERROR.value
    assert result.status_details == {"message": "Job timed out after reaching max TTL of 86400 seconds"}
    assert result.error_details == {"message": "Job timed out after reaching max TTL of 86400 seconds"}

    # Verify that the container was killed
    container_mock.kill.assert_called_once()

    # Verify that the task was updated via the API
    mock_jobs_client.update_job_step_task.assert_called_once()
    task_call = mock_jobs_client.update_job_step_task.call_args
    assert task_call.kwargs["name"] == task_id
    assert task_call.kwargs["workspace"] == test_job_step.workspace
    assert task_call.kwargs["job"] == test_job_step.job
    assert task_call.kwargs["step"] == test_job_step.name
    assert task_call.kwargs["body"].status == PlatformJobStatus.ERROR
    assert task_call.kwargs["body"].status_details == {
        "message": "Job timed out after reaching max TTL of 86400 seconds"
    }
    assert task_call.kwargs["body"].error_details == {
        "message": "Job timed out after reaching max TTL of 86400 seconds"
    }


def test_ttl_enforcement_handles_409_when_kill_races_with_stopped_container(
    docker_job, docker_client_mock, mock_jobs_client, test_job_step
):
    """Test TTL enforcement handles gracefully when container.kill() races with a stopped container."""
    # Get the TTL configuration for pending/created jobs
    ttl_seconds = docker_job._execution_profile_config.ttl_seconds_before_active

    # Set the step to PENDING status
    test_job_step.status = PlatformJobStatus.PENDING

    # Create a step with an created_at timestamp that exceeds the TTL
    old_timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=ttl_seconds + 300)
    test_job_step.created_at = old_timestamp
    test_job_step.updated_at = old_timestamp

    # Create a mock container
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.name = "job-test-job-id-test-step"
    container_mock.status = "created"
    task_id = uuid.uuid4().hex
    container_mock.labels = {
        JOB_WORKSPACE_ID_LABEL: test_job_step.workspace,
        JOB_ID_LABEL: test_job_step.job,
        JOB_STEP_NAME_LABEL: test_job_step.name,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }

    # Mock container.kill() to raise APIError with 409 status (container already stopped)
    api_error = APIError("Container already stopped", response=MagicMock(status_code=409))
    container_mock.kill.side_effect = api_error

    # Mock containers.get to return our container
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Call sync which should detect the TTL timeout and attempt to kill the container
    result = docker_job.sync(test_job_step)

    # Verify that it returns an ERROR status with timeout message
    assert result.status == PlatformJobStatus.ERROR.value
    assert result.status_details == {"message": "Job timed out after reaching max TTL of 1800 seconds"}
    assert result.error_details == {"message": "Job timed out after reaching max TTL of 1800 seconds"}

    # Verify that container.kill() was called (even though it raised 409)
    container_mock.kill.assert_called_once()

    # Verify that the task was updated via the API despite the 409 error
    mock_jobs_client.update_job_step_task.assert_called_once()
    task_call = mock_jobs_client.update_job_step_task.call_args
    assert task_call.kwargs["name"] == task_id
    assert task_call.kwargs["workspace"] == test_job_step.workspace
    assert task_call.kwargs["job"] == test_job_step.job
    assert task_call.kwargs["step"] == test_job_step.name
    assert task_call.kwargs["body"].status == PlatformJobStatus.ERROR
    assert task_call.kwargs["body"].status_details == {
        "message": "Job timed out after reaching max TTL of 1800 seconds"
    }
    assert task_call.kwargs["body"].error_details == {"message": "Job timed out after reaching max TTL of 1800 seconds"}


def test_sync_stop_container_already_stopped(docker_job, docker_client_mock, mock_jobs_client, test_job_step):
    """Test that sync handles gracefully when container.stop() is called on already stopped container."""
    # Set the step to CANCELLING status (which triggers sync_stop_container)
    test_job_step.status = PlatformJobStatus.CANCELLING

    # Create a mock container that's already stopped (with owner labels so we attempt stop)
    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.name = "job-test-job-id-test-step"
    container_mock.status = "exited"
    container_mock.attrs = {"State": {"ExitCode": 0}}
    task_id = uuid.uuid4().hex
    container_mock.labels = {
        JOB_ID_LABEL: test_job_step.job,
        JOB_STEP_NAME_LABEL: test_job_step.name,
        JOB_TASK_ID_LABEL: task_id,
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }

    # Mock container.stop() to raise APIError with 409 status (container already stopped)
    api_error = APIError("Container already stopped", response=MagicMock(status_code=409))
    container_mock.stop.side_effect = api_error

    # Mock containers.get to return our container
    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    # Call sync which should attempt to stop the container
    result = docker_job.sync(test_job_step)

    # Verify that container.stop() was called (even though it raised 409)
    container_mock.stop.assert_called_once()

    # Verify that the sync still completes successfully and returns the appropriate status
    # Since the container is exited with code 0 and step is CANCELLING, it should be CANCELLED
    assert result.status == PlatformJobStatus.CANCELLED.value
    assert "Job was cancelled successfully" in result.status_details["message"]
    assert result.error_details == {}

    # Verify that the task was updated via the API
    mock_jobs_client.update_job_step_task.assert_called_once()
    task_call = mock_jobs_client.update_job_step_task.call_args
    assert task_call.kwargs["name"] == task_id
    assert task_call.kwargs["workspace"] == test_job_step.workspace
    assert task_call.kwargs["job"] == test_job_step.job
    assert task_call.kwargs["step"] == test_job_step.name
    assert task_call.kwargs["body"].status == PlatformJobStatus.CANCELLED
    assert task_call.kwargs["body"].status_details == {"message": "Job was cancelled successfully with exit code 0"}
    assert task_call.kwargs["body"].error_details == {}
    assert task_call.kwargs["body"].error_stack == ""


def test_sync_stop_container_skips_when_not_owned_by_jobs_controller(docker_job, docker_client_mock, test_job_step):
    """sync_stop_container must not call container.stop() if the container is not owned by this controller."""
    test_job_step.status = PlatformJobStatus.CANCELLING

    container_mock = MagicMock()
    container_mock.id = "16-character-uid"
    container_mock.name = "job-test-job-id-test-step"
    container_mock.status = "running"
    container_mock.labels = {}  # No JOB_MANAGED_BY_LABEL

    docker_client_mock.containers.get.side_effect = None
    docker_client_mock.containers.get.return_value = container_mock

    result = docker_job.sync(test_job_step)

    container_mock.stop.assert_not_called()
    assert result.status == PlatformJobStatus.ERROR.value
    assert "not owned" in result.error_details.get("message", "")


# ============================================================================
# Auth Context Propagation Tests
# ============================================================================


@pytest.fixture
def test_job_step_with_auth_context():
    """Create a test job step with auth context for testing."""
    return PlatformJobStepWithContext(
        id="test-step-id",
        job="job-test-job-id",
        attempt_id="test-job-attempt-id",
        fileset="test-logs-fileset",
        workspace="default",
        name="test-step",
        step_spec=PlatformJobStepSpec(
            name="test-step",
            executor=CPUExecutionProvider(
                provider="cpu",
                profile="default",
                container=ContainerSpec(image="test-image"),
            ),
            config={"test_param": "value"},
        ),
        status=PlatformJobStatus.PENDING,
        auth_context=AuthContext(
            principal_id="creator@example.com",
            principal_email="creator@example.com",
            principal_groups=["engineering", "ml-team"],
        ),
    )


def test_docker_job_schedule_with_auth_context(docker_job, docker_client_mock, test_job_step_with_auth_context):
    """Test that scheduling sets NMP_PRINCIPAL and OTEL headers env vars when auth_context is present.

    Verifies GitLab issue #3390 Gap 2: job tasks should run with the creating
    user's auth context, propagated via the NMP_PRINCIPAL environment variable
    and OTEL_EXPORTER_OTLP_LOGS_HEADERS for authenticated telemetry export.
    """
    step_spec = test_job_step_with_auth_context.step_spec
    executor_config = step_spec.executor

    docker_job.schedule(executor_config, test_job_step_with_auth_context)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Get the job container call arguments (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    kwargs = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    # Verify NMP_PRINCIPAL env var is set
    env = kwargs["environment"]
    assert NMP_PRINCIPAL_ENVVAR in env

    # Verify JSON structure uses Principal field names (id, email, groups)
    principal_json = env[NMP_PRINCIPAL_ENVVAR]
    principal_data = json.loads(principal_json)

    assert principal_data == {
        "id": "creator@example.com",
        "email": "creator@example.com",
        "groups": ["engineering", "ml-team"],
    }

    # Verify OTEL headers env var is set for authenticated telemetry
    assert "OTEL_EXPORTER_OTLP_LOGS_HEADERS" in env
    otlp_headers = env["OTEL_EXPORTER_OTLP_LOGS_HEADERS"]
    # URL-encoded: @ -> %40, , -> %2C
    assert "X-NMP-Principal-Id=creator%40example.com" in otlp_headers
    assert "X-NMP-Principal-Email=creator%40example.com" in otlp_headers
    assert "X-NMP-Principal-Groups=engineering%2Cml-team" in otlp_headers


def test_docker_job_schedule_without_auth_context(docker_job, docker_client_mock, test_job_step):
    """Test that auth env vars are NOT set when auth_context is absent."""
    step_spec = test_job_step.step_spec
    executor_config = step_spec.executor

    docker_job.schedule(executor_config, test_job_step)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Get the job container call arguments (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    kwargs = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    # Verify auth env vars are NOT set
    env = kwargs["environment"]
    assert NMP_PRINCIPAL_ENVVAR not in env
    assert "OTEL_EXPORTER_OTLP_LOGS_HEADERS" not in env


def test_docker_job_schedule_with_auth_context_empty_groups():
    """Test that empty groups list is serialized correctly in auth context."""
    auth_context = AuthContext(
        principal_id="user@example.com",
        principal_email="user@example.com",
        principal_groups=[],
    )

    # Verify groups is serialized as empty list, not omitted
    principal = Principal(
        id=auth_context.principal_id,
        email=auth_context.principal_email,
        groups=auth_context.principal_groups or [],
    )
    principal_json = principal.model_dump_json()
    principal_data = json.loads(principal_json)

    assert "groups" in principal_data
    assert principal_data["groups"] == []


def test_docker_job_schedule_with_auth_context_no_email():
    """Test that auth context without email is serialized correctly."""
    auth_context = AuthContext(
        principal_id="service-account",
        principal_email=None,
        principal_groups=["service-accounts"],
    )

    principal = Principal(
        id=auth_context.principal_id,
        email=auth_context.principal_email,
        groups=auth_context.principal_groups or [],
    )
    principal_json = principal.model_dump_json()
    principal_data = json.loads(principal_json)

    assert principal_data["id"] == "service-account"
    assert principal_data.get("email") is None
    assert principal_data["groups"] == ["service-accounts"]


def test_docker_job_schedule_with_auth_context_sdk_model_none_groups(
    docker_job, docker_client_mock, test_job_step_with_auth_context
):
    """Test that SDK auth context with principal_groups=None is handled correctly."""

    test_job_step_with_auth_context.auth_context = SdkAuthContext(
        principal_id="user@example.com",
        principal_email="user@example.com",
        principal_groups=None,
    )

    # This should not raise a validation error - exercises the actual code path
    docker_job.schedule(test_job_step_with_auth_context.step_spec.executor, test_job_step_with_auth_context)

    # Wait for background thread to complete
    docker_job._container_run_threadpool.shutdown(wait=True)
    docker_job._container_run_threadpool = MagicMock()  # Reset for cleanup

    # Get the job container call arguments (create call)
    create_call_args = docker_client_mock.containers.create.call_args
    kwargs = create_call_args[1] if create_call_args[1] else create_call_args[0][0]

    # Verify NMP_PRINCIPAL env var is set correctly
    env = kwargs["environment"]
    assert NMP_PRINCIPAL_ENVVAR in env

    # Verify JSON structure - groups should be empty list (default) not None
    principal_json = env[NMP_PRINCIPAL_ENVVAR]
    principal_data = json.loads(principal_json)

    assert principal_data["id"] == "user@example.com"
    assert principal_data["email"] == "user@example.com"
    assert principal_data["groups"] == []  # Default factory kicks in, not None


def test_cleanup_single_container_checks_job_terminal_before_persistent_storage_cleanup(docker_job, docker_client_mock):
    """Test that cleanup_single_container only cleans up persistent storage when the job is terminal."""
    # Create a mock container with persistent storage label that exited successfully
    mock_container = MagicMock()
    mock_container.name = "test-container-success"
    mock_container.id = "success-container-id"
    mock_container.attrs = {
        "State": {"ExitCode": 0},
    }
    mock_container.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "test-job-id",
        JOB_TASK_ID_LABEL: "task-success",
        JOB_USES_PERSISTENT_STORAGE_LABEL: "true",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }

    # Mock volume operations
    mock_volume = MagicMock()
    docker_client_mock.volumes.get.return_value = mock_volume

    # Test Case 1: Job is NOT in terminal state - should skip persistent storage cleanup
    docker_job.check_job_is_terminal = MagicMock(return_value=False)
    docker_job.cleanup_job_persistent_storage = MagicMock()

    docker_job.cleanup_single_container(mock_container)

    # Verify container and task volumes were cleaned up
    assert mock_container.remove.call_count == 1
    assert docker_client_mock.volumes.get.call_count == 2  # task storage + config volumes

    # Verify persistent storage cleanup was NOT called
    docker_job.cleanup_job_persistent_storage.assert_not_called()

    # Verify check_job_is_terminal was called
    docker_job.check_job_is_terminal.assert_called_once_with(job="test-job-id", workspace="default")

    # Reset mocks
    mock_container.remove.reset_mock()
    docker_client_mock.volumes.get.reset_mock()
    docker_job.cleanup_job_persistent_storage.reset_mock()
    docker_job.check_job_is_terminal.reset_mock()

    # Test Case 2: Job IS in terminal state - should proceed with persistent storage cleanup
    docker_job.check_job_is_terminal = MagicMock(return_value=True)

    docker_job.cleanup_single_container(mock_container)

    # Verify container and task volumes were cleaned up
    assert mock_container.remove.call_count == 1
    assert docker_client_mock.volumes.get.call_count == 2  # task storage + config volumes

    # Verify persistent storage cleanup WAS called
    docker_job.cleanup_job_persistent_storage.assert_called_once_with("default", "test-job-id")

    # Verify check_job_is_terminal was called
    docker_job.check_job_is_terminal.assert_called_once_with(job="test-job-id", workspace="default")


def test_cleanup_single_container_without_persistent_storage_label(docker_job, docker_client_mock):
    """Test that cleanup_single_container doesn't check job terminal state when container doesn't use persistent storage."""
    # Create a mock container WITHOUT persistent storage label
    mock_container = MagicMock()
    mock_container.name = "test-container-no-storage"
    mock_container.id = "no-storage-container-id"
    mock_container.attrs = {
        "State": {"ExitCode": 0},
    }
    mock_container.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "test-job-id",
        JOB_TASK_ID_LABEL: "task-no-storage",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        # No JOB_USES_PERSISTENT_STORAGE_LABEL
    }

    # Mock volume operations
    mock_volume = MagicMock()
    docker_client_mock.volumes.get.return_value = mock_volume

    docker_job.check_job_is_terminal = MagicMock()
    docker_job.cleanup_job_persistent_storage = MagicMock()

    docker_job.cleanup_single_container(mock_container)

    # Verify container and task volumes were cleaned up
    assert mock_container.remove.call_count == 1
    assert docker_client_mock.volumes.get.call_count == 2  # task storage + config volumes

    # Verify job terminal check was NOT called (no persistent storage to cleanup)
    docker_job.check_job_is_terminal.assert_not_called()

    # Verify persistent storage cleanup was NOT called
    docker_job.cleanup_job_persistent_storage.assert_not_called()


def test_cleanup_single_container_step_terminal_but_job_has_more_steps(docker_job, docker_client_mock):
    """Test that persistent storage is NOT cleaned up when a step is terminal but the job has more steps to run.

    This simulates a multi-step job where step 1 completes successfully but step 2 still needs to run.
    The step is in terminal state, but the job is not terminal yet, so persistent storage should be preserved.
    """
    # Create a mock container for step 1 that completed successfully with persistent storage
    mock_container = MagicMock()
    mock_container.name = "test-job-step1"
    mock_container.id = "step1-container-id"
    mock_container.attrs = {
        "State": {"ExitCode": 0},
    }
    mock_container.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "multi-step-job",
        JOB_STEP_NAME_LABEL: "step1",
        JOB_TASK_ID_LABEL: "task-step1",
        JOB_USES_PERSISTENT_STORAGE_LABEL: "true",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
    }

    # Mock volume operations
    mock_volume = MagicMock()
    docker_client_mock.volumes.get.return_value = mock_volume

    # Mock check_step_is_terminal to return True (step 1 is complete)
    docker_job.check_step_is_terminal = MagicMock(return_value=True)

    # Mock check_job_is_terminal to return False (job is not terminal - step 2 still needs to run)
    docker_job.check_job_is_terminal = MagicMock(return_value=False)

    docker_job.cleanup_job_persistent_storage = MagicMock()

    # Call cleanup on the step 1 container
    docker_job.cleanup_single_container(mock_container)

    # Verify container and task volumes were cleaned up
    assert mock_container.remove.call_count == 1
    assert docker_client_mock.volumes.get.call_count == 2  # task storage + config volumes

    # Verify job terminal check WAS called (since container uses persistent storage)
    docker_job.check_job_is_terminal.assert_called_once_with(job="multi-step-job", workspace="default")

    # Verify persistent storage cleanup was NOT called (job is not terminal yet)
    docker_job.cleanup_job_persistent_storage.assert_not_called()


def test_cleanup_steps_with_multi_step_job_only_first_step_complete(docker_job, docker_client_mock):
    """Test cleanup_steps with a multi-step job where only the first step is complete.

    Simulates a job with 2 steps where:
    - Step 1 container has exited successfully (terminal)
    - Step 2 container is still running (non-terminal)
    - The job itself is not terminal (active)

    Persistent storage should NOT be cleaned up.
    """
    docker_job._execution_profile_config.cleanup_completed_jobs_immediately = True

    # Use a recent timestamp so TTL-based cleanup doesn't trigger
    recent_time = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)).isoformat()

    # Mock check_step_is_terminal to return True for step1 (terminal)
    # and False for step2 (non-terminal)
    def check_step_side_effect(job, step_name, workspace):
        if step_name == "step1":
            return True
        return False

    docker_job.check_step_is_terminal = MagicMock(side_effect=check_step_side_effect)

    # Mock check_job_is_terminal to return False (job is not terminal - has more steps)
    docker_job.check_job_is_terminal = MagicMock(return_value=False)

    # Create mock container for step 1 that exited successfully
    mock_container_step1 = MagicMock()
    mock_container_step1.name = "multi-step-job-step1"
    mock_container_step1.id = "step1-container-id"
    mock_container_step1.status = "exited"
    mock_container_step1.attrs = {
        "State": {"ExitCode": 0, "FinishedAt": recent_time},
        "NetworkSettings": {"Networks": {"host": {}}},
    }
    mock_container_step1.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "multi-step-job",
        JOB_STEP_NAME_LABEL: "step1",
        JOB_TASK_ID_LABEL: "task-step1",
        JOB_USES_PERSISTENT_STORAGE_LABEL: "true",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Create mock container for step 2 that is still running
    mock_container_step2 = MagicMock()
    mock_container_step2.name = "multi-step-job-step2"
    mock_container_step2.id = "step2-container-id"
    mock_container_step2.status = "running"
    mock_container_step2.attrs = {"State": {"ExitCode": 0}}
    mock_container_step2.labels = {
        JOB_WORKSPACE_ID_LABEL: "default",
        JOB_ID_LABEL: "multi-step-job",
        JOB_STEP_NAME_LABEL: "step2",
        JOB_TASK_ID_LABEL: "task-step2",
        JOB_USES_PERSISTENT_STORAGE_LABEL: "true",
        JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        JOB_CONTROLLER_INSTANCE_ID_LABEL: TEST_JOBS_CONTROLLER_INSTANCE_ID,
        JOB_TYPE_LABEL: JOB_TYPE_JOB,
    }

    # Mock containers.list to return both containers
    docker_client_mock.containers.list.return_value = [mock_container_step1, mock_container_step2]

    # Mock the network operations
    mock_network = MagicMock()
    docker_client_mock.networks.get.return_value = mock_network

    # Mock volume operations
    mock_volume = MagicMock()
    docker_client_mock.volumes.get.return_value = mock_volume

    # Mock cleanup_job_persistent_storage to track if it's called
    docker_job.cleanup_job_persistent_storage = MagicMock()

    # Run cleanup
    docker_job.cleanup_steps()

    # Verify step 1 container was cleaned up (it's terminal)
    assert mock_container_step1.remove.call_count == 1
    mock_container_step1.remove.assert_called_with(force=True)

    # Verify step 2 container was NOT cleaned up (it's still running)
    mock_container_step2.remove.assert_not_called()

    # Verify network cleanup happened for step 1
    mock_network.disconnect.assert_called_once_with(mock_container_step1)

    # Verify task storage volumes were cleaned up for step 1 (2 volumes per task)
    assert docker_client_mock.volumes.get.call_count == 2
    docker_client_mock.volumes.get.assert_any_call("task-storage-default-multi-step-job-task-step1")
    docker_client_mock.volumes.get.assert_any_call("task-config-default-multi-step-job-task-step1")

    # Verify job terminal check was called for step 1
    docker_job.check_job_is_terminal.assert_called_once_with(job="multi-step-job", workspace="default")

    # Verify persistent storage cleanup was NOT called
    # because the job is not terminal yet (step 2 still running)
    docker_job.cleanup_job_persistent_storage.assert_not_called()
