# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest
from nemo_deployments_plugin.entities import (
    Container,
    DeploymentBackendConfig,
    K8sDeploymentConfig,
    Probe,
    ResourceRequirements,
    Toleration,
    VolumeMount,
)
from nemo_platform.types.inference.k8s_nim_operator_config import K8sNIMOperatorConfig
from nmp.common.config import Runtime
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.controllers.backends.common import DeploymentConfigView
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginConfig
from nmp.core.models.controllers.backends.deployments_plugin.nim_compiler import (
    apply_container_resources,
    apply_k8s_nim_operator_container_overrides,
    apply_nim_override_config,
    build_k8s_deployment_backend_config,
    compile_nim_server_env,
    k8s_backend_config_from_nim_operator,
    pod_security_context_for_engine,
    startup_probe_failure_threshold,
    tool_call_plugin_init_containers,
)
from nmp.core.models.controllers.backends.deployments_plugin.resolve import ResolvedPluginDeployment


def _resolved() -> ResolvedPluginDeployment:
    return ResolvedPluginDeployment(
        deployment=SimpleNamespace(name="my-dep", workspace="default"),
        config=SimpleNamespace(engine="nim"),
        model_entity=None,
        view=DeploymentConfigView(model_namespace="org", model_name="model"),
        weights_type=ModelWeightsType.FILES_SERVICE,
        model_namespace="org",
        model_name="model",
        model_revision=None,
        files_hf_url="http://files/hf",
        huggingface_model_puller="puller:latest",
        runtime=Runtime.KUBERNETES,
    )


def test_compile_nim_server_env_sets_ft_model_for_model_specific_image() -> None:
    env = compile_nim_server_env(_resolved(), DeploymentsPluginConfig(), weighted=True, tool_call_plugin_path=None)
    assert env["NIM_FT_MODEL"] == "/model-store"
    assert env["NIM_CUSTOM_MODEL"] == "/model-store"


def test_compile_nim_server_env_omits_ft_model_for_multi_llm_image() -> None:
    resolved = _resolved()
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="org",
            model_name="model",
            image_name="nvcr.io/nim/nvidia/llm-nim",
        ),
        weights_type=resolved.weights_type,
        model_namespace=resolved.model_namespace,
        model_name=resolved.model_name,
        model_revision=resolved.model_revision,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller=resolved.huggingface_model_puller,
        runtime=resolved.runtime,
    )
    env = compile_nim_server_env(resolved, DeploymentsPluginConfig(), weighted=True, tool_call_plugin_path=None)
    assert "NIM_FT_MODEL" not in env


def test_tool_call_plugin_init_containers_require_puller_tag() -> None:
    resolved = _resolved()
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="org",
            model_name="model",
            tool_call_config=SimpleNamespace(
                tool_call_plugin="ws/fileset",
                tool_call_parser=None,
                auto_tool_choice=None,
            ),
        ),
        weights_type=resolved.weights_type,
        model_namespace=resolved.model_namespace,
        model_name=resolved.model_name,
        model_revision=resolved.model_revision,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller="registry:5000/puller",
        runtime=resolved.runtime,
    )
    assert (
        tool_call_plugin_init_containers(
            resolved, DeploymentsPluginConfig(), names_volume="vol", names_scratch="scr", weighted=True
        )
        is None
    )


def test_k8s_backend_config_maps_node_selector_to_affinity() -> None:
    view = DeploymentConfigView(
        k8s_nim_operator_config=K8sNIMOperatorConfig(node_selector={"zone": "us-west1-a"}),
    )
    k8s = k8s_backend_config_from_nim_operator(view)
    assert k8s is not None
    assert k8s.affinity is not None


def test_startup_probe_failure_threshold_rounds_up() -> None:
    view = DeploymentConfigView(k8s_nim_operator_config=K8sNIMOperatorConfig(startup_probe_grace_seconds=605))
    assert startup_probe_failure_threshold(view, period_seconds=10) == 61


def test_apply_k8s_nim_operator_container_overrides_updates_resources_and_probe() -> None:
    container = Container(name="server", image="nim:latest")
    probe = Probe()
    view = DeploymentConfigView(
        k8s_nim_operator_config=K8sNIMOperatorConfig(
            resources={"requests": {"cpu": "2"}},
            startup_probe_grace_seconds=30,
        )
    )
    apply_k8s_nim_operator_container_overrides(container, probe, view)
    assert container.resources.requests["cpu"] == "2"
    assert probe.failure_threshold == 3


def test_pod_security_context_uses_nim_defaults() -> None:
    view = DeploymentConfigView()
    config = DeploymentsPluginConfig(default_user_id=1000, default_group_id=2000)
    security_context = pod_security_context_for_engine("nim", view, config)
    assert security_context is not None
    assert security_context.run_as_user == 1000
    assert security_context.run_as_group == 2000


def test_build_k8s_deployment_backend_config_merges_security_context() -> None:
    view = DeploymentConfigView()
    config = DeploymentsPluginConfig(default_user_id=1000, default_group_id=2000)
    backend = build_k8s_deployment_backend_config("nim", view, config)
    assert backend.k8s is not None
    assert backend.k8s.security_context is not None
    assert backend.k8s.security_context.run_as_user == 1000


def test_build_k8s_deployment_backend_config_ignores_nim_operator_fields_for_vllm() -> None:
    view = DeploymentConfigView(
        k8s_nim_operator_config=K8sNIMOperatorConfig(node_selector={"zone": "us-west1-a"}),
    )
    backend = build_k8s_deployment_backend_config("vllm", view, DeploymentsPluginConfig())
    assert backend.k8s is not None
    assert backend.k8s.affinity is None


def test_apply_container_resources_deep_merges_existing_values() -> None:
    container = Container(
        name="server",
        image="nim:1.0",
        resources=ResourceRequirements(requests={"cpu": "1", "memory": "8Gi"}, limits={"memory": "16Gi"}),
    )
    apply_container_resources(container, {"requests": {"cpu": "4"}, "limits": {"cpu": "2"}})
    assert container.resources.requests == {"cpu": "4", "memory": "8Gi"}
    assert container.resources.limits == {"memory": "16Gi", "cpu": "2"}


def test_tool_call_plugin_init_containers_use_scratch_path_when_unweighted() -> None:
    resolved = _resolved()
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="org",
            model_name="model",
            tool_call_config=SimpleNamespace(
                tool_call_plugin="ws/fileset",
                tool_call_parser=None,
                auto_tool_choice=None,
            ),
        ),
        weights_type=ModelWeightsType.BAKED_CONTAINER,
        model_namespace=resolved.model_namespace,
        model_name=resolved.model_name,
        model_revision=resolved.model_revision,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller="puller:latest",
        runtime=resolved.runtime,
    )
    inits = tool_call_plugin_init_containers(
        resolved, DeploymentsPluginConfig(), names_volume="vol", names_scratch="scr", weighted=False
    )
    assert inits is not None
    assert inits[0].volume_mounts == [VolumeMount(name="scr", mountPath="/scratch")]
    assert "/scratch/plugin/plugin.py" in inits[0].command[2]
    finalize_script = inits[2].command[2]
    assert 'if [ "$plugin_file" != "/scratch/plugin/plugin.py" ]; then' in finalize_script


def test_apply_nim_override_config_overrides_operator_defaults() -> None:
    from nemo_deployments_plugin.entities import DeploymentConfig

    container = Container(name="server", image="nim:1.0")
    container.resources = ResourceRequirements(requests={"cpu": "1"})
    container.readiness_probe = Probe()
    server_config = DeploymentConfig(
        name="dep-server",
        workspace="default",
        containers=[container],
        backendConfig=DeploymentBackendConfig(
            k8s=K8sDeploymentConfig(
                tolerations=[Toleration(key="old-key")],
            )
        ),
    )
    view = DeploymentConfigView(
        k8s_nim_operator_config=K8sNIMOperatorConfig(resources={"requests": {"cpu": "2"}}),
        override_config={
            "resources": {"requests": {"cpu": "8"}, "limits": {"memory": "64Gi"}},
            "nodeSelector": {"zone": "b"},
            "env": [{"name": "EXTRA", "value": "1"}],
            "image": {"repository": "nvcr.io/override", "tag": "2.0"},
            "readinessProbe": {
                "enabled": True,
                "probe": {"httpGet": {"path": "/ready", "port": 8080}, "failureThreshold": 12},
            },
            "userID": 42,
            "groupID": 84,
            "labels": {"custom": "label"},
        },
    )
    apply_nim_override_config(
        container,
        server_config,
        view,
        engine="nim",
        runtime=Runtime.KUBERNETES,
    )
    assert container.image == "nvcr.io/override:2.0"
    assert container.resources.requests["cpu"] == "8"
    assert container.resources.limits["memory"] == "64Gi"
    assert {item.name: item.value for item in container.env}["EXTRA"] == "1"
    assert container.readiness_probe is not None
    assert container.readiness_probe.http_get is not None
    assert container.readiness_probe.http_get.path == "/ready"
    assert container.readiness_probe.http_get.port == 8080
    assert container.readiness_probe.failure_threshold == 12
    k8s = server_config.backend_config.k8s
    assert k8s is not None
    assert k8s.affinity is not None
    assert k8s.security_context is not None
    assert k8s.security_context.run_as_user == 42
    assert server_config.labels["custom"] == "label"


def test_apply_nim_override_config_ignored_on_docker() -> None:
    from nemo_deployments_plugin.entities import DeploymentConfig

    container = Container(name="server", image="nim:1.0")
    server_config = DeploymentConfig(name="dep-server", workspace="default", containers=[container])
    view = DeploymentConfigView(override_config={"image": {"repository": "override", "tag": "x"}})
    apply_nim_override_config(
        container,
        server_config,
        view,
        engine="nim",
        runtime=Runtime.DOCKER,
    )
    assert container.image == "nim:1.0"


def test_apply_nim_override_config_rejects_unsupported_keys() -> None:
    from nemo_deployments_plugin.entities import DeploymentConfig

    container = Container(name="server", image="nim:1.0")
    server_config = DeploymentConfig(name="dep-server", workspace="default", containers=[container])
    view = DeploymentConfigView(override_config={"authSecret": "secret", "replicas": 2})
    with pytest.raises(ValueError, match="unsupported keys: authSecret, replicas"):
        apply_nim_override_config(
            container,
            server_config,
            view,
            engine="nim",
            runtime=Runtime.KUBERNETES,
        )
