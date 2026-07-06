# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from backends.k8s.k8s_helpers import sample_always_config, sample_config
from kubernetes.client import ApiClient
from nemo_deployments_plugin.backends.k8s.compiler import (
    DeploymentConfigError,
    build_configmap_body,
    compile_workload,
    configmap_data_key,
    validate_config_for_deployment,
    validate_config_for_job,
)
from nemo_deployments_plugin.backends.k8s.deployments import build_deployment_body
from nemo_deployments_plugin.backends.k8s.jobs import build_job_body
from nemo_deployments_plugin.entities import (
    ConfigFile,
    Container,
    ContainerPort,
    K8sDeploymentConfig,
)


def _serialized(obj: object) -> dict:
    return ApiClient().sanitize_for_serialization(obj)


def test_configmap_data_key_sanitizes_paths() -> None:
    assert configmap_data_key("/etc/app/config.yaml") == "etc__app__config.yaml"


def test_compile_job_pod_spec_single_container() -> None:
    config = sample_config(restart_policy="Never")
    compiled = compile_workload(
        config=config,
        workspace="default",
        deployment_name="task",
        labels={"managed-by": "nemo-deployments"},
        k8s_config=None,
        pod_restart_policy="Never",
    )
    pod_spec = _serialized(compiled.pod_spec_kwargs)
    assert pod_spec["restart_policy"] == "Never"
    assert len(pod_spec["containers"]) == 1
    assert pod_spec["containers"][0]["name"] == "main"
    assert compiled.configmap_body is None


def test_compile_deployment_includes_init_and_sidecar() -> None:
    config = sample_always_config().model_copy(
        update={
            "init_containers": [
                Container(name="bootstrap", image="busybox", command=["sh", "-c", "echo hi"]),
                Container.model_validate(
                    {
                        "name": "sidecar",
                        "image": "nginx:alpine",
                        "restartPolicy": "Always",
                        "ports": [{"name": "proxy", "containerPort": 8081}],
                        "livenessProbe": {"httpGet": {"path": "/healthz", "port": 8081}},
                    }
                ),
            ],
            "containers": [
                Container(name="main", image="nginx:alpine", ports=[ContainerPort(name="http", containerPort=8080)]),
                Container(
                    name="metrics",
                    image="prom/node-exporter",
                    ports=[ContainerPort(name="metrics", containerPort=9100)],
                ),
            ],
        }
    )
    compiled = compile_workload(
        config=config,
        workspace="default",
        deployment_name="task",
        labels={"managed-by": "nemo-deployments"},
        k8s_config=None,
        pod_restart_policy="Always",
    )
    pod_spec = _serialized(compiled.pod_spec_kwargs)
    assert pod_spec == {
        "restart_policy": "Always",
        "init_containers": [
            {
                "name": "bootstrap",
                "image": "busybox",
                "command": ["sh", "-c", "echo hi"],
            },
            {
                "name": "sidecar",
                "image": "nginx:alpine",
                "restartPolicy": "Always",
                "ports": [{"name": "proxy", "containerPort": 8081, "protocol": "TCP"}],
                "livenessProbe": {
                    "httpGet": {"path": "/healthz", "port": 8081, "scheme": "HTTP"},
                    "initialDelaySeconds": 0,
                    "timeoutSeconds": 1,
                    "periodSeconds": 10,
                    "failureThreshold": 3,
                },
            },
        ],
        "containers": [
            {
                "name": "main",
                "image": "nginx:alpine",
                "ports": [{"name": "http", "containerPort": 8080, "protocol": "TCP"}],
            },
            {
                "name": "metrics",
                "image": "prom/node-exporter",
                "ports": [{"name": "metrics", "containerPort": 9100, "protocol": "TCP"}],
            },
        ],
    }
    assert len(compiled.service_containers) == 2


def test_compile_applies_k8s_deployment_config() -> None:
    config = sample_always_config()
    k8s_config = K8sDeploymentConfig.model_validate(
        {
            "serviceAccount": "deploy-sa",
            "tolerations": [{"key": "gpu", "operator": "Equal", "value": "true", "effect": "NoSchedule"}],
            "affinity": {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": []}}},
            "securityContext": {"runAsUser": 1000, "fsGroup": 2000},
        }
    )
    compiled = compile_workload(
        config=config,
        workspace="default",
        deployment_name="task",
        labels={"managed-by": "nemo-deployments"},
        k8s_config=k8s_config,
        pod_restart_policy="Always",
    )
    pod_spec = _serialized(compiled.pod_spec_kwargs)
    assert pod_spec["service_account_name"] == "deploy-sa"
    assert pod_spec["tolerations"][0]["key"] == "gpu"
    affinity = compiled.pod_spec_kwargs["affinity"]
    assert affinity.node_affinity is not None
    security_context = compiled.pod_spec_kwargs["security_context"]
    assert security_context.run_as_user == 1000


def test_compile_config_files_emit_configmap_and_mounts() -> None:
    config = sample_always_config().model_copy(
        update={"config_files": [ConfigFile(path="/etc/app/config.yaml", content="key: value")]}
    )
    labels = {"managed-by": "nemo-deployments"}
    compiled = compile_workload(
        config=config,
        workspace="default",
        deployment_name="task",
        labels=labels,
        k8s_config=None,
        pod_restart_policy="Always",
    )
    assert compiled.configmap_body is not None
    configmap = _serialized(compiled.configmap_body)
    assert configmap["data"]["etc__app__config.yaml"] == "key: value"
    pod_spec = _serialized(compiled.pod_spec_kwargs)
    assert any(volume["name"] == "config-files" for volume in pod_spec["volumes"])
    main_container = compiled.pod_spec_kwargs["containers"][0]
    mount_paths = [mount.mount_path for mount in main_container.volume_mounts or []]
    assert "/etc/app/config.yaml" in mount_paths


def test_build_job_body_returns_compiled_workload() -> None:
    config = sample_config(restart_policy="OnFailure")
    built = build_job_body(
        job_name="dep-default-task-abc",
        labels={"managed-by": "nemo-deployments"},
        config=config,
        workspace="default",
        deployment_name="task",
        k8s_config=None,
    )
    assert built.job.kind == "Job"
    assert built.compiled.pod_spec_kwargs["restart_policy"] == "OnFailure"


def test_build_deployment_body_returns_compiled_workload() -> None:
    config = sample_always_config()
    built = build_deployment_body(
        resource_name="dep-default-task-abc",
        labels={"managed-by": "nemo-deployments"},
        config=config,
        workspace="default",
        deployment_name="task",
        k8s_config=None,
    )
    assert built.deployment.kind == "Deployment"
    assert built.compiled.service_containers[0].name == "main"


def test_validate_rejects_main_container_restart_policy() -> None:
    config = sample_always_config().model_copy(
        update={"containers": [Container.model_validate({"name": "main", "image": "nginx", "restartPolicy": "Always"})]}
    )
    with pytest.raises(DeploymentConfigError, match="only init_containers"):
        validate_config_for_deployment(config)


def test_validate_job_rejects_always() -> None:
    with pytest.raises(DeploymentConfigError, match="Deployment"):
        validate_config_for_job(sample_always_config())


def test_validate_rejects_duplicate_port_names() -> None:
    config = sample_always_config().model_copy(
        update={
            "containers": [
                Container(
                    name="main",
                    image="nginx",
                    ports=[ContainerPort(name="http", containerPort=8080)],
                ),
                Container(
                    name="side",
                    image="nginx",
                    ports=[ContainerPort(name="http", containerPort=9090)],
                ),
            ],
        }
    )
    with pytest.raises(DeploymentConfigError, match="duplicate container port name"):
        validate_config_for_deployment(config)


def test_validate_rejects_duplicate_listen_ports() -> None:
    config = sample_always_config().model_copy(
        update={
            "containers": [
                Container(
                    name="main",
                    image="nginx",
                    ports=[ContainerPort(name="http", containerPort=8080)],
                ),
                Container(
                    name="side",
                    image="nginx",
                    ports=[ContainerPort(name="alt", containerPort=8080)],
                ),
            ],
        }
    )
    with pytest.raises(DeploymentConfigError, match="duplicate container port 8080"):
        validate_config_for_deployment(config)


def test_build_configmap_body_none_when_empty() -> None:
    assert build_configmap_body(workspace="default", deployment_name="task", labels={}, config_files=[]) is None
