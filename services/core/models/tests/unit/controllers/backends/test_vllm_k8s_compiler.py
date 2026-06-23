# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the engine-agnostic k8s object compiler (vLLM raw-object path)."""

from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.k8s_nim_operator import vllm_k8s_compiler as c

# ---------------------------------------------------------------------------
# Naming + labels
# ---------------------------------------------------------------------------


def test_resource_name_suffixes():
    assert c.pvc_name("md-default-qwen") == "md-default-qwen-pvc"
    assert c.pull_job_name("md-default-qwen") == "md-default-qwen-pull"


def test_common_labels():
    labels = c.common_labels("default", "qwen", "vllm")
    assert labels[MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
    assert labels[c.DEPLOYMENT_WORKSPACE_LABEL] == "default"
    assert labels[c.DEPLOYMENT_NAME_LABEL] == "qwen"
    assert labels["nmp.nvidia.com/engine"] == "vllm"


# ---------------------------------------------------------------------------
# PVC
# ---------------------------------------------------------------------------


def test_compile_pvc_basic():
    pvc = c.compile_pvc(
        resource_name="md-default-qwen",
        workspace="default",
        name="qwen",
        engine="vllm",
        disk_size="50Gi",
        namespace="nemo",
    )
    assert pvc.metadata.name == "md-default-qwen-pvc"
    assert pvc.metadata.namespace == "nemo"
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests["storage"] == "50Gi"
    assert pvc.spec.storage_class_name is None


def test_compile_pvc_storage_class_and_model_source():
    pvc = c.compile_pvc(
        resource_name="md-default-qwen",
        workspace="default",
        name="qwen",
        engine="vllm",
        disk_size="100Gi",
        storage_class="fast-ssd",
        model_source="default/qwen@main",
    )
    assert pvc.spec.storage_class_name == "fast-ssd"
    # model source is an annotation (its value contains '/' and '@', invalid for labels).
    assert pvc.metadata.annotations[c.MODEL_SOURCE_ANNOTATION] == "default/qwen@main"


def test_compile_pvc_custom_access_modes():
    pvc = c.compile_pvc(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        disk_size="10Gi",
        access_modes=["ReadWriteMany"],
    )
    assert pvc.spec.access_modes == ["ReadWriteMany"]


# ---------------------------------------------------------------------------
# Puller Job
# ---------------------------------------------------------------------------


def test_compile_puller_job_basic():
    job = c.compile_puller_job(
        resource_name="md-default-qwen",
        workspace="default",
        name="qwen",
        engine="vllm",
        image="hf-cli:25.10",
        container_args=["download", "default/qwen", "--local-dir", "/model-store"],
        env={"HF_ENDPOINT": "http://files/apis/files/v2/hf", "HF_TOKEN": "service:models"},
        gpu=2,
        namespace="nemo",
        service_account_name="nemo-models-sa",
        image_pull_secret="nvcrimagepullsecret",
        model_source="default/qwen@main",
    )
    assert job.metadata.name == "md-default-qwen-pull"
    assert job.spec.backoff_limit == c.DEFAULT_BACKOFF_LIMIT
    assert job.spec.ttl_seconds_after_finished == c.DEFAULT_TTL_SECONDS_AFTER_FINISHED

    pod = job.spec.template.spec
    assert pod.restart_policy == "Never"
    assert pod.service_account_name == "nemo-models-sa"
    assert pod.image_pull_secrets[0].name == "nvcrimagepullsecret"

    ctr = pod.containers[0]
    assert ctr.args == ["download", "default/qwen", "--local-dir", "/model-store"]
    # Entrypoint overridden to the HF CLI (nmp-api's image entrypoint is `nemo
    # services run`); args run as `hf download ...`.
    assert ctr.command == ["hf"]
    env = {e.name: e.value for e in ctr.env}
    assert env["HF_ENDPOINT"] == "http://files/apis/files/v2/hf"
    assert env["HF_TOKEN"] == "service:models"
    # GPU request pins the puller into GPU topology for PVC binding.
    assert ctr.resources.requests["nvidia.com/gpu"] == "2"
    assert ctr.resources.limits["nvidia.com/gpu"] == "2"
    assert ctr.volume_mounts[0].mount_path == "/model-store"
    # Job annotation carries the model source for the re-pull policy.
    assert job.metadata.annotations[c.MODEL_SOURCE_ANNOTATION] == "default/qwen@main"


def test_compile_puller_job_cpu_only_no_gpu_request():
    job = c.compile_puller_job(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="hf-cli",
        container_args=["download", "w/n", "--local-dir", "/model-store"],
        gpu=0,
    )
    assert job.spec.template.spec.containers[0].resources is None


def test_compile_puller_job_no_image_pull_secret():
    job = c.compile_puller_job(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="hf-cli",
        container_args=["download"],
    )
    assert job.spec.template.spec.image_pull_secrets is None


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------


def test_compile_deployment_basic():
    dep = c.compile_deployment(
        resource_name="md-default-qwen",
        workspace="default",
        name="qwen",
        engine="vllm",
        image="vllm/vllm-openai:v0.22.1",
        args=["/model-store", "--served-model-name", "default/qwen"],
        health_path="/health",
        gpu=2,
        namespace="nemo",
        service_account_name="nemo-models-sa",
    )
    assert dep.metadata.name == "md-default-qwen"
    assert dep.spec.replicas == 1
    assert dep.spec.selector.match_labels == {"app": "md-default-qwen"}

    pod = dep.spec.template.spec
    assert pod.service_account_name == "nemo-models-sa"
    ctr = pod.containers[0]
    # command unset -> image entrypoint (vllm serve) runs; args appended.
    assert ctr.command is None
    assert ctr.args == ["/model-store", "--served-model-name", "default/qwen"]
    assert ctr.ports[0].container_port == 8000
    assert ctr.resources.limits["nvidia.com/gpu"] == "2"
    assert ctr.startup_probe.http_get.path == "/health"
    assert ctr.readiness_probe.http_get.path == "/health"

    # PVC mounted read-only at /model-store; scratch + dshm present.
    mounts = {m.name: m for m in ctr.volume_mounts}
    assert mounts["model-store"].mount_path == "/model-store"
    assert mounts["model-store"].read_only is True
    assert mounts["scratch"].mount_path == "/scratch"
    assert mounts["dshm"].mount_path == "/dev/shm"

    vols = {v.name: v for v in pod.volumes}
    assert vols["model-store"].persistent_volume_claim.claim_name == "md-default-qwen-pvc"
    assert vols["dshm"].empty_dir.medium == "Memory"


def test_compile_deployment_cpu_only_no_gpu():
    dep = c.compile_deployment(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="img",
        args=["/model-store"],
        health_path="/health",
        gpu=0,
    )
    assert dep.spec.template.spec.containers[0].resources is None


def test_compile_deployment_startup_grace_to_failure_threshold():
    dep = c.compile_deployment(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="img",
        args=[],
        health_path="/health",
        startup_grace_seconds=600,
    )
    # ceil(600 / 10) == 60
    assert dep.spec.template.spec.containers[0].startup_probe.failure_threshold == 60


def test_compile_deployment_shared_memory_size_limit():
    dep = c.compile_deployment(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="img",
        args=[],
        health_path="/health",
        shared_memory_size_limit="8Gi",
    )
    vols = {v.name: v for v in dep.spec.template.spec.volumes}
    assert vols["dshm"].empty_dir.size_limit == "8Gi"


def test_compile_deployment_security_context_set_when_uid_gid_given():
    """When uid/gid are provided, the server pod gets that securityContext."""
    dep = c.compile_deployment(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="img",
        args=[],
        health_path="/health",
        user_id=2000,
        group_id=0,
    )
    sc = dep.spec.template.spec.security_context
    assert sc.run_as_user == 2000
    assert sc.run_as_group == 0
    assert sc.fs_group == 0


def test_compile_deployment_no_security_context_when_uid_gid_unset():
    """No uid/gid -> no forced securityContext (runs as the image's default user)."""
    dep = c.compile_deployment(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="img",
        args=[],
        health_path="/health",
    )
    assert dep.spec.template.spec.security_context is None


def test_compile_deployment_sidecars_and_init_containers():
    from kubernetes import client as k8s_client

    sidecar = k8s_client.V1Container(name="lora-sidecar", image="nmp-api")
    init = k8s_client.V1Container(name="lora-cache-init", image="busybox")
    dep = c.compile_deployment(
        resource_name="r",
        workspace="w",
        name="n",
        engine="vllm",
        image="img",
        args=[],
        health_path="/health",
        init_containers=[init],
        sidecar_containers=[sidecar],
    )
    pod = dep.spec.template.spec
    assert pod.init_containers[0].name == "lora-cache-init"
    assert [ctr.name for ctr in pod.containers] == ["r-ctr", "lora-sidecar"]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def test_compile_service_basic():
    svc = c.compile_service(
        resource_name="md-default-qwen",
        workspace="default",
        name="qwen",
        engine="vllm",
        namespace="nemo",
    )
    assert svc.spec.type == "ClusterIP"
    assert svc.spec.selector == {"app": "md-default-qwen"}
    assert svc.spec.ports[0].port == 8000
    assert svc.spec.ports[0].target_port == c.SERVER_PORT_NAME
    assert svc.metadata.labels[MODEL_MANAGED_BY_LABEL] == MODEL_MANAGED_BY_MODELS_CONTROLLER
