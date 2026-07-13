# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from nmp.common.config import Runtime
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.controllers.backends.common import DeploymentConfigView
from nmp.core.models.controllers.backends.deployments_plugin.compiler import compile_model_deployment
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginConfig
from nmp.core.models.controllers.backends.deployments_plugin.resolve import ResolvedPluginDeployment


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


def test_nim_weighted_chain_sets_model_path_env() -> None:
    compiled = compile_model_deployment(_resolved("nim"), DeploymentsPluginConfig())
    assert compiled.volume is not None
    assert compiled.puller_config is not None
    env = {item.name: item.value for item in compiled.server_config.containers[0].env}
    assert env["NIM_MODEL_NAME"] == "/model-store"
    assert env["NIM_MODEL_PATH"] == "/model-store"
    assert env["NIM_SERVED_MODEL_NAME"] == "org/model"


def test_generic_weightless_is_server_only() -> None:
    resolved = _resolved("generic")
    resolved = ResolvedPluginDeployment(
        deployment=resolved.deployment,
        config=resolved.config,
        model_entity=None,
        view=DeploymentConfigView(image_name="custom/image", image_tag="1"),
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


def test_lora_uses_native_sidecar_on_k8s_and_container_on_docker() -> None:
    config = DeploymentsPluginConfig()
    assert (
        compile_model_deployment(_resolved("vllm", lora=True), config).server_config.init_containers[0].restart_policy
        == "Always"
    )
    assert (
        len(
            compile_model_deployment(
                _resolved("vllm", lora=True, runtime=Runtime.DOCKER), config
            ).server_config.containers
        )
        == 2
    )
