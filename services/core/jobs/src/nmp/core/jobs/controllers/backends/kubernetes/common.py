# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import logging
import os
import uuid
from typing import Any

from kubernetes import client, config
from kubernetes.client.models import V1Pod
from kubernetes.client.rest import ApiException
from nemo_platform import NeMoPlatform
from nmp.common.auth import AuthContext
from nmp.common.config import ImagePullSecret, get_platform_config
from nmp.common.jobs.constants import (
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
from nmp.core.jobs.api.v2.jobs.schemas import PlatformJobStepWithContext
from nmp.core.jobs.app.constants import (
    DEFAULT_VOLUME_PERMISSIONS_IMAGE,
    JOB_ATTEMPT_ID_LABEL,
    JOB_EXECUTION_BACKEND_LABEL,
    JOB_EXECUTION_PROFILE_LABEL,
    JOB_ID_LABEL,
    JOB_MANAGED_BY_JOBS_CONTROLLER,
    JOB_MANAGED_BY_LABEL,
    JOB_STEP_ID_LABEL,
    JOB_STEP_NAME_LABEL,
    JOB_TYPE_JOB,
    JOB_TYPE_LABEL,
    JOB_TYPE_STORAGE_CLEANUP,
    JOB_USES_PERSISTENT_STORAGE_LABEL,
    JOB_WORKSPACE_ID_LABEL,
    KUBE_JOB_SELECTOR_LABELS,
    NEMO_JOB_TASK_CONTAINER_NAME,
)
from nmp.core.jobs.app.providers import ComputeResources, ContainerSpec
from nmp.core.jobs.controllers.backends.base import (
    JobExecutionProfileConfig,
    get_logs_endpoint_from_fileset,
    resolve_gpu_job_shm_size,
    resolve_task_image,
)
from nmp.core.jobs.controllers.backends.exceptions import FailedToScheduleError, JobStorageError
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

TASK_STORAGE_VOLUME_NAME = "task-storage"
JOB_STORAGE_VOLUME_NAME = "job-storage"
STEP_CONFIG_VOLUME_NAME = "job-step-config"


class PodStatus(BaseModel):
    task_id: str
    name: str
    errors: dict[str, int]
    completed: set[str]
    active: set[str]
    waiting: dict[str, str]
    phase: str


_load_kubernetes_config_once = False


def load_kubernetes_config():
    """Load Kubernetes configuration, either from in-cluster config or kubeconfig file.
    This function is idempotent and will only load the configuration once.
    """
    global _load_kubernetes_config_once
    if _load_kubernetes_config_once:
        return

    try:
        # Try to load in-cluster config first (for when running in K8s)
        config.load_incluster_config()
    except config.ConfigException:
        # Fall back to kubeconfig file
        config.load_kube_config()

    _load_kubernetes_config_once = True


def get_namespace_from_environment() -> str:
    """
    Determine the namespace of the current controller pod.

    Returns:
        str: The namespace of the current pod

    Raises:
        RuntimeError: If the namespace cannot be determined
    """
    # Try to get from environment variable (often set in K8s deployments)
    namespace = os.getenv("POD_NAMESPACE")
    if namespace:
        logger.debug("Determined current namespace from POD_NAMESPACE env var", extra=dict(namespace=namespace))
        return namespace

    # If we get here, we couldn't determine the namespace
    raise RuntimeError("Unable to determine current namespace, POD_NAMESPACE environment variable not set.")


def build_image_pull_secrets(
    image_pull_secrets: list[ImagePullSecret],
) -> list[client.V1LocalObjectReference]:
    """Build Kubernetes image pull secrets from configuration."""
    global_image_pull_secrets = get_platform_config().image_pull_secrets

    # Merge the two lists, avoiding duplicates
    merged_secrets = {secret.name: secret for secret in global_image_pull_secrets}
    for secret in image_pull_secrets:
        merged_secrets[secret.name] = secret

    result = []
    for secret in list(merged_secrets.values()):
        result.append(client.V1LocalObjectReference(name=secret.name))
    return result


def build_resource_requirements(
    resources: ComputeResources | None, num_gpus: int | None
) -> client.V1ResourceRequirements:
    """Build Kubernetes resource requirements from executor config."""
    # Handle new Kubernetes resource structure if available
    resources_dict = {}
    if resources is not None:
        dump = resources.model_dump(exclude_none=True)
        # Not valid V1ResourceRequirements fields (jobs-specific extensions / scheduling hints)
        dump.pop("shm_size", None)
        dump.pop("num_nodes", None)
        dump.pop("num_gpus", None)
        resources_dict.update(dump)

    if num_gpus is not None:
        limits = resources_dict.get("limits", {})
        limits["nvidia.com/gpu"] = num_gpus
        resources_dict["limits"] = limits

    return load_from_dict(resources_dict, klass="V1ResourceRequirements")


def build_tolerations(
    tolerations: list[dict[str, Any]] | None, num_gpus: int | None = None
) -> list[client.V1Toleration]:
    """Build Kubernetes tolerations from configuration."""

    result = []
    if not tolerations:
        return result

    if num_gpus is not None and num_gpus > 0:
        has_nvidia_toleration = next(filter(lambda x: x["key"] == "nvidia.com/gpu", tolerations), None)
        if not has_nvidia_toleration:
            tolerations.append(
                {"key": "nvidia.com/gpu", "operator": "Equal", "value": "true", "effect": "NoSchedule"},
            )

    for toleration_dict in tolerations:
        try:
            toleration: client.V1Toleration = load_from_dict(toleration_dict, klass="V1Toleration")
            if toleration:
                result.append(toleration)
        except Exception as e:
            raise ValueError(f"Invalid affinity configuration: {e}") from e
    return result


def build_affinity(affinity: dict[str, Any] | None) -> client.V1Affinity:
    """Build Kubernetes affinity from configuration."""
    if not affinity:
        return client.V1Affinity()

    try:
        return load_from_dict(affinity, klass="V1Affinity")
    except Exception as e:
        raise ValueError(f"Invalid affinity configuration: {e}") from e


def build_pod_security_context(security_context: dict[str, Any] | None) -> client.V1PodSecurityContext | None:
    """Build Kubernetes pod security context from configuration."""
    if not security_context:
        return None

    try:
        return load_from_dict(security_context, klass="V1PodSecurityContext")
    except Exception as e:
        raise ValueError(f"Invalid security context configuration: {e}") from e


class KubernetesObjectMetadata(BaseModel):
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


def build_metadata(labels: dict[str, str] | None, metadata: KubernetesObjectMetadata | None) -> client.V1ObjectMeta:
    """Build Kubernetes metadata from configuration."""
    if not metadata:
        return client.V1ObjectMeta(labels=labels)

    merged_labels = copy.deepcopy(labels) if labels else {}

    # merge the labels with the provided metadata labels
    if metadata.labels:
        merged_labels.update(metadata.labels)

    return client.V1ObjectMeta(labels=merged_labels, annotations=metadata.annotations)


def map_pod_to_pod_status(pod: V1Pod) -> PodStatus:
    """Map Kubernetes job status to PodStatus."""
    statuses = (
        (pod.status.container_statuses or [])  # type: ignore
        + (pod.status.init_container_statuses or [])  # type: ignore
        + (pod.status.ephemeral_container_statuses or [])  # type: ignore
    )
    states = [(status.name, status.state) for status in statuses]

    status = PodStatus(
        name=pod.metadata.name,  # type: ignore
        errors={},
        completed=set(),
        active=set(),
        waiting={},
        phase=pod.status.phase,  # type: ignore
        task_id=f"task-{pod.metadata.uid}",  # type: ignore
    )

    for name, state in states:
        if state.running is not None:
            status.active.add(name)
        elif state.waiting is not None:
            if state.waiting.reason in [
                "ImagePullBackOff",
                "ErrImagePull",
                "InvalidImageName",
                "CreateContainerConfigError",
            ]:
                status.errors[name] = state.waiting.reason
            else:
                status.waiting[name] = "waiting"
        elif state.terminated is not None:
            if state.terminated.exit_code in TERMINAL_EXIT_CODES and state.terminated.reason != "Error":
                status.completed.add(name)
            else:
                status.errors[name] = state.terminated.exit_code

    logger.debug("errors %s", [name for name in status.errors.keys()])
    logger.debug("completed %s", [name for name in status.errors.keys()])
    logger.debug("active %s", [name for name in status.errors.keys()])
    logger.debug("waiting %s", [name for name in status.errors.keys()])
    return status


def map_pod_status_to_platform_status(pod_status: PodStatus) -> PlatformJobStatus:
    """Map Kubernetes job status to PlatformJobStatus."""

    if pod_status.phase == "Failed":
        return PlatformJobStatus.ERROR
    elif pod_status.phase == "Succeeded":
        return PlatformJobStatus.COMPLETED
    elif len(pod_status.active) > 0:
        return PlatformJobStatus.ACTIVE
    elif len(pod_status.waiting) > 0:
        return PlatformJobStatus.PENDING
    elif len(pod_status.errors) > 0:
        return PlatformJobStatus.ERROR
    elif len(pod_status.completed) > 0:
        return PlatformJobStatus.COMPLETED
    else:
        return PlatformJobStatus.PENDING


def aggregate_pod_statuses_for_job_step(pods: list[PodStatus]) -> tuple[PlatformJobStatus, dict[str, Any]]:
    """Combine per-pod platform statuses when the Job has no completion_time and no Running/Pending pods.

    Used when Kubernetes pod ``phase`` is not yet Running or Pending but container-level state may still
    indicate progress (for example, Succeeded pods before the Job controller sets ``completion_time``).

    Precedence:

    1. If any pod maps to ERROR → ERROR.
    2. Else if any pod maps to ACTIVE → ACTIVE (for example, phase not Running but containers still running).
    3. Else if every pod maps to COMPLETED → COMPLETED (batch Job ``completion_time`` may lag).
    4. Else → PENDING (Unknown phase, mixed states, and so on).

    Args:
        pods: Non-empty list of :class:`PodStatus` for pods selected for this step.

    Returns:
        Platform status and a detail dict for the step.

    Raises:
        ValueError: If ``pods`` is empty (callers should handle an empty list before aggregating).
    """
    if not pods:
        raise ValueError("aggregate_pod_statuses_for_job_step requires a non-empty pod list")

    per_pod = [map_pod_status_to_platform_status(p) for p in pods]
    if PlatformJobStatus.ERROR in per_pod:
        return PlatformJobStatus.ERROR, {"message": "Job has pods in error state, check tasks for error details"}
    if PlatformJobStatus.ACTIVE in per_pod:
        n_active = sum(1 for s in per_pod if s == PlatformJobStatus.ACTIVE)
        return PlatformJobStatus.ACTIVE, {
            "message": f"Job has active containers on {n_active}/{len(pods)} pod(s) (phase not Running)"
        }
    if all(s == PlatformJobStatus.COMPLETED for s in per_pod):
        return PlatformJobStatus.COMPLETED, {
            "message": "Job pods report success; batch Job completion_time not yet observed (transient)",
        }
    return PlatformJobStatus.PENDING, {
        "message": "Job status unclear from pod phases; reconciling on next sync",
    }


def list_pods_by_labels(core_v1: client.CoreV1Api, namespace: str, labels: dict[str, str]) -> list[V1Pod]:
    label_selector = ",".join([f"{k}={v}" for k, v in labels.items()])
    result = core_v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
    return result.items


def list_pod_status(core_v1: client.CoreV1Api, namespace: str, labels: dict[str, str]) -> list[PodStatus]:
    return [map_pod_to_pod_status(pod) for pod in list_pods_by_labels(core_v1, namespace, labels)]


def get_pod_details(core_v1: client.CoreV1Api, namespace: str, name: str) -> tuple[dict[str, Any], dict[str, str], str]:
    """Get details for pods associated with the step's k8s job."""
    try:
        # Get pods for this job
        pod: V1Pod = core_v1.read_namespaced_pod(
            namespace=namespace,  # type: ignore
            name=name,  # type: ignore
        )
        pod_info = {
            "name": pod.metadata.name,  # type: ignore
            "phase": pod.status.phase,  # type: ignore
            "conditions": [],
            "containers": [],
            "events": None,
        }
        error_details: dict[str, str] = {}
        error_stack = ""

        # Capture container statuses and conditions from status
        if pod.status:
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    pod_info["conditions"].append(
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message,
                        }
                    )
            if pod.status.container_statuses:
                for container_status in pod.status.container_statuses:
                    container_info = {
                        "name": container_status.name,
                        "ready": container_status.ready,
                        "restart_count": container_status.restart_count,
                    }
                    if container_status.state and container_status.state.terminated:
                        container_info["terminated"] = {
                            "exit_code": container_status.state.terminated.exit_code,
                            "reason": container_status.state.terminated.reason,
                            "message": container_status.state.terminated.message,
                        }
                        if container_info["terminated"]["exit_code"] != 0:
                            error_stack += f"Container {container_status.name} terminated with exit code {container_info['terminated']['exit_code']}: {container_info['terminated']['message']}\n"
                    pod_info["containers"].append(container_info)

        # Get pod events
        pod_info["events"] = get_pod_events(core_v1, pod)

        # Check events for Warning:InspectFailed and Failed conditions
        for event in pod_info["events"]:
            if event["type"] == "Warning":
                if event["reason"] == "InspectFailed":
                    error_details["inspect_failed"] = event["message"]
                elif event["reason"] == "Failed":
                    error_details["failed"] = event["message"]

        return pod_info, error_details, error_stack

    except ApiException as e:
        logger.exception(f"Failed to get details for pod {name}")
        return {"error": f"Failed to retrieve details: {str(e)}"}, {}, ""


def get_pod_events(core_v1: client.CoreV1Api, pod: V1Pod) -> list[dict[str, Any]]:
    """Get events related to a Kubernetes Pod."""
    pod_name = pod.metadata.name  # type: ignore
    pod_namespace = pod.metadata.namespace  # type: ignore
    try:
        events_list = core_v1.list_namespaced_event(
            namespace=pod_namespace,
            field_selector=f"involvedObject.kind=Pod,involvedObject.name={pod_name}",
        )
        events = []
        for event in events_list.items:
            events.append(
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "first_timestamp": str(event.first_timestamp),
                    "last_timestamp": str(event.last_timestamp),
                    "count": event.count,
                }
            )
        return events
    except ApiException:
        logger.exception(f"Failed to get events for pod {pod_name}")
        return []


def name_for_step(step: PlatformJobStepWithContext) -> str:
    """Generate a valid Kubernetes acceptable job name from the platform job step."""
    if not step.id:
        raise ValueError("Step is missing required ID field")

    # Kubernetes job names must be lowercase and contain only alphanumeric characters and dashes
    # They cannot start or end with a dash and must be 63 characters or less
    job_name = step.id.lower().replace("_", "-")

    # Ensure it doesn't start/end with a dash
    job_name = job_name.strip("-")

    # Truncate if too long
    if len(job_name) > 63:
        job_name = job_name[:63].rstrip("-")

    return job_name


def common_labels_for_step(step: PlatformJobStepWithContext) -> dict[str, str]:
    """Generate common labels for a job step."""
    labels = copy.deepcopy(KUBE_JOB_SELECTOR_LABELS)
    labels.update(
        {
            JOB_TYPE_LABEL: JOB_TYPE_JOB,
            JOB_WORKSPACE_ID_LABEL: step.workspace,
            JOB_ID_LABEL: step.job,
            JOB_ATTEMPT_ID_LABEL: step.attempt_id,
            JOB_STEP_NAME_LABEL: step.name,
            JOB_STEP_ID_LABEL: step.id,
            JOB_USES_PERSISTENT_STORAGE_LABEL: "false",
            JOB_MANAGED_BY_LABEL: JOB_MANAGED_BY_JOBS_CONTROLLER,
        }
    )

    # Check if this step uses persistent storage
    if step.step_spec.environment:
        for envvar in step.step_spec.environment:
            if envvar.name == PERSISTENT_JOB_STORAGE_PATH_ENVVAR and envvar.value:
                labels[JOB_USES_PERSISTENT_STORAGE_LABEL] = "true"
                break

    return labels


def create_configmap(core_v1: client.CoreV1Api, namespace: str, step: PlatformJobStepWithContext) -> str:
    """Create a ConfigMap to hold the job step config file."""
    configmap_name = name_for_step(step)
    config_data = {
        NEMO_JOB_STEP_CONFIG_FILE_NAME: json.dumps(step.step_spec.config),
    }
    configmap = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=configmap_name,
            labels=common_labels_for_step(step),
        ),
        data=config_data,
    )
    try:
        core_v1.create_namespaced_config_map(namespace=namespace, body=configmap)
        logger.debug(
            "Created Kubernetes ConfigMap for job step",
            extra=dict(configmap_name=configmap_name, job=step.job, step=step.name),
        )
    except ApiException as e:
        if e.status == 409:
            logger.debug(
                "Kubernetes ConfigMap already exists for job step",
                extra=dict(configmap_name=configmap_name, job=step.job, step=step.name),
            )
        else:
            raise FailedToScheduleError(
                f"Failed to create Kubernetes ConfigMap {configmap_name} for job step {step.job}/{step.name}: {e}"
            ) from e

    return configmap_name


def delete_configmap(core_v1: client.CoreV1Api, namespace: str, name: str) -> None:
    """Delete the ConfigMap associated with the job step.

    Only deletes the ConfigMap if it is managed by the jobs controller
    (has label JOB_MANAGED_BY_LABEL=JOB_MANAGED_BY_JOBS_CONTROLLER). This avoids
    deleting ConfigMaps created by other controllers or users.
    """
    try:
        cm = core_v1.read_namespaced_config_map(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            logger.warning(
                "ConfigMap not found when attempting deletion (may already be deleted)",
                extra=dict(configmap_name=name, namespace=namespace),
            )
            return
        raise e

    metadata = getattr(cm, "metadata", None)
    labels = getattr(metadata, "labels", None)
    labels = labels or {}
    if labels.get(JOB_MANAGED_BY_LABEL) != JOB_MANAGED_BY_JOBS_CONTROLLER:
        logger.warning(
            "Skipping ConfigMap deletion: not managed by jobs-controller",
            extra=dict(configmap_name=name, namespace=namespace),
        )
        return

    try:
        core_v1.delete_namespaced_config_map(name=name, namespace=namespace)
        logger.info("Deleted Kubernetes ConfigMap", extra=dict(configmap_name=name, namespace=namespace))
    except ApiException as e:
        if e.status == 404:
            logger.warning("ConfigMap already deleted", extra=dict(configmap_name=name, namespace=namespace))
            return
        raise e


def load_from_dict(data: dict, klass: str):
    """
    Convert a dictionary containing kubernetes config to a deserialized object

    Input:
    data: a dictionary holding a valid kubernetes object
    klass: class literal for deserialized object, or string of class name.
    """

    class RespMock:
        """
        A dummy class to mock RESTResponse object
        """

        data: str | None

        def __init__(self, *args):
            self.data = None

    # Mock api response from dict
    resp_mock = RespMock()
    resp_mock.data = json.dumps(data)

    # Infer response_type from json data when not provided
    api_client = client.api_client.ApiClient()  # type: ignore
    obj = api_client.deserialize(response=resp_mock, response_type=klass)

    return obj


class KubernetesPersistentVolumeClaim(BaseModel):
    """Kubernetes Persistent Volume Claim definition."""

    claim_name: str = Field(description="Persistent Volume Claim Name")
    read_only: bool = Field(default=False, description="Whether the volume is mounted read-only")


class KubernetesEmptyDirVolume(BaseModel):
    """Kubernetes EmptyDir Volume definition."""

    medium: str | None = Field(default=None, description="The medium of the emptyDir volume (e.g., 'Memory')")
    size_limit: str | None = Field(default=None, description="The size limit of the emptyDir volume (e.g., '1Gi')")


class KubernetesVolume(BaseModel):
    """Kubernetes Volume definition."""

    name: str = Field(description="Volume Name")
    persistent_volume_claim: KubernetesPersistentVolumeClaim | None = Field(
        default=None, description="Persistent Volume Claim configuration"
    )
    empty_dir: KubernetesEmptyDirVolume | None = Field(default=None, description="EmptyDir Volume configuration")

    @model_validator(mode="after")
    def validate_self(self):
        """Ensure that exactly one volume source is specified."""
        if sum(source is not None for source in [self.persistent_volume_claim, self.empty_dir]) != 1:
            raise ValueError("Exactly one of 'persistent_volume_claim' or 'empty_dir' must be specified.")
        return self

    def to_k8s(self) -> client.V1Volume:
        """Convert to Kubernetes V1Volume object."""
        volume = client.V1Volume(name=self.name)
        if self.persistent_volume_claim:
            volume.persistent_volume_claim = client.V1PersistentVolumeClaimVolumeSource(
                claim_name=self.persistent_volume_claim.claim_name,
                read_only=self.persistent_volume_claim.read_only,
            )
        if self.empty_dir:
            volume.empty_dir = client.V1EmptyDirVolumeSource(
                medium=self.empty_dir.medium,
                size_limit=self.empty_dir.size_limit,
            )
        return volume


class KubernetesVolumeMount(BaseModel):
    """Kubernetes Volume Mount definition."""

    name: str = Field(description="Volume Name")
    mount_path: str = Field(description="Mount Path in the container")
    sub_path: str | None = Field(default=None, description="Sub-path within the volume to mount")
    read_only: bool = Field(default=False, description="Whether the volume mount is read-only")

    def to_k8s(self) -> client.V1VolumeMount:
        """Convert to Kubernetes V1VolumeMount object."""
        return client.V1VolumeMount(
            name=self.name,
            mount_path=self.mount_path,
            sub_path=self.sub_path,
            read_only=self.read_only,
        )


class KubernetesJobStorageConfig(BaseModel):
    """Configuration for persistent storage in Kubernetes jobs."""

    pvc_name: str = Field(default="", description="Persistent Volume Claim Name to use for job storage.")
    volume_permissions_image: str = Field(
        default=DEFAULT_VOLUME_PERMISSIONS_IMAGE, description="Image used to set volume permissions"
    )
    additional_volumes: list[KubernetesVolume] = Field(default_factory=list, description="Additional volumes to mount")
    additional_volume_mounts: list[KubernetesVolumeMount] = Field(
        default_factory=list, description="Additional volume mounts"
    )


class BaseKubernetesExecutionProfileConfig(JobExecutionProfileConfig):
    """Common configuration for Kubernetes execution environment."""

    namespace: str | None = Field(
        default=None,
        description="Kubernetes namespace to submit the job to. If not set, it will be determined from the environment.",
    )

    service_account_name: str = Field(
        default="default",
        description="Kubernetes service account name for job pods. Uses the Kubernetes default service account when set to 'default'.",
    )

    # Scheduling and resource configuration
    tolerations: list[dict[str, Any]] = Field(
        default_factory=list, description="Tolerations for the Kubernetes job pods."
    )
    node_selector: dict[str, str] = Field(
        default_factory=dict, description="Node selector for the Kubernetes job pods."
    )
    affinity: dict[str, Any] = Field(default_factory=dict, description="Affinity for the Kubernetes job pods.")
    resources: ComputeResources = Field(
        default_factory=ComputeResources, description="Resource requests and limits for the Kubernetes job pods."
    )
    pod_security_context: dict[str, Any] = Field(
        default_factory=dict, description="Pod security context for the Kubernetes job pods."
    )

    # Image pull secrets
    image_pull_secrets: list[ImagePullSecret] = Field(
        default_factory=list, description="Image pull secrets for the Kubernetes job pods."
    )

    # Optional metadata to add to each job object
    job_metadata: KubernetesObjectMetadata = Field(
        default_factory=KubernetesObjectMetadata,
        description="Metadata to add to each job object in the Kubernetes job.",
    )

    # Optional metadata to add to each pod in the job
    pod_metadata: KubernetesObjectMetadata = Field(
        default_factory=KubernetesObjectMetadata, description="Metadata to add to each pod in the Kubernetes job."
    )

    # Storage configurations for the job
    storage: KubernetesJobStorageConfig = Field(
        default_factory=KubernetesJobStorageConfig, description="Storage configuration for the Kubernetes job pods."
    )

    num_gpus: int = Field(default=1, description="Number of GPUs to request for the job")

    scheduler_name: str = Field(
        default="",
        description="The scheduler name to use for the pod spec. When non-empty, this value is applied to the pod's schedulerName field, enabling custom schedulers such as KAI Scheduler. Empty string omits schedulerName so the cluster default scheduler is used.",
    )

    launcher_image: str = Field(
        default="nvcr.io/nvidia/nemo-microservices/jobs-launcher:latest",
        description="Container image that contains the jobs-launcher binary.",
    )


# This is the name of the shared volume used to inject the launcher binary into the main job container
LAUNCHER_VOLUME_NAME = "launcher"

# Memory-backed emptyDir mounted at /dev/shm for GPU jobs (larger than the default 64Mi tmpfs)
JOB_DSHM_VOLUME_NAME = "dshm"

# This is the path where the launcher volume is mounted inside the init and job containers
LAUNCHER_MOUNT_PATH = "/launcher"

# This is the path to where we want the launcher to be mounted inside the job container
MOUNTED_LAUNCHER_BINARY_PATH = f"{LAUNCHER_MOUNT_PATH}/jobs-launcher"

# This is the command used to run the launcher within the job container
MOUNTED_LAUNCHER_RUN_COMMAND = [MOUNTED_LAUNCHER_BINARY_PATH, "run"]


def build_launcher_init_container(launcher_image: str, launcher_tool_path: str) -> client.V1Container:
    """
    Creates an init container that injects the launcher script into a shared volume.
    """
    return client.V1Container(
        name="launcher-injector",
        image=launcher_image,
        # This is the command used to run the launcher in the init container to copy the launcher binary
        # to the shared volume
        command=[launcher_tool_path, "init"],
        args=["-s", launcher_tool_path, "-d", MOUNTED_LAUNCHER_BINARY_PATH],
        volume_mounts=[client.V1VolumeMount(name=LAUNCHER_VOLUME_NAME, mount_path=LAUNCHER_MOUNT_PATH)],
    )


def build_permissions_init_container(
    volume_name: str, workspace: str, job_id: str, permissions_image: str
) -> client.V1Container:
    """
    Creates an init container that creates the job's subpath on the PVC and sets
    permissions so a non-root user can read/write files.

    Kubernetes does not create subPath directories automatically; the path must exist
    before the main container's volumeMount with subPath can be used. This container
    mounts the full volume, creates the directory, and chmods it in one shot.
    """
    volume_subpath = f"jobs/{workspace}/{job_id}"
    return client.V1Container(
        name="fix-permissions",
        image=permissions_image,
        command=["sh", "-c", f"mkdir -p /vol/{volume_subpath} && chmod -R 777 /vol/{volume_subpath}"],
        volume_mounts=[client.V1VolumeMount(name=volume_name, mount_path="/vol")],
    )


def ensure_job_storage(namespace: str, core_v1: client.CoreV1Api, pvc_name: str, workspace: str, job_id: str):
    """Ensure the persistent volume claim exists for a given job"""
    try:
        core_v1.read_namespaced_persistent_volume_claim(name=pvc_name, namespace=namespace)
        logger.debug(
            "Persistent volume claim created for job.", extra=dict(pvc_name=pvc_name, job=f"{workspace}/{job_id}")
        )
    except ApiException as e:
        raise JobStorageError(
            f"Failed to assert the validity of the persistent volume claim {pvc_name}. This may be caused by an issue talking to the Kubernetes API; see the stack trace for more details."
        ) from e


def cleanup_job_persistent_storage(
    namespace: str,
    batch_v1: client.BatchV1Api,
    pvc_name: str,
    workspace: str,
    job_id: str,
    step_name: str,
    permissions_image: str,
    execution_backend: str,
    execution_profile: str,
    job_metadata: KubernetesObjectMetadata,
    pod_metadata: KubernetesObjectMetadata,
    pod_security_context: dict[str, Any] | None = None,
) -> None:
    """
    Create a Kubernetes Job to clean up persistent storage for a completed job.

    Labels are built from the same execution profile the job was submitted with (including
    backend name, profile name, and profile-specific job/pod metadata such as Istio sidecar settings).

    Args:
        namespace: Kubernetes namespace
        batch_v1: BatchV1Api instance for creating Jobs
        pvc_name: Name of the PersistentVolumeClaim
        workspace: Workspace ID
        job_id: Job ID
        step_name: Step ID
        permissions_image: Docker image to use for the cleanup job
        execution_backend: Backend that ran the job (e.g. kubernetes_job, volcano_job).
        execution_profile: Execution profile name (e.g. default, a100) that ran the job.
        job_metadata: Optional metadata (labels/annotations) to merge onto the cleanup Job.
        pod_metadata: Optional metadata (labels/annotations) to merge onto the cleanup Job's pod template.
        pod_security_context: Same pod security context as workload jobs (runAsUser/fsGroup, etc.) so cleanup
            can remove files on NFS and similar storage where the workload user owns the data.
    """
    job_storage_subpath = f"jobs/{workspace}/{job_id}"
    cleanup_job_name = f"cleanup-{workspace}-{job_id}-{uuid.uuid4().hex[:8]}"[:63].rstrip("-")

    # Use same common labels as regular jobs (app, managed-by, backend, profile) plus cleanup-specific labels
    cleanup_common_labels = copy.deepcopy(KUBE_JOB_SELECTOR_LABELS)
    cleanup_common_labels.update(
        {
            JOB_TYPE_LABEL: JOB_TYPE_STORAGE_CLEANUP,
            JOB_WORKSPACE_ID_LABEL: workspace,
            JOB_ID_LABEL: job_id,
            JOB_STEP_NAME_LABEL: step_name,
            JOB_EXECUTION_BACKEND_LABEL: execution_backend,
            JOB_EXECUTION_PROFILE_LABEL: execution_profile,
        }
    )

    job_meta = build_metadata(cleanup_common_labels, job_metadata)
    job_meta.name = cleanup_job_name  # type: ignore[assignment]
    job_meta.namespace = namespace  # type: ignore[assignment]

    pod_meta = build_metadata(cleanup_common_labels, pod_metadata)

    # Create a Job that removes the job's storage directory
    cleanup_job = client.V1Job(
        metadata=job_meta,
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=300,  # Auto-delete cleanup job after 5 minutes
            backoff_limit=3,
            template=client.V1PodTemplateSpec(
                metadata=pod_meta,
                spec=client.V1PodSpec(
                    restart_policy="OnFailure",
                    security_context=build_pod_security_context(pod_security_context),
                    containers=[
                        client.V1Container(
                            name="cleanup",
                            image=permissions_image,
                            command=["sh", "-c"],
                            args=[
                                f"""
set -ex
# Remove the job's storage directory
if [ -d "/vol/{job_storage_subpath}" ]; then
    rm -rf "/vol/{job_storage_subpath}"
    echo "Removed persistent storage for job {workspace}/{job_id}"
else
    echo "Storage directory not found, may have been already cleaned up"
fi
"""
                            ],
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="job-storage",
                                    mount_path="/vol",
                                )
                            ],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="job-storage",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=pvc_name,
                                read_only=False,
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    try:
        batch_v1.create_namespaced_job(namespace=namespace, body=cleanup_job)
        logger.info(
            "Created persistent storage cleanup job",
            extra=dict(cleanup_job_name=cleanup_job_name, job=f"{workspace}/{job_id}"),
        )
    except ApiException as e:
        logger.error(
            "Failed to create persistent storage cleanup job",
            extra=dict(job=f"{workspace}/{job_id}", error=e),
            exc_info=True,
        )


def build_event_field_selector(kind: str, api_version: str, name: str = "") -> str:
    """Build a field selector string for Kubernetes events."""
    selector = f"involvedObject.kind={kind},involvedObject.apiVersion={api_version}"
    if name:
        selector += f",involvedObject.name={name}"
    return selector


def create_pod_template_spec(
    step: PlatformJobStepWithContext,
    namespace: str,
    container: ContainerSpec,
    common_labels: dict[str, str],
    secret_env_var_str: str,
    configmap_name: str,
    config: BaseKubernetesExecutionProfileConfig,
    core_v1: client.CoreV1Api,
    num_gpus: int | None = None,
    executor_resources: ComputeResources | None = None,
) -> client.V1PodTemplateSpec:
    """
    Create a V1PodTemplateSpec for the given job step and container.

    Args:
        step: The job step context.
        namespace: The Kubernetes namespace to create the pod in.
        container: The container specification for the main job container.
        common_labels: Common labels to apply to the pod.
        config: Execution provider config
        secret_env_var_str: Serialized secret environment variable mappings.
        core_v1: CoreV1Api instance for Kubernetes API interactions.
        num_gpus: Number of GPUs required by the job.
        executor_resources: Step-level resource block (e.g. GPU executor); used with profile resources for shm_size.
    Returns:
        A configured V1PodTemplateSpec object.
    """

    platform_config = get_platform_config()

    # Profile-level env vars first (e.g. HOME=/tmp); system, step, and shared env override these
    env = [client.V1EnvVar(name=name, value=value) for name, value in config.env.items()]
    env.extend(
        [
            client.V1EnvVar(name=NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, value=DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH),
            client.V1EnvVar(name=NEMO_JOB_ID_ENVVAR, value=step.job),
            client.V1EnvVar(name=NEMO_JOB_ATTEMPT_ID_ENVVAR, value=step.attempt_id),
            client.V1EnvVar(name=NEMO_JOB_STEP_ENVVAR, value=step.name),
            client.V1EnvVar(name=NEMO_JOB_WORKSPACE_ENVVAR, value=step.workspace),
            client.V1EnvVar(name=NEMO_JOB_FILESET_ENVVAR, value=step.fileset),
            client.V1EnvVar(
                name=NEMO_JOB_TASK_ENVVAR,
                value_from=client.V1EnvVarSource(field_ref=client.V1ObjectFieldSelector(field_path="metadata.uid")),
            ),
            client.V1EnvVar(name=EPHEMERAL_TASK_STORAGE_PATH_ENVVAR, value=DEFAULT_TASK_STORAGE_PATH),
            client.V1EnvVar(
                name="OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
                value=get_logs_endpoint_from_fileset(
                    platform_config,
                    step.workspace,
                    step.fileset,
                ),
            ),
            client.V1EnvVar(name="OTEL_LOGS_EXPORTER", value="otlp"),
            client.V1EnvVar(name="OTEL_SERVICE_NAME", value="nmp-job-task"),
            client.V1EnvVar(name=NEMO_JOB_SECRETS_ENVVAR, value=secret_env_var_str),
        ]
    )

    # Set auth context env var for job containers to make authenticated API calls
    if step.auth_context:
        sdk_auth_context = step.auth_context
        auth_context = AuthContext.model_validate(sdk_auth_context.model_dump(mode="python", exclude_none=True))
        principal = auth_context.to_principal()
        env_var_dict = principal.get_env_var()
        for name, value in env_var_dict.items():
            env.append(client.V1EnvVar(name=name, value=value))
        # Also set OTLP headers for telemetry (logs) to be authenticated
        env.append(client.V1EnvVar(name="OTEL_EXPORTER_OTLP_LOGS_HEADERS", value=principal.get_otlp_headers_value()))

    # Thread through shared platform envvars to the job
    shared_envvars = platform_config.to_shared_envvars()
    env.extend([client.V1EnvVar(name=name, value=value) for name, value in shared_envvars.items()])

    job_storage_mount = ""
    task_storage_mount = DEFAULT_TASK_STORAGE_PATH
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

                env.append(client.V1EnvVar(name=envvar.name, value=str(envvar.value)))

    # Prepare volume mounts
    volume_mounts = [
        client.V1VolumeMount(name=TASK_STORAGE_VOLUME_NAME, mount_path=task_storage_mount),
        client.V1VolumeMount(name=LAUNCHER_VOLUME_NAME, mount_path=LAUNCHER_MOUNT_PATH),
        client.V1VolumeMount(
            name=STEP_CONFIG_VOLUME_NAME,
            mount_path=DEFAULT_CONFIG_STORAGE_PATH,
        ),
    ]
    storage_config = config.storage
    if storage_config.additional_volume_mounts:
        volume_mounts.extend(mount.to_k8s() for mount in storage_config.additional_volume_mounts)

    # Prepare volumes
    volumes = [
        client.V1Volume(name=TASK_STORAGE_VOLUME_NAME, empty_dir=client.V1EmptyDirVolumeSource()),
        client.V1Volume(name=LAUNCHER_VOLUME_NAME, empty_dir=client.V1EmptyDirVolumeSource()),
        client.V1Volume(name=STEP_CONFIG_VOLUME_NAME, config_map=client.V1ConfigMapVolumeSource(name=configmap_name)),
    ]
    if storage_config.additional_volumes:
        volumes.extend(vol.to_k8s() for vol in storage_config.additional_volumes)

    if num_gpus is not None and num_gpus > 0:
        shm_size = resolve_gpu_job_shm_size(executor_resources, config.resources, num_gpus)
        volume_mounts.append(
            client.V1VolumeMount(name=JOB_DSHM_VOLUME_NAME, mount_path="/dev/shm"),
        )
        volumes.append(
            client.V1Volume(
                name=JOB_DSHM_VOLUME_NAME,
                empty_dir=client.V1EmptyDirVolumeSource(medium="Memory", size_limit=shm_size),
            ),
        )
        logger.debug(
            "Injected /dev/shm emptyDir for GPU job step",
            extra={"shm_size": shm_size, "num_gpus": num_gpus, "job": step.job, "step": step.name},
        )

    # Prepare init containers
    init_containers = [build_launcher_init_container(config.launcher_image, config.launcher_tool_path)]

    # If job storage is requested, add the volume, volume mount and the permissions init container for job storage.
    if job_storage_mount != "":
        if storage_config is None:
            raise JobStorageError(
                "Job step requests persistent job storage path, but no storage configuration was provided."
            )

        if storage_config.pvc_name == "":
            raise JobStorageError(
                "Job step requests persistent job storage path, but storage configuration is missing pvc_name configuration."
            )

        ensure_job_storage(
            namespace=namespace,
            core_v1=core_v1,
            pvc_name=storage_config.pvc_name,
            workspace=step.workspace,
            job_id=step.job,
        )
        job_storage_subpath = f"jobs/{step.workspace}/{step.job}"
        volume_mounts.append(
            client.V1VolumeMount(
                name=JOB_STORAGE_VOLUME_NAME, mount_path=job_storage_mount, sub_path=job_storage_subpath
            )
        )
        volumes.append(
            client.V1Volume(
                name=JOB_STORAGE_VOLUME_NAME,
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=storage_config.pvc_name,
                    read_only=False,
                ),
            )
        )
        init_containers.append(
            build_permissions_init_container(
                volume_name=JOB_STORAGE_VOLUME_NAME,
                workspace=step.workspace,
                job_id=step.job,
                permissions_image=storage_config.volume_permissions_image,
            ),
        )

    # Construct the container entrypoint and args
    # to be fed to the launcher script
    command = copy.deepcopy(MOUNTED_LAUNCHER_RUN_COMMAND)

    # Add the "--" separator between launcher args and container entrypoint
    # to indicate that all subsequent args are for the container and are considered positional args
    # when computed by the launcher.
    # See also: https://unix.stackexchange.com/questions/11376/what-does-double-dash-double-hyphen-mean
    # The launcher will pass these args directly to the container as-is, which may interpret them as either
    # positional or flags depending on the container design.
    command.append("--")

    # Now insert the container entrypoint commands.
    # Any container arguments will be passed as args to the container below.
    for cmd in container.entrypoint or []:
        command.append(cmd)

    # Resolve the task image: explicit container.image takes precedence,
    # then the profile's default_task_image, then platform CPU tasks image fallback.
    task_image = resolve_task_image(container.image, config.default_task_image)

    # Main job container
    job_container = client.V1Container(
        name=NEMO_JOB_TASK_CONTAINER_NAME,
        image=task_image,
        command=command,
        args=container.command,
        env=env,
        resources=build_resource_requirements(config.resources, num_gpus=num_gpus),
        volume_mounts=volume_mounts,
        # This ensures that when a container fails, we get the last few lines of logs in the pod status.
        # See https://kubernetes.io/docs/tasks/debug/debug-application/determine-reason-pod-failure/#customizing-the-termination-message
        termination_message_policy="FallbackToLogsOnError",
    )

    # Build pod spec kwargs; service_account_name is always set (defaults to "default")
    pod_spec_kwargs: dict[str, Any] = {
        "init_containers": init_containers,
        "containers": [job_container],
        "volumes": volumes,
        "restart_policy": "Never",
        "active_deadline_seconds": config.ttl_seconds_active,
        "tolerations": build_tolerations(config.tolerations, num_gpus=num_gpus),
        "node_selector": config.node_selector or {},
        "affinity": build_affinity(config.affinity),
        "image_pull_secrets": [
            client.V1LocalObjectReference(name=secret.name)
            for secret in (build_image_pull_secrets(config.image_pull_secrets) or [])
        ],
        "security_context": build_pod_security_context(config.pod_security_context),
        "service_account_name": config.service_account_name,
    }
    if config.scheduler_name:
        pod_spec_kwargs["scheduler_name"] = config.scheduler_name

    # Create pod template spec with native sidecar container
    pod_template = client.V1PodTemplateSpec(
        metadata=build_metadata(
            labels=common_labels,
            metadata=config.pod_metadata,
        ),
        spec=client.V1PodSpec(**pod_spec_kwargs),
    )

    return pod_template


def update_all_tasks(
    nmp_sdk: NeMoPlatform,
    core_v1: client.CoreV1Api,
    namespace: str,
    step: PlatformJobStepWithContext,
) -> bool:
    pod_statuses = list_pod_status(core_v1, namespace, common_labels_for_step(step))

    has_errors = False

    for pod_status in pod_statuses:
        status_details, error_details, error_stack = get_pod_details(core_v1, namespace, pod_status.name)

        # If we have error details from pod events or container statuses, mark the status as ERROR.
        if error_details:
            status = PlatformJobStatus.ERROR
        else:
            status = map_pod_status_to_platform_status(pod_status)

        if status == PlatformJobStatus.ERROR:
            if not has_errors:
                has_errors = True
            error_details["message"] = f"Pod {pod_status.name} is in error state"

        # Upsert the task against the Jobs API.
        nmp_sdk.jobs.tasks.create_or_update(
            pod_status.task_id,
            workspace=step.workspace,
            job=step.job,
            step=step.name,
            status=status.value,
            status_details=status_details,
            error_details=error_details,  # type: ignore
            error_stack=error_stack,
        )
        logger.info(f"updated task '{pod_status.task_id}'")

    return has_errors
