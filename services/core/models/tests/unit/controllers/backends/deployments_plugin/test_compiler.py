# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from nemo_platform.types.inference.k8s_nim_operator_config import K8sNIMOperatorConfig
from nmp.common.config import Runtime
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.controllers.backends.common import DeploymentConfigView
from nmp.core.models.controllers.backends.deployments_plugin.compiler import compile_model_deployment
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginConfig
from nmp.core.models.controllers.backends.deployments_plugin.resolve import ResolvedPluginDeployment
from nmp.core.models.controllers.backends.vllm_compiler import MODEL_STORE_PATH


def _resolved(engine: str, *, lora: bool = False, runtime: Runtime = Runtime.KUBERNETES) -> ResolvedPluginDeployment:
    return ResolvedPluginDeployment(
        deployment=SimpleNamespace(name="my-dep", workspace="default"),
        config=SimpleNamespace(engine=engine),
        model_entity=None,
        view=DeploymentConfigView(model_namespace="org", model_name="model", lora_enabled=lora),
        weights_type=ModelWeightsType.FILES_SERVICE,
        model_namespace="org",
        model_name="model",
        model_revision=None,
        files_hf_url="http://files/hf",
        huggingface_model_puller="puller:latest",
        runtime=runtime,
    )


def test_vllm_weighted_chain_has_on_failure_puller_and_always_server() -> None:
    compiled = compile_model_deployment(_resolved("vllm"), DeploymentsPluginConfig())
    assert compiled.volume is not None
    assert compiled.puller_config is not None and compiled.puller_config.restart_policy == "OnFailure"
    assert compiled.server_config.restart_policy == "Always"
    assert compiled.puller_prerequisite is True
    assert compiled.server_config.containers[0].volume_mounts[0].read_only is True


def test_docker_weights_volume_requests_init_chmod() -> None:
    # Docker named volumes are root-owned with no fs_group, so the weights volume
    # must be made writable (chmod) for the non-root puller. The compiler requests
    # this on the volume's docker backend config (docker analogue of k8s fsGroup).
    compiled = compile_model_deployment(_resolved("vllm", runtime=Runtime.DOCKER), DeploymentsPluginConfig())
    assert compiled.volume is not None
    docker_cfg = compiled.volume.backend_config.docker
    assert docker_cfg is not None
    assert docker_cfg.init_chmod == "0777"
    assert docker_cfg.init_image  # busybox image is set


def test_k8s_weights_volume_has_no_docker_init_chmod() -> None:
    # On k8s, pod securityContext/fs_group handles volume ownership, so no docker
    # init-chmod is emitted.
    compiled = compile_model_deployment(_resolved("vllm", runtime=Runtime.KUBERNETES), DeploymentsPluginConfig())
    assert compiled.volume is not None
    assert compiled.volume.backend_config.docker is None


def test_vllm_server_command_image_args_and_gpu() -> None:
    resolved = _resolved("vllm")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(model_namespace="org", model_name="model", gpu=1),
        weights_type=resolved.weights_type,
        model_namespace=resolved.model_namespace,
        model_name=resolved.model_name,
        model_revision=resolved.model_revision,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller=resolved.huggingface_model_puller,
        runtime=resolved.runtime,
    )
    compiled = compile_model_deployment(resolved, DeploymentsPluginConfig())
    server = compiled.server_config.containers[0]
    assert server.command == ["vllm", "serve"]
    assert server.args[0] == MODEL_STORE_PATH
    assert server.image == "docker.io/vllm/vllm-openai:v0.22.1"
    assert server.resources is not None
    assert server.resources.limits["nvidia.com/gpu"] == "1"
    assert compiled.puller_config is not None
    puller = compiled.puller_config.containers[0]
    puller_env = {item.name: item.value for item in puller.env}
    assert puller_env["HF_ENDPOINT"] == resolved.files_hf_url
    assert puller_env["HF_TOKEN"] == "service:models"
    assert puller.resources is not None
    assert puller.resources.limits["nvidia.com/gpu"] == "1"


def test_nim_gpu_resources_without_override() -> None:
    resolved = _resolved("nim")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="org",
            model_name="model",
            gpu=1,
            image_name="nvcr.io/nim/meta/llama-3.1-8b-instruct",
            image_tag="1.8.5",
        ),
        weights_type=ModelWeightsType.BAKED_CONTAINER,
        model_namespace=None,
        model_name=None,
        model_revision=None,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller=resolved.huggingface_model_puller,
        runtime=Runtime.KUBERNETES,
    )
    compiled = compile_model_deployment(resolved, DeploymentsPluginConfig())
    server = compiled.server_config.containers[0]
    assert server.resources is not None
    assert server.resources.limits["nvidia.com/gpu"] == "1"


def test_nim_weighted_chain_sets_model_path_env() -> None:
    compiled = compile_model_deployment(_resolved("nim"), DeploymentsPluginConfig())
    assert compiled.volume is not None
    assert compiled.puller_config is not None
    env = {item.name: item.value for item in compiled.server_config.containers[0].env}
    assert env["NIM_MODEL_NAME"] == "/model-store"
    assert env["NIM_MODEL_PATH"] == "/model-store"
    assert env["NIM_SERVED_MODEL_NAME"] == "org/model"
    assert env["NIM_FT_MODEL"] == "/model-store"
    assert env["NIM_CUSTOM_MODEL"] == "/model-store"


def test_nim_multi_llm_weighted_omits_ft_model_env() -> None:
    resolved = _resolved("nim")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="nvidia",
            model_name="Llama-3.1-Nemotron-Nano-4B-v1.1",
            image_name="nvcr.io/nim/nvidia/llm-nim",
        ),
        weights_type=resolved.weights_type,
        model_namespace="nvidia",
        model_name="Llama-3.1-Nemotron-Nano-4B-v1.1",
        model_revision=resolved.model_revision,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller=resolved.huggingface_model_puller,
        runtime=resolved.runtime,
    )
    compiled = compile_model_deployment(resolved, DeploymentsPluginConfig())
    env = {item.name: item.value for item in compiled.server_config.containers[0].env}
    assert env["NIM_MODEL_NAME"] == "/model-store"
    assert "NIM_FT_MODEL" not in env
    assert "NIM_CUSTOM_MODEL" not in env
    assert env["NIM_SERVED_MODEL_NAME"] == "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1"


def test_nim_tool_call_plugin_adds_init_containers_and_env() -> None:
    resolved = _resolved("nim")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="org",
            model_name="model",
            tool_call_config=SimpleNamespace(
                tool_call_plugin="test-ws/my-plugin-fileset",
                tool_call_parser=None,
                auto_tool_choice=None,
            ),
        ),
        weights_type=resolved.weights_type,
        model_namespace=resolved.model_namespace,
        model_name=resolved.model_name,
        model_revision=resolved.model_revision,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller="nvcr.io/nvidia/model-puller:latest",
        runtime=resolved.runtime,
    )
    compiled = compile_model_deployment(resolved, DeploymentsPluginConfig())
    assert len(compiled.server_config.init_containers) == 3
    pull = compiled.server_config.init_containers[1]
    assert pull.command == ["download", "test-ws/my-plugin-fileset", "--local-dir", "/scratch/plugin"]
    pull_env = {item.name: item.value for item in pull.env}
    assert pull_env["HF_TOKEN"] == "service:models"
    assert pull_env["HF_ENDPOINT"] == resolved.files_hf_url
    server_env = {item.name: item.value for item in compiled.server_config.containers[0].env}
    assert server_env["NIM_TOOL_PARSER_PLUGIN"] == "/model-store/plugin/plugin.py"


def test_nim_k8s_nim_operator_config_maps_tolerations_and_resources() -> None:
    resolved = _resolved("nim")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="org",
            model_name="model",
            k8s_nim_operator_config=K8sNIMOperatorConfig(
                tolerations=[{"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"}],
                node_selector={"node-type": "gpu-node"},
                resources={"requests": {"cpu": "4"}, "limits": {"memory": "32Gi"}},
                startup_probe_grace_seconds=600,
            ),
        ),
        weights_type=resolved.weights_type,
        model_namespace=resolved.model_namespace,
        model_name=resolved.model_name,
        model_revision=resolved.model_revision,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller=resolved.huggingface_model_puller,
        runtime=Runtime.KUBERNETES,
    )
    compiled = compile_model_deployment(resolved, DeploymentsPluginConfig())
    k8s = compiled.server_config.backend_config.k8s
    assert k8s is not None
    assert len(k8s.tolerations) == 1
    assert k8s.tolerations[0].key == "nvidia.com/gpu"
    assert k8s.affinity is not None
    server = compiled.server_config.containers[0]
    assert server.resources.requests["cpu"] == "4"
    assert server.resources.limits["memory"] == "32Gi"
    assert server.readiness_probe is not None
    assert server.readiness_probe.failure_threshold == 60
    assert k8s.security_context is not None
    assert k8s.security_context.run_as_user == 1000
    assert k8s.security_context.run_as_group == 2000


def test_nim_override_config_wins_over_k8s_nim_operator_config() -> None:
    resolved = _resolved("nim")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=resolved.model_entity,
        view=DeploymentConfigView(
            model_namespace="org",
            model_name="model",
            k8s_nim_operator_config=K8sNIMOperatorConfig(
                node_selector={"zone": "a"},
                resources={"requests": {"cpu": "2"}},
            ),
            override_config={
                "nodeSelector": {"zone": "override-zone"},
                "resources": {"requests": {"cpu": "16"}},
            },
        ),
        weights_type=ModelWeightsType.BAKED_CONTAINER,
        model_namespace=None,
        model_name=None,
        model_revision=None,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller=resolved.huggingface_model_puller,
        runtime=Runtime.KUBERNETES,
    )
    compiled = compile_model_deployment(resolved, DeploymentsPluginConfig())
    server = compiled.server_config.containers[0]
    assert server.resources.requests["cpu"] == "16"
    k8s = compiled.server_config.backend_config.k8s
    assert k8s is not None
    assert k8s.affinity is not None


def test_generic_weightless_is_server_only() -> None:
    resolved = _resolved("generic")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=None,
        view=DeploymentConfigView(
            image_name="custom/image",
            image_tag="1",
            additional_args=["python3", "-m", "http.server", "8000"],
        ),
        weights_type=ModelWeightsType.BAKED_CONTAINER,
        model_namespace=None,
        model_name=None,
        model_revision=None,
        files_hf_url=resolved.files_hf_url,
        huggingface_model_puller=resolved.huggingface_model_puller,
        runtime=resolved.runtime,
    )
    compiled = compile_model_deployment(resolved, DeploymentsPluginConfig())
    assert compiled.volume is None
    assert compiled.puller_config is None
    assert compiled.puller_prerequisite is False
    assert compiled.server_config.containers[0].image == "custom/image:1"
    assert compiled.server_config.containers[0].args == ["python3", "-m", "http.server", "8000"]
    assert compiled.server_config.containers[0].command == []
    k8s = compiled.server_config.backend_config.k8s
    assert k8s is None


def test_lora_uses_native_sidecar_on_k8s_and_container_on_docker() -> None:
    config = DeploymentsPluginConfig()
    platform = MagicMock()
    platform.base_url = "http://platform.example:8080"
    with (
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.compiler.get_qualified_image",
            return_value="registry/nmp-api:tag",
        ),
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.compiler.get_platform_config",
            return_value=platform,
        ),
    ):
        k8s = compile_model_deployment(_resolved("vllm", lora=True), config)
        docker = compile_model_deployment(_resolved("vllm", lora=True, runtime=Runtime.DOCKER), config)

    assert k8s.scratch_volume is not None
    init = k8s.server_config.init_containers[0]
    assert init.name == "lora-cache-init"
    assert init.image == "docker.io/library/busybox:latest"
    sidecar = k8s.server_config.init_containers[-1]
    assert sidecar.restart_policy == "Always"
    assert sidecar.image == "registry/nmp-api:tag"
    env = {item.name: item.value for item in sidecar.env}
    assert env["NIM_PEFT_SOURCE"] == "/scratch/loras"
    # Sidecar `nemo services run` writes both its instance state ($XDG_STATE_HOME) and its
    # local data dir ($XDG_DATA_HOME, via nmp_user_data_dir) -- both must land on the
    # writable scratch volume, not the nmp-api image's $HOME (unwritable under the pod's
    # vLLM uid, so the sidecar crash-loops on PermissionError). See _lora_sidecar.
    assert env["XDG_STATE_HOME"] == "/scratch/.local"
    assert env["XDG_DATA_HOME"] == "/scratch/.local"
    assert env["VLLM_LORA_BASE_MODEL_OVERRIDE"] == "/model-store"
    assert env["NMP_BASE_URL"] == "http://platform.example:8080"
    assert env["VLLM_ENDPOINT"] == "http://127.0.0.1:8000"
    assert len(docker.server_config.containers) == 2
