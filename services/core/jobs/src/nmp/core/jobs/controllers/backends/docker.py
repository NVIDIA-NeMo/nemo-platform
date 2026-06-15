# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime
import io
import json
import logging
import os
import tarfile
import time
import uuid
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Generic, Literal, TypeVar

import docker.types
from docker.errors import APIError, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.types import LogConfig, Mount
from nemo_platform.types.jobs import PlatformJobStepWithContext
from nmp.common.auth import AuthContext
from nmp.common.config import get_platform_config
from nmp.common.docker.gpu_pool import GPUAllocationError
from nmp.common.jobs.constants import (
    CONFIG_TASK_STORAGE_PATH_ENVVAR,
    DEFAULT_CONFIG_STORAGE_PATH,
    DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH,
    DEFAULT_TASK_STORAGE_PATH,
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    NEMO_JOB_ATTEMPT_ID_ENVVAR,
    NEMO_JOB_FILESET_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_SECRETS_ENVVAR,
    NEMO_JOB_STEP_CONFIG_FILE_NAME,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    NEMO_JOB_STEP_ENVVAR,
    NEMO_JOB_TASK_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
    TERMINAL_EXIT_CODES,
)
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.common.observability import start_span_with_ctx
from nmp.common.resources import SharedResourceManager
from nmp.core.jobs.app.constants import (
    JOB_ATTEMPT_ID_LABEL,
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
from nmp.core.jobs.app.ctx import JobContext
from nmp.core.jobs.app.providers import (
    ComputeResources,
    CPUExecutionProvider,
    ExecutionProviderT,
    GPUExecutionProvider,
)
from nmp.core.jobs.app.schemas import BaseExecutionProfile
from nmp.core.jobs.controllers.backends.base import (
    JobBackend,
    JobExecutionProfileConfig,
    JobUpdate,
    get_logs_endpoint_from_fileset,
    resolve_gpu_job_shm_size,
    resolve_task_image,
    staleness_error_message,
)
from nmp.core.jobs.controllers.backends.exceptions import (
    FailedToScheduleError,
    JobStorageError,
    ResourceAllocationError,
)
from opentelemetry import trace
from pydantic import BaseModel, Field

import docker

tracer = trace.get_tracer(__name__)
logger = logging.getLogger(__name__)


def k8s_shm_quantity_to_docker(quantity: str) -> str:
    """Convert a Kubernetes-style memory quantity to docker-py's shm_size string (e.g. '1g', '512m')."""
    q = quantity.strip()
    if q.endswith("Gi"):
        return f"{q[:-2]}g"
    if q.endswith("Mi"):
        return f"{q[:-2]}m"
    if q.endswith("G") and not q.endswith("Gi"):
        return q
    return q


DEFAULT_VOLUME_PERMISSIONS_IMAGE = "busybox"

NEMO_JOBS_IMAGE_REGISTRY_PASSWORD = os.getenv("NEMO_JOBS_IMAGE_REGISTRY_PASSWORD")
NEMO_JOBS_IMAGE_REGISTRY = os.getenv("NEMO_JOBS_IMAGE_REGISTRY")
NEMO_JOBS_IMAGE_REGISTRY_USER_NAME = os.getenv("NEMO_JOBS_IMAGE_REGISTRY_USER_NAME")
NEMO_JOBS_DEFAULT_DOCKER_NETWORK = os.getenv("NEMO_JOBS_DEFAULT_DOCKER_NETWORK", "host")

# Timeout for stopping Docker containers gracefully with SIGTERM before SIGKILL is sent.
# Default is 30 seconds which matches the Kubernetes default grace period for pod termination.
DOCKER_STOP_TIMEOUT = int(os.getenv("NEMO_JOBS_DEFAULT_DOCKER_STOP_TIMEOUT", "30"))


ProviderT = TypeVar("ProviderT", bound=ExecutionProviderT)


class DockerVolumeMount(BaseModel):
    volume_name: str = Field(description="Name of the Docker volume to mount")
    mount_path: str = Field(description="Path inside the container where the volume will be mounted")
    kind: Literal["volume", "tmpfs"] = Field(
        default="volume",
        description="Type of the Docker volume to mount. Options are 'volume' or 'tmpfs' (default: 'volume'). tmpfs volumes are only supported on Linux hosts.",
    )
    options: dict | None = Field(default=None, description="Additional options for the volume")
    allow_create_volume: bool = Field(
        default=False, description="Whether to allow the creation of the volume if it does not exist (default: false)."
    )


class DockerJobStorageConfig(BaseModel):
    """Configuration for persistent storage in Docker jobs."""

    volume_name: str = Field(
        default="nemo-jobs-storage", description="Name of the Docker volume for persistent storage"
    )
    volume_permissions_image: str = Field(
        default=DEFAULT_VOLUME_PERMISSIONS_IMAGE, description="Docker image used to set permissions on the volume"
    )
    additional_volume_mounts: list[DockerVolumeMount] = Field(
        default_factory=list,
        description="List of additional Docker volume mounts for the job",
    )


class DockerJobNetworkConfig(BaseModel):
    job_container_network: str = Field(
        default=NEMO_JOBS_DEFAULT_DOCKER_NETWORK, description="Docker network for the job container"
    )


class DockerJobExecutionProfileConfig(JobExecutionProfileConfig):
    """Configuration for Docker Job execution profile."""

    storage: DockerJobStorageConfig = Field(
        default_factory=DockerJobStorageConfig, description="Docker storage configuration"
    )
    networking: DockerJobNetworkConfig = Field(
        default_factory=DockerJobNetworkConfig, description="Docker networking configuration"
    )


class DockerJobExecutionProfile(BaseExecutionProfile):
    """
    Execution configuration for a Docker Job.
    This is used to define the executor type, provider, profile, and any additional configuration
    required for the executor to run the job on Docker
    """

    backend: Literal["docker"] = "docker"
    config: DockerJobExecutionProfileConfig = Field(description="Additional configuration for the docker executor")

    @property
    def supports_persistent_storage(self) -> bool:
        """Indicates if the execution profile supports persistent storage."""
        return self.config.storage is not None


class DockerJobBackend(JobBackend[ProviderT, DockerJobExecutionProfileConfig], Generic[ProviderT]):
    BACKEND_NAME: str = "docker"

    def init(self) -> None:
        self._container_run_threadpool = ThreadPoolExecutor(max_workers=10)
        self._client = docker.from_env(timeout=180)
        if NEMO_JOBS_IMAGE_REGISTRY:
            logger.info(
                f"Got image registry config, logging into {NEMO_JOBS_IMAGE_REGISTRY} with {NEMO_JOBS_IMAGE_REGISTRY_USER_NAME}"
            )
            self._client.login(
                username=NEMO_JOBS_IMAGE_REGISTRY_USER_NAME,
                password=NEMO_JOBS_IMAGE_REGISTRY_PASSWORD,
                registry=NEMO_JOBS_IMAGE_REGISTRY,
            )

    def shutdown(self) -> None:
        self._container_run_threadpool.shutdown(wait=True)
        self._client.close()

    @staticmethod
    def get_label_from_container(container: Container, label: str) -> str:
        return container.labels[label]

    @staticmethod
    def _is_container_managed_by_jobs_controller(container: Container) -> bool:
        """Return True if the container has the jobs-controller managed-by label."""
        labels = getattr(container, "labels", None) or {}
        return labels.get(JOB_MANAGED_BY_LABEL) == JOB_MANAGED_BY_JOBS_CONTROLLER

    def job_storage_subpath(self, workspace: str, job: str) -> str:
        return f"jobs/{workspace}/{job}"

    def task_storage_volume_name(self, workspace: str, job: str, task: str) -> str:
        """Generate a unique volume name for task storage space."""
        return f"task-storage-{workspace}-{job}-{task}"

    def task_config_volume_name(self, workspace: str, job: str, task: str) -> str:
        """Generate a unique volume name for task config space."""
        return f"task-config-{workspace}-{job}-{task}"

    def cleanup_task_storage_volumes(self, workspace: str, job: str, task: str) -> None:
        """Remove the task storage volume after the container is done."""

        volumes_to_delete = [
            self.task_storage_volume_name(workspace, job, task),
            self.task_config_volume_name(workspace, job, task),
        ]
        for volume_name in volumes_to_delete:
            try:
                volume = self._client.volumes.get(volume_name)
                volume.remove(force=True)
                logger.debug("Cleaned up task storage volume", extra={"volume_name": volume_name})
            except NotFound:
                logger.warning(
                    "Task storage volume not found, may have been already cleaned up",
                    extra={"volume_name": volume_name},
                )
            except Exception:
                logger.exception("Failed to clean up task storage volume", extra={"volume_name": volume_name})

    def cleanup_job_persistent_storage(self, workspace: str, job: str) -> None:
        """Remove persistent job storage from the shared volume after successful job completion."""
        storage_config = self._execution_profile_config.storage
        if storage_config is None or storage_config.volume_name == "":
            logger.debug(
                "No persistent storage configured, skipping cleanup for job", extra={"workspace": workspace, "job": job}
            )
            return

        job_storage_subpath = self.job_storage_subpath(workspace, job)
        cleanup_script = f"""#!/bin/sh
set -ex
# Remove the job's storage directory
if [ -d "/vol/{job_storage_subpath}" ]; then
    rm -rf "/vol/{job_storage_subpath}"
    echo "Removed persistent storage for job {workspace}/{job}"
else
    echo "Storage directory not found, may have been already cleaned up"
fi
"""

        fileobj = io.BytesIO()
        with tarfile.open(fileobj=fileobj, mode="w") as tar:
            info = tarfile.TarInfo(name="cleanup.sh")
            info.size = len(cleanup_script)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(cleanup_script.encode("utf-8")))
        fileobj.seek(0)

        volumes = {storage_config.volume_name: {"bind": "/vol", "mode": "rw"}}

        labels = {
            JOB_WORKSPACE_ID_LABEL: workspace,
            JOB_ID_LABEL: job,
            JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
            JOB_TYPE_LABEL: JOB_TYPE_STORAGE_CLEANUP,
            JOB_EXECUTION_BACKEND_LABEL: self.BACKEND_NAME,
            JOB_EXECUTION_PROFILE_LABEL: self._profile_name,
        }
        container_args = {
            "name": f"job-cleanup-{workspace}-{job}-{uuid.uuid4().hex[:8]}",
            "image": storage_config.volume_permissions_image,
            "command": ["sh", "/cleanup.sh"],
            "volumes": volumes,
            "labels": labels,
        }

        try:
            container = self._client.containers.create(**container_args)
        except ImageNotFound:
            # Try pulling the image if not found locally
            self._client.images.pull(storage_config.volume_permissions_image)
            container = self._client.containers.create(**container_args)
        except APIError:
            logger.error(
                "Error creating cleanup container for job", extra={"workspace": workspace, "job": job}, exc_info=True
            )
            return

        container.put_archive(path="/", data=fileobj)
        try:
            container.start()
        except APIError:
            logger.error(
                "Error starting cleanup container for job", extra={"workspace": workspace, "job": job}, exc_info=True
            )
            self.cleanup_container(container)
            return

        try:
            exit_status = container.wait()
            if exit_status["StatusCode"] != 0:
                logger.warning(
                    "Cleanup container for job exited with non-zero status",
                    extra={"workspace": workspace, "job": job, "exit_code": exit_status["StatusCode"]},
                )
        except APIError:
            logger.error(
                "Error waiting for cleanup container for job", extra={"workspace": workspace, "job": job}, exc_info=True
            )
        finally:
            self.cleanup_container(container)

    def cleanup_container(self, container: Container) -> None:
        """Remove a Docker container. Only removes containers managed by the jobs controller."""
        if not self._is_container_managed_by_jobs_controller(container):
            logger.warning(
                "Skipping container remove (not managed by jobs-controller)",
                extra={"container_id": container.id[:16] if container.id else "unknown"},
            )
            return
        try:
            container.remove(force=True)
            logger.debug("Removed container", extra={"container_id": container.id[:16]})  # type: ignore
        except NotFound:
            logger.warning(
                "Container not found, may have been already removed", extra={"container_id": container.id[:16]}
            )  # type: ignore
        except Exception:
            logger.exception("Failed to remove container", extra={"container_id": container.id[:16]})  # type: ignore

    def cleanup_container_network(self, container: Container) -> None:
        """Remove a Docker network."""

        # First check if the container is attached to the network
        network_name = self._execution_profile_config.networking.job_container_network
        if network_name not in container.attrs.get("NetworkSettings", {}).get("Networks", {}):
            logger.debug(
                "Container already detached from network",
                extra={"container_id": container.id[:16], "network_name": network_name},
            )  # type: ignore
            return

        # If it is, disconnect it
        network = self._client.networks.get(network_name)
        network.disconnect(container)
        logger.debug(
            "Removed network from container", extra={"container_id": container.id[:16], "network_name": network_name}
        )  # type: ignore

    def get_mounts(
        self,
        workspace: str,
        job: str,
        job_volume_name: str,
        job_volume_path: str,
        config_volume_name: str,
        config_volume_path: str,
        task_volume_name: str,
        task_volume_path: str,
        additional_volume_mounts: list[DockerVolumeMount] | None = None,
    ) -> list[Mount]:
        """
        Create `Mount` objects that attach persistent storage to the container.
        We need the more advanced `mounts` over `volumes` so we can utilize the `Subpath` option.
        This allows us to mount in a subpath of an existing volume, ensuring that the mount
        can't see more than we explicitly allow. This is essential so one job can't see
        the activity of another one.
        """

        task_storage_mount = docker.types.Mount(
            type="volume",
            source=task_volume_name,
            target=task_volume_path,
        )
        config_storage_mount = docker.types.Mount(
            type="volume",
            source=config_volume_name,
            target=config_volume_path,
        )

        mounts = [
            task_storage_mount,
            config_storage_mount,
        ]

        if job_volume_path != "":
            job_storage_mount = docker.types.Mount(
                type="volume",
                source=job_volume_name,
                target=job_volume_path,
            )
            job_storage_mount["VolumeOptions"] = {"Subpath": self.job_storage_subpath(workspace, job)}
            mounts.append(job_storage_mount)

        if additional_volume_mounts:
            for vol_mount in additional_volume_mounts:
                mount = docker.types.Mount(
                    type=vol_mount.kind,
                    source=vol_mount.volume_name,
                    target=vol_mount.mount_path,
                )
                if vol_mount.options:
                    mount["VolumeOptions"] = vol_mount.options
                mounts.append(mount)

        return mounts

    def ensure_job_storage(
        self,
        job_storage_volume_name: str,
        permissions_image: str,
        workspace: str,
        job: str,
        task: str,
        step_config_json: str,
        additional_volumes_mounts: list[DockerVolumeMount] | None = None,
    ) -> None:
        """
        Ensure Docker volumes exist for the job and task, with proper permissions.
        This creates:
        1. A task-specific storage volume for temporary task storage
        2. Job-specific subpaths in the shared job volume for persistent storage, if requested

        Both volumes are configured with proper permissions so non-root-user containers can access them.
        """

        task_vol = "/task-vol"
        task_volume_name = self.task_storage_volume_name(workspace, job, task)
        try:
            self._client.volumes.create(task_volume_name)
            logger.debug("Created task storage volume", extra={"volume_name": task_volume_name})
        except Exception as exc:
            raise JobStorageError(f"Error creating task storage volume {task_volume_name}") from exc

        # create a config volume for placing config files if needed
        config_vol = "/config-vol"
        config_volume_name = self.task_config_volume_name(workspace, job, task)
        try:
            self._client.volumes.create(config_volume_name)
            logger.debug("Created task config volume", extra={"volume_name": config_volume_name})
        except Exception as exc:
            raise JobStorageError(f"Error creating task config volume {config_volume_name}") from exc

        script = f"""#!/bin/sh
set -ex
chmod -R 777 {task_vol}
cat > {config_vol}/{NEMO_JOB_STEP_CONFIG_FILE_NAME} << 'EOF'
{step_config_json}
EOF
cat {config_vol}/{NEMO_JOB_STEP_CONFIG_FILE_NAME}
chmod -R 777 {config_vol}
"""
        volumes = {
            task_volume_name: {"bind": task_vol, "mode": "rw"},
            config_volume_name: {"bind": config_vol, "mode": "rw"},
        }

        if job_storage_volume_name != "":
            job_vol = "/job-vol"
            storage_subpath = self.job_storage_subpath(workspace, job)
            script += f"""
mkdir -p {job_vol}/{storage_subpath}
chmod -R 777 {job_vol}/{storage_subpath}
"""
            try:
                self._client.volumes.get(job_storage_volume_name)
                logger.debug(
                    "Volume exists for job",
                    extra={"volume_name": job_storage_volume_name, "workspace": workspace, "job": job},
                )
            except NotFound:
                logger.info(
                    "Could not find storage volume, creating one now", extra={"volume_name": job_storage_volume_name}
                )
                self._client.volumes.create(job_storage_volume_name)
            volumes[job_storage_volume_name] = {"bind": job_vol, "mode": "rw"}

        if additional_volumes_mounts:
            for vol_mount in additional_volumes_mounts:
                # Check for existence of the additional volume
                try:
                    self._client.volumes.get(vol_mount.volume_name)
                    logger.debug("Additional volume already exists", extra={"volume_name": vol_mount.volume_name})
                except NotFound as e:
                    if vol_mount.allow_create_volume:
                        logger.info(
                            "Could not find additional volume, creating one now",
                            extra={"volume_name": vol_mount.volume_name},
                        )
                        self._client.volumes.create(vol_mount.volume_name)
                    else:
                        raise JobStorageError(f"Additional volume {vol_mount.volume_name} not found") from e

                volumes[vol_mount.volume_name] = {"bind": vol_mount.mount_path, "mode": "rw"}

        script += "\necho 'Job init completed.'\n"

        fileobj = io.BytesIO()
        with tarfile.open(fileobj=fileobj, mode="w") as tar:
            info = tarfile.TarInfo(name="job-init.sh")
            info.size = len(script)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(script.encode("utf-8")))
        fileobj.seek(0)

        try:
            container = self._client.containers.create(
                name=f"job-init-{workspace}-{job}-{task}",
                image=permissions_image,
                command=["sh", "/job-init.sh"],
                volumes=volumes,
            )
        except ImageNotFound:
            # Try pulling the permissions image if not found locally
            self._client.images.pull(permissions_image)
            container = self._client.containers.create(
                name=f"job-init-{workspace}-{job}-{task}",
                image=permissions_image,
                command=["sh", "/job-init.sh"],
                volumes=volumes,
            )
        except APIError as exc:
            raise JobStorageError(f"Error creating job init container with image {permissions_image}") from exc

        container.put_archive(path="/", data=fileobj)
        try:
            container.start()
        except Exception as exc:
            self.cleanup_task_storage_volumes(workspace, job, task)
            raise JobStorageError("Error starting job init container") from exc

        exit_status = container.wait()
        if exit_status["StatusCode"] != 0:
            self.cleanup_task_storage_volumes(workspace, job, task)
            raise JobStorageError(f"Job init container exited with non-zero status {exit_status['StatusCode']}")

        try:
            container.remove()
        except Exception as e:
            raise JobStorageError("Failed to remove job init container") from e

    def schedule_single_container(
        self,
        executor_config: ProviderT,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        ttl_seconds = self._execution_profile_config.ttl_seconds_before_active
        if self.should_enforce_before_active_ttl(step) and self.check_step_ttl_before_active(step, ttl_seconds):
            # If we are here it is because the scheduler kept retrying the job,
            # which means there was a resource issue (GPU contention).  Nothing really
            # imperative to clean up, just mark as ERROR.
            return JobUpdate(
                status=PlatformJobStatus.ERROR.value,
                status_details={"message": f"Job timed out after reaching max TTL of {ttl_seconds} seconds"},
                error_details={"message": f"Job timed out after reaching max TTL of {ttl_seconds} seconds"},
            )

        platform_config = get_platform_config()

        # Profile-level env vars first (e.g. HOME=/tmp); system, step, and shared env override these
        env = self._execution_profile_config.env.copy()

        # identify the task using a uuid.  In docker, there's only one task per step.
        # because parallelism and completions are not supported.
        task_id = f"task-{uuid.uuid4().hex}"
        env.update(
            {
                NEMO_JOB_ID_ENVVAR: step.job,
                NEMO_JOB_ATTEMPT_ID_ENVVAR: step.attempt_id,
                NEMO_JOB_STEP_ENVVAR: step.name,
                NEMO_JOB_TASK_ENVVAR: task_id,
                NEMO_JOB_WORKSPACE_ENVVAR: step.workspace,
                NEMO_JOB_FILESET_ENVVAR: step.fileset,
                EPHEMERAL_TASK_STORAGE_PATH_ENVVAR: DEFAULT_TASK_STORAGE_PATH,
                CONFIG_TASK_STORAGE_PATH_ENVVAR: DEFAULT_CONFIG_STORAGE_PATH,
                NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR: DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH,
                # Forward OTEL env vars for jobs-launcher to emit telemetry, particularly logs
                "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": get_logs_endpoint_from_fileset(
                    platform_config,
                    step.workspace,
                    step.fileset,
                ),
                "OTEL_LOGS_EXPORTER": "otlp",
                "OTEL_SERVICE_NAME": "nmp-job-task",
                # Inject secret environment variable mappings for the jobs-launcher to fetch
                NEMO_JOB_SECRETS_ENVVAR: self.get_secrets_environment_variable_for_injection(step),
            }
        )

        # Set auth context env var for job containers to make authenticated API calls
        if step.auth_context:
            sdk_auth_context = step.auth_context
            auth_context = AuthContext.model_validate(sdk_auth_context.model_dump(mode="python", exclude_none=True))
            principal = auth_context.to_principal()
            env_var_dict = principal.get_env_var()
            for name, value in env_var_dict.items():
                env[name] = value
            # Also set OTLP headers for telemetry (logs) to be authenticated
            env["OTEL_EXPORTER_OTLP_LOGS_HEADERS"] = principal.get_otlp_headers_value()

        step_config_json = json.dumps(step.step_spec.config)

        job_storage_mount = ""
        task_storage_mount = DEFAULT_TASK_STORAGE_PATH

        # Update the step container's environment variables for non-secret values
        if step.step_spec.environment:
            for envvar in step.step_spec.environment:
                if envvar.value is not None:
                    # If the job has requested persistent job storage path, capture it for use when constructing the volume mount.
                    if envvar.name == PERSISTENT_JOB_STORAGE_PATH_ENVVAR:
                        job_storage_mount = envvar.value

                    # The job has explicitly overridden the mount path for task storage.
                    # Since this fields has already been set via environment variables, we should update the appropriate variable instead.
                    elif envvar.name == EPHEMERAL_TASK_STORAGE_PATH_ENVVAR:
                        task_storage_mount = envvar.value

                    env[envvar.name] = envvar.value

        # Thread through shared platform envvars to the job
        # Note: address_override defaults to None, which triggers automatic loopback detection
        env.update(platform_config.to_shared_envvars())

        log_config = LogConfig(
            type=LogConfig.types.JSON,
            config={
                "labels": ",".join(
                    [JOB_WORKSPACE_ID_LABEL, JOB_ID_LABEL, JOB_ATTEMPT_ID_LABEL, JOB_STEP_NAME_LABEL, JOB_TASK_ID_LABEL]
                )
            },
        )

        storage_config = self._execution_profile_config.storage
        job_volume_name = storage_config.volume_name if storage_config is not None else ""
        task_volume_name = self.task_storage_volume_name(workspace=step.workspace, job=step.job, task=task_id)
        config_volume_name = self.task_config_volume_name(workspace=step.workspace, job=step.job, task=task_id)
        additional_volume_mounts = storage_config.additional_volume_mounts if storage_config else None
        self.ensure_job_storage(
            # if the job storage mount is not used, pass empty string to avoid creating unnecessary job storage volume
            job_storage_volume_name=job_volume_name if job_storage_mount != "" else "",
            permissions_image=storage_config.volume_permissions_image
            if storage_config is not None
            else DEFAULT_VOLUME_PERMISSIONS_IMAGE,
            workspace=step.workspace,
            job=step.job,
            task=task_id,
            additional_volumes_mounts=additional_volume_mounts,
            step_config_json=step_config_json,
        )

        labels = {
            JOB_WORKSPACE_ID_LABEL: step.workspace,
            JOB_ID_LABEL: step.job,
            JOB_ATTEMPT_ID_LABEL: step.attempt_id,
            JOB_STEP_NAME_LABEL: step.name,
            # identify the task using a uuid.  In docker, there's only one task per step.
            # because parallelism is not supported.
            JOB_TASK_ID_LABEL: task_id,
            JOB_STEP_ID_LABEL: step.id,
            JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
            JOB_TYPE_LABEL: JOB_TYPE_JOB,
            JOB_EXECUTION_BACKEND_LABEL: self.BACKEND_NAME,
            JOB_EXECUTION_PROFILE_LABEL: self._profile_name,
        }

        # Mark container if it uses persistent storage so we can clean it up later
        if job_storage_mount != "":
            labels[JOB_USES_PERSISTENT_STORAGE_LABEL] = "true"
        else:
            labels[JOB_USES_PERSISTENT_STORAGE_LABEL] = "false"

        task_image = resolve_task_image(
            executor_config.container.image, self._execution_profile_config.default_task_image
        )
        container_args = {
            "name": self.name_for_step(step),
            "entrypoint": executor_config.container.entrypoint or [],
            "command": executor_config.container.command or [],
            "image": task_image,
            "labels": labels,
            "log_config": log_config,
            "environment": env,
            "detach": True,
            "init": True,
            "mounts": self.get_mounts(
                workspace=step.workspace,
                job=step.job,
                job_volume_name=job_volume_name,
                job_volume_path=job_storage_mount,
                config_volume_name=config_volume_name,
                config_volume_path=DEFAULT_CONFIG_STORAGE_PATH,
                task_volume_name=task_volume_name,
                task_volume_path=task_storage_mount,
                additional_volume_mounts=additional_volume_mounts,
            ),
        }

        container_args["network"] = self._execution_profile_config.networking.job_container_network
        container_args = self.configure_container(container_args, executor_config)
        self._container_run_threadpool.submit(self.run_container, step, container_args)
        return JobUpdate(
            status=PlatformJobStatus.PENDING,
            status_details={"message": "Container schedule pending, checking for existing image and container"},
        )

    def cancel_scheduling(self, step: PlatformJobStepWithContext) -> bool:
        """Check if the job step is cancelling or pausing, and update status accordingly."""
        updated_step = self.get_step(step_name=step.name, job=step.job, workspace=step.workspace)
        is_cancelling_or_pausing = updated_step.status in (
            PlatformJobStatus.CANCELLING,
            PlatformJobStatus.CANCELLED,
            PlatformJobStatus.PAUSING,
            PlatformJobStatus.PAUSED,
        )

        if is_cancelling_or_pausing:
            if updated_step.status in (
                PlatformJobStatus.CANCELLED,
                PlatformJobStatus.PAUSED,
            ):
                logger.info(
                    "Job step is already in terminal state, no update required", extra={"status": updated_step.status}
                )
                return True  # Already in terminal state, no step updates needed

            status_details = {}
            if updated_step.status == PlatformJobStatus.PAUSING:
                status = PlatformJobStatus.PAUSED
                status_details["message"] = "Job is paused, not creating container"
            else:
                status = PlatformJobStatus.CANCELLED
                status_details["message"] = "Job is cancelled, not creating container"
            logger.info("Job step is not scheduling container", extra={"status": updated_step.status})
            self._nmp_sdk.jobs.steps.update_status(
                step.name,
                workspace=step.workspace,
                job=step.job,
                status=status.value,
                status_details=status_details,
            )
        return is_cancelling_or_pausing

    def get_jobs_launcher_binary(self) -> io.BytesIO | None:
        """Get a copy of the jobs-launcher binary as a tar stream to include in the job container."""
        jobs_launcher_stream = None
        if os.path.exists(self._execution_profile_config.launcher_tool_path):
            jobs_launcher_stream = io.BytesIO()
            with (
                tarfile.open(fileobj=jobs_launcher_stream, mode="w") as tar,
                open(self._execution_profile_config.launcher_tool_path, "rb") as f,
            ):
                file_data = f.read()
                tarinfo = tarfile.TarInfo(name="jobs-launcher")
                tarinfo.size = len(file_data)
                tarinfo.mode = 0o755  # Make it executable
                tar.addfile(tarinfo, io.BytesIO(file_data))
            jobs_launcher_stream.seek(0)
            return jobs_launcher_stream
        return None

    def run_container(self, step: PlatformJobStepWithContext, container_args: dict):
        with start_span_with_ctx(
            tracer, "jobs_controller/docker_backend/run_container", JobContext(id=step.job, step_name=step.name)
        ):
            try:
                self._run_container_in_thread(step, container_args)
            except FailedToScheduleError as e:
                status = PlatformJobStatus.ERROR
                self._nmp_sdk.jobs.steps.update_status(
                    step.name,
                    workspace=step.workspace,
                    job=step.job,
                    status=status.value,
                    error_details=e.error_details,  # type: ignore
                )
                logger.exception("Failed to schedule container for job step")
            except Exception:
                logger.exception("Unexpected error while scheduling container for job step")

    def _run_container_in_thread(self, step: PlatformJobStepWithContext, container_args: dict):
        status_details = {}
        status = PlatformJobStatus.PENDING.value

        # If a request to pause or cancel came in while we were waiting for scheduling loop,
        # cancel scheduling the container
        logger.debug("Checking for cancellation or pausing before creating container")
        if self.cancel_scheduling(step):
            return

        # For resuming containers, check if it already exists
        logger.debug("Checking for existing container for job step")
        container = self.get_container(step)
        if container is not None:
            logger.info("Container already exists, not creating a new one", extra={"container_name": container.name})
        else:
            # Container not found, create it
            logger.debug("Creating container for job step")

            # Find the jobs launcher binary inside this running python container and also include it in the job container
            jobs_launcher_stream = self.get_jobs_launcher_binary()
            if jobs_launcher_stream is not None:
                # Modify the container entrypoint and command to use the jobs-launcher
                original_entrypoint = container_args.get("entrypoint", [])
                container_args["entrypoint"] = ["/jobs-launcher", "run", "--"] + original_entrypoint
                logger.debug("Jobs launcher found, will be included in container")
            else:
                logger.warning(
                    "Jobs launcher not found, container will use original entrypoint",
                    extra={"launcher_tool_path": self._execution_profile_config.launcher_tool_path},
                )

            try:
                container = self._client.containers.create(**container_args)
                # Container will create successfully only if image is found locally
                logger.info("Image found locally", extra={"image": container_args["image"]})
            except (ImageNotFound, NotFound):
                # Image not found locally, pull it
                logger.info("Image not found locally, pulling from registry", extra={"image": container_args["image"]})
                status_details["message"] = f"Pulling image {container_args['image']} from registry"

                # Send the status update to indicate we are pulling the image
                self._nmp_sdk.jobs.steps.update_status(
                    step.name,
                    workspace=step.workspace,
                    job=step.job,
                    status=status,
                    status_details=status_details,
                )
                try:
                    pull_start = time.time()
                    self._client.images.pull(container_args["image"])
                    pull_elapsed = time.time() - pull_start
                    logger.info(
                        "Successfully pulled image for job step",
                        extra={"image": container_args["image"], "pull_elapsed_s": f"{pull_elapsed:.1f}"},
                    )
                except APIError as e:
                    raise FailedToScheduleError(
                        "Failed to pull image",
                        error_details={"message": f"Failed to pull image {container_args['image']}: {e}"},
                    ) from e

                # If a request to pause or cancel came in while we were pulling down an image,
                # cancel scheduling the container
                logger.debug("Checking for cancellation or pausing before creating container after image pull")
                if self.cancel_scheduling(step):
                    return

                # Send the status update to indicate we are starting the container
                status_details["message"] = f"Creating container with image {container_args['image']}"
                self._nmp_sdk.jobs.steps.update_status(
                    step.name,
                    workspace=step.workspace,
                    job=step.job,
                    status=status,
                    status_details=status_details,
                )

                # Now create it with the pulled container image
                logger.debug("Creating container for job step after pulling image")
                try:
                    container = self._client.containers.create(**container_args)
                except APIError as e:
                    raise FailedToScheduleError(
                        "Failed to create container for job step",
                        error_details={"message": f"Failed to create container after pulling image: {e}"},
                    ) from e
            except APIError as e:
                raise FailedToScheduleError(
                    "Failed to create container for job step",
                    error_details={"message": f"Failed to create container: {e}"},
                ) from e

            # Insert the jobs-launcher into the container if the launcher exists
            if jobs_launcher_stream is not None:
                try:
                    container.put_archive(path="/", data=jobs_launcher_stream)
                    logger.debug("Jobs launcher inserted into container successfully")
                except APIError as e:
                    raise FailedToScheduleError(
                        "Failed to insert jobs-launcher into container",
                        error_details={"message": f"Failed to add jobs-launcher to job container: {e}"},
                    ) from e

        # At this point we now have container created successfully, including the jobs launcher container if applicable
        logger.info("Created container for job step", extra={"container_name": container.name})

        # If a request to pause or cancel came in while we were waiting for scheduling loop,
        # cancel scheduling the container
        logger.debug("Checking for cancellation or pausing before starting container")
        if self.cancel_scheduling(step):
            return

        try:
            # If no errors to this point, start the container
            status_details["message"] = "Starting container"
            self._nmp_sdk.jobs.steps.update_status(
                step.name,
                workspace=step.workspace,
                job=step.job,
                status=status,
                status_details=status_details,
            )
            started = False
            max_attempts = 3
            attempts = 0
            while not started and attempts < max_attempts:
                attempts += 1
                try:
                    container.start()
                    started = True
                except APIError as e:
                    logger.warning(
                        "Attempt to start container failed",
                        extra={"attempt": attempts, "container_name": container.name},
                        exc_info=True,
                    )
                    # Raise the exception if max attempts reached
                    if attempts >= max_attempts:
                        raise e

                    time.sleep(5)  # brief pause before retrying
            logger.info(
                "Started container for job step", extra={"container_name": container.name, "attempts": attempts}
            )
        except Exception as e:
            raise FailedToScheduleError(
                f"Failed to start container {container.name} for job step",
                error_details={"message": f"Failed to start container: {e}"},
            ) from e

    def _sync(self, step: PlatformJobStepWithContext) -> JobUpdate:
        container: Container | None = self.get_container(step)
        if step.status == PlatformJobStatus.ACTIVE:
            if result := self.enforce_sync_ttl(
                step, self._execution_profile_config.ttl_seconds_active, container, before_active=False
            ):
                return result
            if container is not None and self.check_step_is_stale(step):
                message = staleness_error_message(step.step_spec.lifecycle.staleness_timeout_seconds)
                return self._kill_container_with_error(step, container, message)
            return self.sync_active(step, container)
        elif step.status == PlatformJobStatus.PENDING:
            if result := self.enforce_sync_ttl(
                step,
                self._execution_profile_config.ttl_seconds_before_active,
                container,
                before_active=True,
            ):
                return result
            return self.sync_pending(step, container)
        elif step.status == PlatformJobStatus.CANCELLING:
            # Handle cases where container is already gone, or was never created in the first place
            if container is None:
                return JobUpdate(
                    status=PlatformJobStatus.CANCELLED,
                    status_details={"message": "Container not found, job cancelled"},
                )
            return self.sync_stop_container(step, container)
        elif step.status == PlatformJobStatus.PAUSING:
            # Handle cases where container is already gone, or was never created in the first place
            if container is None:
                return JobUpdate(
                    status=PlatformJobStatus.PAUSED, status_details={"message": "Container not found, job paused"}
                )
            return self.sync_stop_container(step, container)
        else:
            raise ValueError(f"Unhandled job status during sync: {step.status}")

    def get_container(self, step: PlatformJobStepWithContext) -> Container | None:
        container_name = self.name_for_step(step)
        try:
            return self._client.containers.get(container_name)
        except NotFound:
            return None

    def enforce_sync_ttl(
        self,
        step: PlatformJobStepWithContext,
        ttl_seconds: int,
        container: Container | None,
        *,
        before_active: bool = False,
    ) -> JobUpdate | None:
        ttl_exceeded = (
            self.check_step_ttl_before_active(step, ttl_seconds)
            if before_active
            else self.check_step_ttl(step, ttl_seconds)
        )
        if not ttl_exceeded:
            return None

        message = f"Job timed out after reaching max TTL of {ttl_seconds} seconds"

        if container is None:
            return JobUpdate(
                status=PlatformJobStatus.ERROR.value,
                status_details={"message": message},
                error_details={"message": message},
            )

        return self._kill_container_with_error(step, container, message)

    def _kill_container_with_error(
        self, step: PlatformJobStepWithContext, container: Container, message: str
    ) -> JobUpdate:
        """Kill a managed container, update its task to ERROR, and return a JobUpdate."""
        status_details = {"message": message}
        error_details = {"message": message}

        if not self._is_container_managed_by_jobs_controller(container):
            logger.warning(
                "Skipping container kill (not managed by jobs-controller)",
                extra={"container_name": container.name},
            )
            return JobUpdate(
                status=PlatformJobStatus.ERROR.value,
                status_details=status_details,
                error_details=error_details,
            )

        try:
            container.kill()
        except APIError as e:
            if e.status_code == 409:
                logger.warning("Container already stopping or stopped", extra={"container_name": container.name})
            else:
                raise

        task_id = self.get_label_from_container(container, JOB_TASK_ID_LABEL)
        self._nmp_sdk.jobs.tasks.create_or_update(
            task_id,
            workspace=step.workspace,
            job=step.job,
            step=step.name,
            status=PlatformJobStatus.ERROR.value,
            status_details=status_details,  # type: ignore
            error_details=error_details,  # type: ignore
        )
        logger.info(
            "Updated task",
            extra={
                "job": step.job,
                "step_name": step.name,
                "task_id": task_id,
                "status": PlatformJobStatus.ERROR,
                "error_details": error_details,
            },
        )
        return JobUpdate(
            status=PlatformJobStatus.ERROR.value, status_details=status_details, error_details=error_details
        )

    def sync_pending(self, step: PlatformJobStepWithContext, container: Container | None) -> JobUpdate:
        if container is None:
            # Job doesn't exist yet
            return JobUpdate(
                status=PlatformJobStatus.PENDING,
                # status details are not set in this case to avoid overwriting any existing details
                # propagated from the scheduling loop
            )
        else:
            return self.create_step_update(step, container)

    def sync_active(self, step: PlatformJobStepWithContext, container: Container | None) -> JobUpdate:
        if container is None:
            container_name = self.name_for_step(step)
            logger.error("Container not found while syncing active step: %s", container_name)
            return JobUpdate(
                status=PlatformJobStatus.ERROR,
                error_details={"message": "Container not found while syncing active step"},
            )
        else:
            return self.create_step_update(step, container)

    def sync_stop_container(self, step: PlatformJobStepWithContext, container: Container | None) -> JobUpdate:
        if container is None:
            container_name = self.name_for_step(step)
            logger.error("Container not found while stopping container: %s", container_name)
            # Job was deleted
            return JobUpdate(
                status=PlatformJobStatus.ERROR,
                error_details={"message": "Container not found while stopping container"},
            )
        else:
            if not self._is_container_managed_by_jobs_controller(container):
                logger.warning(
                    "Skipping container stop (not managed by jobs-controller)",
                    extra={"container_name": container.name},
                )
                return JobUpdate(
                    status=PlatformJobStatus.ERROR,
                    error_details={"message": "Container not managed by jobs controller"},
                )
            try:
                logger.debug(
                    "Stopping container for job step", extra={"container_name": container.name, "step_name": step.name}
                )
                container.stop(timeout=DOCKER_STOP_TIMEOUT)
                return self.create_step_update(step, container)
            except APIError as e:
                if e.status_code == 409:
                    # Container already stopping or stopped
                    logger.warning(
                        "Container already stopping or stopped when calling stop",
                        extra={"container_name": container.name},
                    )
                    return self.create_step_update(step, container)
                else:
                    raise e

    def create_step_update(self, step: PlatformJobStepWithContext, container: Container) -> JobUpdate:
        status, status_details, error_stack = self.map_docker_container_status_to_platform_status(step, container)
        task_id = self.get_label_from_container(container, JOB_TASK_ID_LABEL)
        error_details = {}
        if status == PlatformJobStatus.ERROR:
            error_details["message"] = status_details.get("message", "Job encountered an error")

        # Upsert the task against the Jobs API.
        self._nmp_sdk.jobs.tasks.create_or_update(
            task_id,
            workspace=step.workspace,
            job=step.job,
            step=step.name,
            status=status.value,
            status_details=status_details,
            error_details=error_details,
            error_stack=error_stack,
        )
        logger.info("Updated task", extra={"task_id": task_id, "status": status})
        return JobUpdate(status=status.value, status_details=status_details, error_details=error_details)

    def map_docker_container_status_to_platform_status(
        self, step: PlatformJobStepWithContext, container: Container
    ) -> tuple[PlatformJobStatus, dict, str]:
        status_details = {}
        error_stack = ""
        is_cancelling = step.status == PlatformJobStatus.CANCELLING
        is_pausing = step.status == PlatformJobStatus.PAUSING
        if container.status == "running":
            if is_cancelling:
                return PlatformJobStatus.CANCELLING, {"message": "Job is cancelling"}, error_stack
            elif is_pausing:
                return PlatformJobStatus.PAUSING, {"message": "Job is pausing"}, error_stack
            else:
                return PlatformJobStatus.ACTIVE, {"message": "Job is running"}, error_stack
        elif container.status in ("exited", "dead"):
            attrs = container.attrs or {}
            exit_code = attrs.get("State", {}).get("ExitCode", 0)
            status_details["exit_code"] = exit_code
            if exit_code == 0:
                if is_cancelling:
                    return (
                        PlatformJobStatus.CANCELLED,
                        {"message": f"Job was cancelled successfully with exit code {exit_code}"},
                        error_stack,
                    )
                elif is_pausing:
                    return (
                        PlatformJobStatus.PAUSED,
                        {"message": f"Job paused successfully with exit code {exit_code}"},
                        error_stack,
                    )
                else:
                    return (
                        PlatformJobStatus.COMPLETED,
                        {"message": f"Job completed successfully with exit code {exit_code}"},
                        error_stack,
                    )
            elif exit_code == 137 and is_cancelling:
                # 137 is SIGKILL, which is what Docker sends after the grace period expires
                return (
                    PlatformJobStatus.CANCELLED,
                    {"message": f"Job was cancelled successfully with exit code {exit_code}"},
                    error_stack,
                )
            else:
                # Get logs for error stack
                try:
                    # Get last 80 lines of logs and up to 2048 characters
                    logs = container.logs(tail=80).decode("utf-8", errors="ignore")
                    error_stack = logs
                    if len(error_stack) > 2048:
                        error_stack = error_stack[-2048:]
                except Exception as exc:
                    logger.error("Failed to get logs for container %s: %s", container.name, exc)

                return (
                    PlatformJobStatus.ERROR,
                    {
                        "message": f"Job exited with non-zero code {exit_code}, check logs for details.",
                        "exit_code": exit_code,
                    },
                    error_stack,
                )
        elif container.status in ("created"):
            return PlatformJobStatus.PENDING, {"message": "Job is pending"}, error_stack

        raise ValueError("Unable to determine status of Docker container")

    def apply_resource_limits(self, container_args: dict, resources: ComputeResources | None) -> dict:
        """Apply resource limits from executor config to container arguments.

        Args:
            container_args: Container arguments dictionary to modify
            executor_config: The execution provider configuration

        Returns:
            Updated container arguments dictionary
        """
        if resources and resources.limits:
            limits = resources.limits
            if limits.memory is not None:
                # Convert Kubernetes memory format to Docker format
                memory_limit = limits.memory
                # Simple conversion - Docker expects format like "1g", "512m"
                if memory_limit.endswith("Gi"):
                    container_args["mem_limit"] = memory_limit.replace("Gi", "g")
                elif memory_limit.endswith("Mi"):
                    container_args["mem_limit"] = memory_limit.replace("Mi", "m")
                else:
                    container_args["mem_limit"] = memory_limit

            if limits.cpu is not None:
                cpu_limit = limits.cpu
                # Convert CPU format - Docker expects float/int
                if cpu_limit.endswith("m"):
                    # Convert millicores to cores
                    cpu_cores = int(float(cpu_limit[:-1]) / 1000)
                    container_args["cpu_count"] = cpu_cores
                else:
                    container_args["cpu_count"] = int(cpu_limit)

        return container_args

    def cleanup_steps(self):
        containers = self._client.containers.list(
            all=True,
            filters={"label": JOB_MANAGED_BY_LABEL},
            ignore_removed=True,
        )
        for container in containers:
            try:
                if container.labels.get(JOB_MANAGED_BY_LABEL) != JOB_MANAGED_BY_JOBS_CONTROLLER:
                    continue
                if container.labels.get(JOB_TYPE_LABEL) != JOB_TYPE_JOB:
                    continue
                if container.status in ("exited", "dead"):
                    exit_code = container.attrs.get("State", {}).get("ExitCode", 0)
                    job = self.get_label_from_container(container, JOB_ID_LABEL)
                    step_name = self.get_label_from_container(container, JOB_STEP_NAME_LABEL)
                    workspace = self.get_label_from_container(container, JOB_WORKSPACE_ID_LABEL)

                    # Verify the step is terminal before cleaning up.
                    # This prevents cleaning up resources that we last marked in active state,
                    # were prematurely cleaned up, and then sync active to error because the resource is gone.
                    if not self.check_step_is_terminal(job=job, step_name=step_name, workspace=workspace):
                        logger.debug("Skipping cleanup for for job container because step is not in terminal state")
                        continue

                    # Always disconnect the container from its network first if not already done.
                    # We do this to avoid dangling containers being connected to user-defined networks.
                    self.cleanup_container_network(container)

                    # Containers in terminal state can be cleaned up immediately if configured to do so
                    if (
                        self._execution_profile_config.cleanup_completed_jobs_immediately
                        and exit_code in TERMINAL_EXIT_CODES
                    ):
                        self.cleanup_single_container(container)
                        continue

                    # Otherwise, check if the TTL has expired for errored jobs or completed jobs if not cleaned up immediately
                    last_transition_time_str = container.attrs.get("State", {}).get("FinishedAt")
                    if last_transition_time_str and (
                        datetime.datetime.fromisoformat(last_transition_time_str)
                        + datetime.timedelta(seconds=self._execution_profile_config.ttl_seconds_after_finished)
                    ) < datetime.datetime.now(datetime.UTC):
                        self.cleanup_single_container(container)
            except NotFound:
                # Container may disappear between list and inspect/attribute access.
                # Ignore and continue cleanup for remaining containers.
                logger.debug("Container disappeared during cleanup loop; skipping")

    def cleanup_single_container(self, container: Container) -> None:
        """Cleanup a single container and its associated task storage volume."""
        workspace = self.get_label_from_container(container, JOB_WORKSPACE_ID_LABEL)
        job = self.get_label_from_container(container, JOB_ID_LABEL)
        task = self.get_label_from_container(container, JOB_TASK_ID_LABEL)
        exit_code = container.attrs.get("State", {}).get("ExitCode", 0)

        self.cleanup_container(container)
        logger.debug(
            "Cleaned up container",
            extra={"container_name": container.name, "workspace": workspace, "job": job, "task": task},
        )

        self.cleanup_task_storage_volumes(workspace, job, task)
        logger.debug("Cleaned up task storage volume", extra={"workspace": workspace, "job": job, "task": task})

        # Clean up persistent storage for successful jobs that used it
        # Only clean up if the job itself is in a terminal state to prevent premature cleanup
        if JOB_USES_PERSISTENT_STORAGE_LABEL in container.labels:
            uses_persistent_storage = (
                self.get_label_from_container(container, JOB_USES_PERSISTENT_STORAGE_LABEL) == "true"
            )
            if uses_persistent_storage and exit_code == 0:
                # Verify the job is in a terminal state before cleaning up persistent storage
                if self.check_job_is_terminal(job=job, workspace=workspace):
                    logger.debug(
                        "Cleaning up persistent storage for successful job", extra={"workspace": workspace, "job": job}
                    )
                    self.cleanup_job_persistent_storage(workspace, job)
                else:
                    logger.debug(
                        "Skipping persistent storage cleanup for job because it is not in terminal state yet",
                        extra={"workspace": workspace, "job": job},
                    )

    @abstractmethod
    def configure_container(self, container_args: dict, executor_config: ProviderT) -> dict:
        """Customize container arguments based on the execution provider.

        Args:
            container_args: Base container arguments dictionary
            executor_config: The execution provider configuration

        Returns:
            Updated container arguments dictionary
        """
        return container_args

    def name_for_step(self, step: PlatformJobStepWithContext) -> str:
        return f"{step.job}-{step.name}"


class CPUDockerJobBackend(DockerJobBackend[CPUExecutionProvider]):
    """Docker job backend for CPU execution."""

    def schedule(
        self,
        executor_config: CPUExecutionProvider,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        return self.schedule_single_container(executor_config, step)

    def sync(
        self,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        return self._sync(step)

    def configure_container(self, container_args: dict, executor_config: CPUExecutionProvider) -> dict:
        """Customize container arguments for CPU execution."""
        return self.apply_resource_limits(container_args, executor_config.resources)


class GPUDockerJobBackend(DockerJobBackend[GPUExecutionProvider]):
    """Docker job backend for GPU execution."""

    def init(self) -> None:
        super().init()
        # Get shared GPU pool from resource manager (shared with models service)
        # Pool is auto-detected from available GPUs on the system
        resource_manager = SharedResourceManager.get_instance()
        self.gpu_pool = resource_manager.get_gpu_pool()

        if self.gpu_pool is None:
            logger.warning(
                "No GPU pool available - no GPUs were detected on this system. "
                "GPU jobs will fail until GPUs are available."
            )

    def schedule(
        self,
        executor_config: GPUExecutionProvider,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        return self.schedule_single_container(executor_config, step)

    def sync(
        self,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate:
        job_update = self._sync(step)
        # Release GPU on any terminal state. Do not wait for cleanup_steps - that method
        # is called on the base class and has no visibility into the GPU pool!
        # Note: job_update.status may be a string or enum depending on code path
        terminal_states = {s.value for s in PlatformJobStatus.terminals()}
        status_value = (
            job_update.status.value if isinstance(job_update.status, PlatformJobStatus) else job_update.status
        )
        if self.gpu_pool is not None and status_value in terminal_states:
            self.gpu_pool.release_gpu(step.id)
        return job_update

    def configure_container(self, container_args: dict, executor_config: GPUExecutionProvider) -> dict:
        """Customize container arguments for GPU execution."""
        # Apply resource limits
        container_args = self.apply_resource_limits(container_args, executor_config.resources)

        if executor_config.resources is not None and executor_config.resources.num_gpus is not None:
            num_gpus = executor_config.resources.num_gpus
        else:
            num_gpus = 1

        shm = resolve_gpu_job_shm_size(executor_config.resources, None, num_gpus)
        container_args["shm_size"] = k8s_shm_quantity_to_docker(shm)

        # If no GPU pool is available (no GPUs detected), raise an error
        if self.gpu_pool is None:
            raise ResourceAllocationError(
                "No GPUs available on this system. GPU jobs require a system with NVIDIA GPUs."
            )

        # Allocate explicit device IDs from the pool to prevent conflicts
        # This will raise a GPUAllocationError if not enough GPUs are available.
        try:
            gpu_ids = self.gpu_pool.allocate_gpu(container_args["labels"][JOB_STEP_ID_LABEL], num_requested=num_gpus)
        except GPUAllocationError as e:
            raise ResourceAllocationError(str(e)) from e

        container_args["device_requests"] = [
            docker.types.DeviceRequest(
                driver="nvidia",
                device_ids=[str(gpu_id) for gpu_id in gpu_ids],
                capabilities=[["gpu"]],
            )
        ]

        return container_args
