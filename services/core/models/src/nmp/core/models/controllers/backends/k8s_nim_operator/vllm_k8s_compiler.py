# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Engine-agnostic compiler for directly-emitted Kubernetes objects.

For the k8s service backend's non-operator path, this module compiles the four
native Kubernetes objects a model deployment needs:

* ``V1PersistentVolumeClaim`` -- holds the model weights.
* ``V1Job`` -- weight puller (populates the PVC, then exits 0).
* ``V1Deployment`` -- the inference server (mounts the PVC, serves the model).
* ``V1Service`` -- ClusterIP exposing the server port for IGW routing.

The builders are intentionally **engine-agnostic**: every value the
k8s-nim-operator used to hardcode or derive (image, command/args, env,
securityContext, probes, resources, shared memory, service account, labels) is a
parameter the caller supplies. The vLLM path passes vLLM's values (via the shared
``vllm_compiler``); when NIM migrates onto this emission path it will pass NIM's
values through the same builders. Keep this module free of engine-specific logic.

These functions are pure (no Kubernetes I/O); the backend applies the returned
objects via the typed Kubernetes API clients.

FUTURE / NIM migration (dropping k8s-nim-operator -- see the Deployments Plugin
RFC):
    When NIM is cut over to emit these raw objects instead of NIMService/NIMCache
    CRs, route the NIM path through these same builders -- but DO NOT reuse vLLM's
    values. The footgun is the securityContext ``user_id`` / ``group_id`` params:
    they are engine-specific on purpose. The vLLM path passes
    ``default_vllm_user_id`` / ``default_vllm_group_id`` (2000/0) because that is
    the user the ``vllm/vllm-openai`` image ships with an ``/etc/passwd`` entry
    (an arbitrary uid like 1000 crashes torch/inductor's ``getpass.getuser()``).
    NIM images expect the operator's historical 1000/2000. So the NIM path must
    pass its own uid/gid (e.g. the existing ``default_user_id`` /
    ``default_group_id`` config, defaulting to the NIM-appropriate values) -- NOT
    the ``default_vllm_*`` fields. Same reasoning applies to image, args/command
    (NIM is env-configured; vLLM is arg-configured), and env. Pick per engine at
    the call site; never hardcode either engine's value in this module.
"""

from logging import getLogger
from typing import Optional

from kubernetes import client as k8s_client
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER

logger = getLogger(__name__)

# Label keys (shared with the operator path for orphan reconciliation / listing).
DEPLOYMENT_WORKSPACE_LABEL = "nmp.nvidia.com/deployment-workspace"
DEPLOYMENT_NAME_LABEL = "nmp.nvidia.com/deployment-name"
# Records the resolved model source on the PVC + Job so update can detect a change
# and decide whether to re-pull weights (see backend re-pull policy). This is an
# ANNOTATION, not a label: the value is "<ns>/<name>@<rev>" which contains '/'
# and ':' and is therefore not a valid label value.
MODEL_SOURCE_ANNOTATION = "nmp.nvidia.com/model-source"

# In-pod paths.
MODEL_STORE_PATH = "/model-store"
SCRATCH_PATH = "/scratch"
DSHM_PATH = "/dev/shm"

# Resource-name suffixes derived from the deployment resource name.
PVC_SUFFIX = "-pvc"
PULL_JOB_SUFFIX = "-pull"

# Defaults mirroring the k8s-nim-operator.
DEFAULT_BACKOFF_LIMIT = 5
DEFAULT_TTL_SECONDS_AFTER_FINISHED = 600
DEFAULT_USER_ID = 1000
DEFAULT_GROUP_ID = 2000
SERVER_PORT_NAME = "api"


def pvc_name(resource_name: str) -> str:
    """PVC name derived from the deployment resource name."""
    return f"{resource_name}{PVC_SUFFIX}"


def pull_job_name(resource_name: str) -> str:
    """Weight-puller Job name derived from the deployment resource name."""
    return f"{resource_name}{PULL_JOB_SUFFIX}"


def common_labels(
    workspace: str,
    name: str,
    engine: str,
    *,
    extra: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Labels stamped on every emitted object for management + orphan listing."""
    labels = {
        MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
        DEPLOYMENT_WORKSPACE_LABEL: workspace,
        DEPLOYMENT_NAME_LABEL: name,
        "nmp.nvidia.com/engine": engine,
    }
    if extra:
        labels.update(extra)
    return labels


def _merge_annotations(
    base: Optional[dict[str, str]],
    model_source: Optional[str],
) -> Optional[dict[str, str]]:
    """Merge caller annotations with the model-source annotation (re-pull marker)."""
    annotations = dict(base) if base else {}
    if model_source:
        annotations[MODEL_SOURCE_ANNOTATION] = model_source
    return annotations or None


def _gpu_resources(gpu: int) -> Optional[k8s_client.V1ResourceRequirements]:
    """GPU resource requirements (requests == limits). None when gpu == 0."""
    if gpu < 1:
        return None
    quantity = {"nvidia.com/gpu": str(gpu)}
    return k8s_client.V1ResourceRequirements(requests=dict(quantity), limits=dict(quantity))


def _pod_security_context(
    user_id: Optional[int],
    group_id: Optional[int],
) -> Optional[k8s_client.V1PodSecurityContext]:
    """Pod securityContext from explicitly-configured uid/gid only.

    Returns ``None`` when neither is set, so the pod runs as the container image's
    default user. We intentionally do NOT force the operator's 1000/2000 default:
    some images (e.g. vLLM) lack an ``/etc/passwd`` entry for uid 1000, which makes
    libraries that call ``getpass.getuser()`` (torch inductor) crash with
    ``getpwuid(): uid not found``. NIM can opt into a uid/gid via config.
    """
    if user_id is None and group_id is None:
        return None
    return k8s_client.V1PodSecurityContext(
        run_as_user=user_id,
        run_as_group=group_id,
        fs_group=group_id,
    )


def compile_pvc(
    *,
    resource_name: str,
    workspace: str,
    name: str,
    engine: str,
    disk_size: str,
    storage_class: Optional[str] = None,
    access_modes: Optional[list[str]] = None,
    model_source: Optional[str] = None,
    namespace: Optional[str] = None,
    annotations: Optional[dict[str, str]] = None,
) -> k8s_client.V1PersistentVolumeClaim:
    """Compile the model-weights PVC.

    ``access_modes`` defaults to ``["ReadWriteOnce"]`` (single-pod; the puller and
    server co-locate). ``model_source`` is stamped as an annotation so the
    backend's update path can detect a weight-source change and decide whether to
    re-pull.
    """
    return k8s_client.V1PersistentVolumeClaim(
        metadata=k8s_client.V1ObjectMeta(
            name=pvc_name(resource_name),
            namespace=namespace,
            labels=common_labels(workspace, name, engine),
            annotations=_merge_annotations(annotations, model_source),
        ),
        spec=k8s_client.V1PersistentVolumeClaimSpec(
            access_modes=access_modes or ["ReadWriteOnce"],
            resources=k8s_client.V1VolumeResourceRequirements(requests={"storage": disk_size}),
            storage_class_name=storage_class,
        ),
    )


def compile_puller_job(
    *,
    resource_name: str,
    workspace: str,
    name: str,
    engine: str,
    image: str,
    container_args: list[str],
    env: Optional[dict[str, str]] = None,
    gpu: int = 0,
    namespace: Optional[str] = None,
    service_account_name: Optional[str] = None,
    image_pull_secret: Optional[str] = None,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    model_source: Optional[str] = None,
    backoff_limit: int = DEFAULT_BACKOFF_LIMIT,
    ttl_seconds_after_finished: int = DEFAULT_TTL_SECONDS_AFTER_FINISHED,
    annotations: Optional[dict[str, str]] = None,
) -> k8s_client.V1Job:
    """Compile the weight-puller Job.

    Mirrors the docker puller: a single container running ``hf download <repo>
    --local-dir /model-store [...]`` against ``image`` (the platform nmp-api
    image), mounting the PVC at ``/model-store``. ``command=["hf"]`` overrides the
    image ENTRYPOINT (nmp-api's is ``nemo services run``) to the Hugging Face CLI,
    and ``container_args`` (e.g. ``["download", "<repo>", "--local-dir",
    "/model-store"]``) are the CLI arguments. The puller requests the same ``gpu``
    as the server --
    not for compute, but to pin it into GPU topology so the shared RWO PVC binds
    where the server can mount it (correct across any StorageClass
    ``volumeBindingMode``).
    """
    labels = common_labels(workspace, name, engine)
    job_annotations = _merge_annotations(annotations, model_source)

    env_list = [k8s_client.V1EnvVar(name=k, value=str(v)) for k, v in (env or {}).items()]

    container = k8s_client.V1Container(
        name="weight-puller",
        image=image,
        command=["hf"],
        args=container_args,
        env=env_list or None,
        resources=_gpu_resources(gpu),
        security_context=k8s_client.V1SecurityContext(
            allow_privilege_escalation=False,
            run_as_non_root=True,
            run_as_user=user_id if user_id is not None else DEFAULT_USER_ID,
            run_as_group=group_id if group_id is not None else DEFAULT_GROUP_ID,
            capabilities=k8s_client.V1Capabilities(drop=["ALL"]),
        ),
        volume_mounts=[
            k8s_client.V1VolumeMount(name="model-store", mount_path=MODEL_STORE_PATH),
        ],
    )

    # The puller writes to a freshly-provisioned PVC, so it needs fsGroup to own
    # the volume's filesystem (without it, a non-root puller can't create files at
    # the PVC root -> PermissionError on /model-store). Default to 1000/2000; the
    # nmp-api puller image runs as the 'nvs' user (uid/gid 1000).
    puller_security_context = k8s_client.V1PodSecurityContext(
        run_as_user=user_id if user_id is not None else DEFAULT_USER_ID,
        run_as_group=group_id if group_id is not None else DEFAULT_GROUP_ID,
        fs_group=group_id if group_id is not None else DEFAULT_GROUP_ID,
    )
    pod_spec = k8s_client.V1PodSpec(
        restart_policy="Never",
        service_account_name=service_account_name,
        security_context=puller_security_context,
        image_pull_secrets=([k8s_client.V1LocalObjectReference(name=image_pull_secret)] if image_pull_secret else None),
        containers=[container],
        volumes=[
            k8s_client.V1Volume(
                name="model-store",
                persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=pvc_name(resource_name),
                ),
            ),
        ],
    )

    return k8s_client.V1Job(
        metadata=k8s_client.V1ObjectMeta(
            name=pull_job_name(resource_name),
            namespace=namespace,
            labels=labels,
            annotations=job_annotations,
        ),
        spec=k8s_client.V1JobSpec(
            backoff_limit=backoff_limit,
            ttl_seconds_after_finished=ttl_seconds_after_finished,
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels=labels),
                spec=pod_spec,
            ),
        ),
    )


def _probe(health_path: str, port: int, *, failure_threshold: int, period_seconds: int = 10) -> k8s_client.V1Probe:
    return k8s_client.V1Probe(
        http_get=k8s_client.V1HTTPGetAction(path=health_path, port=port),
        period_seconds=period_seconds,
        timeout_seconds=5,
        failure_threshold=failure_threshold,
    )


def compile_deployment(
    *,
    resource_name: str,
    workspace: str,
    name: str,
    engine: str,
    image: str,
    args: list[str],
    health_path: str,
    port: int = 8000,
    env: Optional[dict[str, str]] = None,
    gpu: int = 0,
    namespace: Optional[str] = None,
    service_account_name: Optional[str] = None,
    image_pull_secret: Optional[str] = None,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    shared_memory_size_limit: Optional[str] = None,
    startup_grace_seconds: int = 600,
    init_containers: Optional[list[k8s_client.V1Container]] = None,
    sidecar_containers: Optional[list[k8s_client.V1Container]] = None,
    extra_labels: Optional[dict[str, str]] = None,
    mount_model_store: bool = True,
) -> k8s_client.V1Deployment:
    """Compile the inference-server Deployment.

    ``args`` is the server arg vector (e.g. from ``compile_vllm_args``), appended
    to the image's entrypoint; ``command`` is intentionally left unset so the
    upstream image entrypoint (``vllm serve``) runs. ``health_path`` drives the
    startup/readiness probes. A ``dshm`` emptyDir is always mounted at
    ``/dev/shm`` (vLLM uses it for tensor-parallel NCCL); ``scratch`` is mounted
    for the LoRA cache dir.

    ``mount_model_store`` controls whether the ``model-store`` PVC volume + mount
    are attached. The vLLM/NIM weight-pull paths set it ``True`` (the PVC holds
    the pulled weights). The ``generic`` engine pulls no weights and has no PVC,
    so it passes ``False`` -- the container runs purely from its image.
    """
    selector_labels = {"app": resource_name}
    pod_labels = {
        **selector_labels,
        **common_labels(workspace, name, engine),
    }
    if extra_labels:
        pod_labels.update(extra_labels)

    env_list = [k8s_client.V1EnvVar(name=k, value=str(v)) for k, v in (env or {}).items()]
    period = 10
    failure_threshold = max(1, -(-startup_grace_seconds // period))  # ceil

    volume_mounts = [
        k8s_client.V1VolumeMount(name="scratch", mount_path=SCRATCH_PATH),
        k8s_client.V1VolumeMount(name="dshm", mount_path=DSHM_PATH),
    ]
    if mount_model_store:
        volume_mounts.insert(
            0, k8s_client.V1VolumeMount(name="model-store", mount_path=MODEL_STORE_PATH, read_only=True)
        )

    container = k8s_client.V1Container(
        name=f"{resource_name}-ctr",
        image=image,
        args=args or None,
        env=env_list or None,
        ports=[k8s_client.V1ContainerPort(container_port=port, name=SERVER_PORT_NAME)],
        resources=_gpu_resources(gpu),
        startup_probe=_probe(health_path, port, failure_threshold=failure_threshold, period_seconds=period),
        readiness_probe=_probe(health_path, port, failure_threshold=3, period_seconds=period),
        volume_mounts=volume_mounts,
    )

    containers = [container]
    if sidecar_containers:
        containers.extend(sidecar_containers)

    volumes = [
        k8s_client.V1Volume(name="scratch", empty_dir=k8s_client.V1EmptyDirVolumeSource()),
        k8s_client.V1Volume(
            name="dshm",
            empty_dir=k8s_client.V1EmptyDirVolumeSource(medium="Memory", size_limit=shared_memory_size_limit),
        ),
    ]
    if mount_model_store:
        volumes.insert(
            0,
            k8s_client.V1Volume(
                name="model-store",
                persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=pvc_name(resource_name),
                    read_only=True,
                ),
            ),
        )

    pod_spec = k8s_client.V1PodSpec(
        service_account_name=service_account_name,
        security_context=_pod_security_context(user_id, group_id),
        image_pull_secrets=([k8s_client.V1LocalObjectReference(name=image_pull_secret)] if image_pull_secret else None),
        init_containers=init_containers or None,
        containers=containers,
        volumes=volumes,
    )

    return k8s_client.V1Deployment(
        metadata=k8s_client.V1ObjectMeta(
            name=resource_name,
            namespace=namespace,
            labels=common_labels(workspace, name, engine),
        ),
        spec=k8s_client.V1DeploymentSpec(
            replicas=1,
            selector=k8s_client.V1LabelSelector(match_labels=selector_labels),
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels=pod_labels),
                spec=pod_spec,
            ),
        ),
    )


def compile_service(
    *,
    resource_name: str,
    workspace: str,
    name: str,
    engine: str,
    port: int = 8000,
    namespace: Optional[str] = None,
) -> k8s_client.V1Service:
    """Compile the ClusterIP Service exposing the server port for IGW routing."""
    return k8s_client.V1Service(
        metadata=k8s_client.V1ObjectMeta(
            name=resource_name,
            namespace=namespace,
            labels=common_labels(workspace, name, engine),
        ),
        spec=k8s_client.V1ServiceSpec(
            type="ClusterIP",
            selector={"app": resource_name},
            ports=[
                k8s_client.V1ServicePort(
                    name=SERVER_PORT_NAME,
                    port=port,
                    target_port=SERVER_PORT_NAME,
                    protocol="TCP",
                ),
            ],
        ),
    )
