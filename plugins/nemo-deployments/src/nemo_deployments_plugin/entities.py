# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployment plugin entity definitions and supporting Pydantic types."""

from __future__ import annotations

from typing import Any, Literal

from nemo_deployments_plugin.constants import (
    ENTITY_TYPE_DEPLOYMENT,
    ENTITY_TYPE_DEPLOYMENT_CONFIG,
    ENTITY_TYPE_VOLUME,
)
from nemo_deployments_plugin.types import (
    AccessMode,
    DeploymentStatus,
    DesiredState,
    DriftRecoveryAction,
    Endpoint,
    PrerequisiteCondition,
    RestartPolicy,
    VolumeStatus,
)
from nemo_platform_plugin.entity import NemoEntity
from pydantic import BaseModel, Field, model_validator


class EnvVar(BaseModel):
    name: str
    value: str | None = None
    value_from: dict[str, Any] | None = Field(default=None, alias="valueFrom")

    model_config = {"populate_by_name": True}


class ContainerPort(BaseModel):
    name: str | None = None
    container_port: int = Field(alias="containerPort")
    protocol: Literal["TCP", "UDP"] = "TCP"

    model_config = {"populate_by_name": True}


class ResourceRequirements(BaseModel):
    limits: dict[str, str] = Field(default_factory=dict)
    requests: dict[str, str] = Field(default_factory=dict)


class VolumeMount(BaseModel):
    name: str
    mount_path: str = Field(alias="mountPath")
    read_only: bool = Field(default=False, alias="readOnly")
    sub_path: str | None = Field(default=None, alias="subPath")

    model_config = {"populate_by_name": True}


class ExecAction(BaseModel):
    command: list[str] = Field(default_factory=list)


class HTTPGetAction(BaseModel):
    path: str = "/"
    port: int | str = 8080
    scheme: Literal["HTTP", "HTTPS"] = "HTTP"


class TCPSocketAction(BaseModel):
    port: int | str


class Probe(BaseModel):
    exec_action: ExecAction | None = Field(default=None, alias="exec")
    http_get: HTTPGetAction | None = Field(default=None, alias="httpGet")
    tcp_socket: TCPSocketAction | None = Field(default=None, alias="tcpSocket")
    initial_delay_seconds: int = Field(default=0, alias="initialDelaySeconds")
    period_seconds: int = Field(default=10, alias="periodSeconds")
    timeout_seconds: int = Field(default=1, alias="timeoutSeconds")
    failure_threshold: int = Field(default=3, alias="failureThreshold")

    model_config = {"populate_by_name": True}


class Container(BaseModel):
    name: str
    image: str
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: list[EnvVar] = Field(default_factory=list)
    ports: list[ContainerPort] = Field(default_factory=list)
    resources: ResourceRequirements = Field(default_factory=ResourceRequirements)
    volume_mounts: list[VolumeMount] = Field(default_factory=list, alias="volumeMounts")
    liveness_probe: Probe | None = Field(default=None, alias="livenessProbe")
    readiness_probe: Probe | None = Field(default=None, alias="readinessProbe")

    model_config = {"populate_by_name": True}


class ConfigFile(BaseModel):
    path: str
    content: str
    mode: int = 0o644


class Toleration(BaseModel):
    key: str | None = None
    operator: Literal["Equal", "Exists"] = "Equal"
    value: str | None = None
    effect: Literal["NoSchedule", "PreferNoSchedule", "NoExecute"] | None = None
    toleration_seconds: int | None = Field(default=None, alias="tolerationSeconds")

    model_config = {"populate_by_name": True}


class LabelSelector(BaseModel):
    match_labels: dict[str, str] = Field(default_factory=dict, alias="matchLabels")

    model_config = {"populate_by_name": True}


class LocalObjectReference(BaseModel):
    name: str


class PodSecurityContext(BaseModel):
    run_as_user: int | None = Field(default=None, alias="runAsUser")
    run_as_group: int | None = Field(default=None, alias="runAsGroup")
    fs_group: int | None = Field(default=None, alias="fsGroup")

    model_config = {"populate_by_name": True}


class Affinity(BaseModel):
    node_affinity: dict[str, Any] | None = Field(default=None, alias="nodeAffinity")
    pod_affinity: dict[str, Any] | None = Field(default=None, alias="podAffinity")
    pod_anti_affinity: dict[str, Any] | None = Field(default=None, alias="podAntiAffinity")

    model_config = {"populate_by_name": True}


class DockerDeploymentConfig(BaseModel):
    port_range_start: int = 9000
    port_range_end: int = 9100
    network: str | None = None


class K8sDeploymentConfig(BaseModel):
    namespace: str | None = None
    service_account: str | None = Field(default=None, alias="serviceAccount")
    tolerations: list[Toleration] = Field(default_factory=list)
    affinity: Affinity | None = None
    security_context: PodSecurityContext | None = Field(default=None, alias="securityContext")

    model_config = {"populate_by_name": True}


class DeploymentBackendConfig(BaseModel):
    docker: DockerDeploymentConfig | None = None
    k8s: K8sDeploymentConfig | None = None


class DockerVolumeConfig(BaseModel):
    driver: str = "local"
    mount_point: str | None = None


class K8sVolumeConfig(BaseModel):
    storage_class: str | None = Field(default=None, alias="storageClass")
    namespace: str | None = None

    model_config = {"populate_by_name": True}


class VolumeBackendConfig(BaseModel):
    docker: DockerVolumeConfig | None = None
    k8s: K8sVolumeConfig | None = None


class DriftRecoveryPolicy(BaseModel):
    action: DriftRecoveryAction = "recreate"
    max_attempts: int | None = Field(
        default=None,
        ge=0,
        description="Override controller drift_recovery_max_attempts when set.",
    )
    initial_delay_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Override controller drift_recovery_initial_delay_seconds when set.",
    )
    max_delay_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Override controller drift_recovery_max_delay_seconds when set.",
    )

    @model_validator(mode="after")
    def _validate_delays(self) -> DriftRecoveryPolicy:
        if (
            self.initial_delay_seconds is not None
            and self.max_delay_seconds is not None
            and self.initial_delay_seconds > self.max_delay_seconds
        ):
            raise ValueError("initial_delay_seconds must not exceed max_delay_seconds")
        return self


class Prerequisite(BaseModel):
    deployment_name: str = Field(
        description=(
            "Name of another DeploymentConfig in the same workspace whose corresponding "
            "Deployment must satisfy condition before this deployment may start."
        ),
    )
    condition: PrerequisiteCondition = Field(
        default="succeeded",
        description=(
            "ready: prerequisite Deployment.status == READY. "
            "succeeded: prerequisite Deployment.status == SUCCEEDED with exit_code == 0."
        ),
    )


class StatusEvent(BaseModel):
    status: DeploymentStatus
    message: str = ""
    timestamp: str = ""


class DeploymentConfig(NemoEntity, entity_type=ENTITY_TYPE_DEPLOYMENT_CONFIG):
    """Immutable PodSpec-shaped deployment template."""

    containers: list[Container] = Field(default_factory=list)
    init_containers: list[Container] = Field(default_factory=list, alias="initContainers")
    volume_mounts: list[VolumeMount] = Field(default_factory=list, alias="volumeMounts")
    config_files: list[ConfigFile] = Field(default_factory=list, alias="configFiles")
    restart_policy: RestartPolicy = Field(default="Always", alias="restartPolicy")
    backoff_limit: int = Field(default=6, alias="backoffLimit")
    prerequisites: list[Prerequisite] = Field(default_factory=list)
    drift_recovery: DriftRecoveryPolicy = Field(default_factory=DriftRecoveryPolicy, alias="driftRecovery")
    labels: dict[str, str] = Field(default_factory=dict)
    backend_config: DeploymentBackendConfig = Field(default_factory=DeploymentBackendConfig, alias="backendConfig")

    model_config = {"populate_by_name": True}


class Deployment(NemoEntity, entity_type=ENTITY_TYPE_DEPLOYMENT):
    """Desired and observed deployment state."""

    deployment_config: str = Field(description="Name of the DeploymentConfig entity.")
    desired_state: DesiredState = Field(default="READY")
    executor: str | None = Field(
        default=None,
        description="Named executor registry entry; falls back to plugin default_executor.",
    )
    status: DeploymentStatus = Field(default="PENDING")
    status_message: str = Field(default="")
    endpoints: list[Endpoint] = Field(default_factory=list)
    exit_code: int | None = None
    error_details: dict[str, Any] | None = None
    status_history: list[StatusEvent] = Field(default_factory=list)

    # Reconciler (758) enforces restart_policy vs terminal status on DeploymentConfig:
    # Never → SUCCEEDED terminal; Always/OnFailure → READY while running.


class Volume(NemoEntity, entity_type=ENTITY_TYPE_VOLUME):
    """Persistent volume request and observed state."""

    size: str = Field(default="1Gi", description="Requested storage size (Kubernetes quantity).")
    access_modes: list[AccessMode] = Field(default_factory=lambda: ["ReadWriteOnce"])
    backend_config: VolumeBackendConfig = Field(default_factory=VolumeBackendConfig, alias="backendConfig")
    status: VolumeStatus = Field(default="PENDING")
    status_message: str = Field(default="")
    error_details: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}
