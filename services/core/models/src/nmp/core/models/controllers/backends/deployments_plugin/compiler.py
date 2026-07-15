# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compile ModelDeployments into deployments-plugin entity specifications."""

from dataclasses import dataclass

from nemo_deployments_plugin.entities import (
    Container,
    ContainerPort,
    DeploymentConfig,
    EnvVar,
    HTTPGetAction,
    K8sVolumeConfig,
    Probe,
    Volume,
    VolumeBackendConfig,
    VolumeMount,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.config import Runtime
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginConfig
from nmp.core.models.controllers.backends.deployments_plugin.naming import EntityNames, entity_names
from nmp.core.models.controllers.backends.deployments_plugin.resolve import ResolvedPluginDeployment
from nmp.core.models.controllers.backends.engine import (
    ENGINE_GENERIC,
    ENGINE_NIM,
    ENGINE_VLLM,
    config_engine,
    resolve_health_path,
)
from nmp.core.models.controllers.backends.generic_compiler import (
    compile_generic_args,
    compile_generic_env_vars,
    resolve_generic_image,
)
from nmp.core.models.controllers.backends.vllm_compiler import (
    MODEL_STORE_PATH,
    compile_vllm_args,
    compile_vllm_env_vars,
    resolve_vllm_image,
)

_WEIGHTS_MOUNT = "/model-store"
_SCRATCH_MOUNT = "/scratch"
_LORA_MOUNT = "/scratch/loras"
_SCRATCH_VOLUME_SIZE = "1Gi"


@dataclass(frozen=True)
class CompiledModelDeployment:
    """The plugin entities and dependency metadata for one model deployment."""

    names: EntityNames
    volume: Volume | None
    scratch_volume: Volume | None
    puller_config: DeploymentConfig | None
    server_config: DeploymentConfig
    puller_prerequisite: bool


def _labels(resolved: ResolvedPluginDeployment, engine: str, role: str) -> dict[str, str]:
    return {
        MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
        "nmp.nvidia.com/deployment-workspace": resolved.deployment.workspace,
        "nmp.nvidia.com/deployment-name": resolved.deployment.name,
        "nmp.nvidia.com/models-role": role,
        "nmp.nvidia.com/engine": engine,
    }


def _image(name: str, tag: str) -> str:
    return name if "@" in name or name.endswith(f":{tag}") else f"{name}:{tag}"


def _busybox_image(config: DeploymentsPluginConfig) -> str:
    return _image(config.busybox_image, config.busybox_image_tag)


def _weighted(resolved: ResolvedPluginDeployment, engine: str) -> bool:
    is_files = resolved.weights_type == ModelWeightsType.FILES_SERVICE
    if engine == ENGINE_VLLM:
        return is_files or bool(resolved.model_namespace and resolved.model_name)
    if engine == ENGINE_NIM:
        return is_files
    return is_files or bool(resolved.model_entity and resolved.model_entity.fileset)


def _env(values: dict[str, str]) -> list[EnvVar]:
    return [EnvVar(name=name, value=value) for name, value in values.items()]


def _lora_sidecar(
    resolved: ResolvedPluginDeployment,
    *,
    engine: str,
    config: DeploymentsPluginConfig,
    names: EntityNames,
    weighted: bool,
) -> Container:
    """Build the adapters sidecar with the same env contract as existing backends."""
    entity_workspace = resolved.model_entity.workspace if resolved.model_entity else resolved.deployment.workspace
    entity_name = resolved.model_entity.name if resolved.model_entity else resolved.deployment.name
    sidecar_env = {
        "NIM_PEFT_SOURCE": _LORA_MOUNT,
        "NIM_PEFT_REFRESH_INTERVAL": str(config.peft_refresh_interval),
        "NMP_MODEL_ENTITY_WORKSPACE": entity_workspace,
        "NMP_MODEL_ENTITY_NAME": entity_name,
    }
    if engine == ENGINE_VLLM:
        sidecar_env["VLLM_LORA_BASE_MODEL_OVERRIDE"] = MODEL_STORE_PATH
    mounts = [VolumeMount(name=names.scratch, mountPath=_SCRATCH_MOUNT)]
    if weighted:
        mounts.append(VolumeMount(name=names.volume, mountPath=_WEIGHTS_MOUNT, readOnly=True))
    return Container(
        name="lora-adapters",
        image=get_qualified_image(config.lora_sidecar_image_name),
        command=config.lora_sidecar_command,
        args=config.lora_sidecar_args,
        env=_env(sidecar_env),
        volumeMounts=mounts,
        restartPolicy="Always",
    )


def compile_model_deployment(
    resolved: ResolvedPluginDeployment, config: DeploymentsPluginConfig
) -> CompiledModelDeployment:
    """Compile volume, puller, and always-on serving config specifications."""
    engine = config_engine(resolved.config)
    if engine not in {ENGINE_NIM, ENGINE_VLLM, ENGINE_GENERIC}:
        raise ValueError(f"Unsupported engine {engine!r}.")
    names = entity_names(resolved.deployment.name)
    weighted = _weighted(resolved, engine)
    lora_enabled = resolved.view.lora_enabled and engine != ENGINE_GENERIC
    volume = None
    scratch_volume = None
    puller_config = None
    if weighted:
        volume = Volume(
            name=names.volume,
            workspace=resolved.deployment.workspace,
            size=resolved.view.disk_size or config.default_pvc_size,
            backendConfig=VolumeBackendConfig(k8s=K8sVolumeConfig(storageClass=config.default_storage_class)),
        )
        puller_env = {"HF_ENDPOINT": resolved.files_hf_url}
        puller_args = ["download", f"{resolved.model_namespace}/{resolved.model_name}", "--local-dir", _WEIGHTS_MOUNT]
        if resolved.model_revision:
            puller_args.extend(["--revision", resolved.model_revision])
        puller = Container(
            name="weight-puller",
            image=resolved.huggingface_model_puller,
            command=["hf"],
            args=puller_args,
            env=_env(puller_env),
            volumeMounts=[VolumeMount(name=names.volume, mountPath=_WEIGHTS_MOUNT)],
        )
        puller_config = DeploymentConfig(
            name=names.puller,
            workspace=resolved.deployment.workspace,
            containers=[puller],
            labels=_labels(resolved, engine, "puller"),
            restartPolicy="OnFailure",
            backoffLimit=config.max_restart_count,
        )

    if engine == ENGINE_VLLM:
        image_name, image_tag = resolve_vllm_image(
            resolved.view, config.default_vllm_image, config.default_vllm_image_tag
        )
        args = compile_vllm_args(resolved.view, resolved.model_entity)
        env = compile_vllm_env_vars(resolved.view)
    elif engine == ENGINE_NIM:
        image_name, image_tag = (
            resolved.view.image_name or config.default_nimservice_image,
            resolved.view.image_tag or config.default_nimservice_image_tag,
        )
        args = list(resolved.view.additional_args or [])
        env = dict(resolved.view.additional_envs or {})
        env.update({"NIM_MODEL_NAME": _WEIGHTS_MOUNT, "NIM_MODEL_PATH": _WEIGHTS_MOUNT})
        if resolved.model_name:
            env["NIM_SERVED_MODEL_NAME"] = (
                f"{resolved.model_namespace}/{resolved.model_name}" if resolved.model_namespace else resolved.model_name
            )
        if lora_enabled:
            env["NIM_PEFT_SOURCE"] = _LORA_MOUNT
            env["NIM_PEFT_REFRESH_INTERVAL"] = str(config.peft_refresh_interval)
    else:
        image_name, image_tag = resolve_generic_image(resolved.view)
        args = compile_generic_args(resolved.view)
        env = compile_generic_env_vars(resolved.view)

    mounts: list[VolumeMount] = []
    if weighted:
        mounts.append(VolumeMount(name=names.volume, mountPath=_WEIGHTS_MOUNT, readOnly=True))
    init_containers: list[Container] = []
    server_config_containers: list[Container]
    if lora_enabled:
        scratch_volume = Volume(
            name=names.scratch,
            workspace=resolved.deployment.workspace,
            size=_SCRATCH_VOLUME_SIZE,
            backendConfig=VolumeBackendConfig(k8s=K8sVolumeConfig(storageClass=config.default_storage_class)),
        )
        mounts.append(VolumeMount(name=names.scratch, mountPath=_SCRATCH_MOUNT))
        # Ensure the LoRA cache dir exists before the server/sidecar start.
        init_containers.append(
            Container(
                name="lora-cache-init",
                image=_busybox_image(config),
                command=["sh", "-c", f"mkdir -p {_LORA_MOUNT} && chmod -R 777 {_LORA_MOUNT}"],
                volumeMounts=[VolumeMount(name=names.scratch, mountPath=_SCRATCH_MOUNT)],
            )
        )
        lora = _lora_sidecar(resolved, engine=engine, config=config, names=names, weighted=weighted)
        server = Container(
            name="server",
            image=_image(image_name, image_tag),
            args=args,
            env=_env(env),
            ports=[ContainerPort(name="http", containerPort=8000)],
            volumeMounts=mounts,
            readinessProbe=Probe(httpGet=HTTPGetAction(path=resolve_health_path(engine, resolved.view), port=8000)),
        )
        if resolved.runtime == Runtime.DOCKER:
            # Docker v1 is single-container today; emit a second container so the
            # shape matches the locked design for when the plugin docker backend
            # accepts multi-container DeploymentConfigs. In practice the backend
            # fails fast on docker + LoRA before reaching create (see
            # DeploymentsPluginServiceBackend.create_model_deployment).
            server_config_containers = [server, lora]
        else:
            server_config_containers = [server]
            init_containers.append(lora)
    else:
        server_config_containers = [
            Container(
                name="server",
                image=_image(image_name, image_tag),
                args=args,
                env=_env(env),
                ports=[ContainerPort(name="http", containerPort=8000)],
                volumeMounts=mounts,
                readinessProbe=Probe(httpGet=HTTPGetAction(path=resolve_health_path(engine, resolved.view), port=8000)),
            )
        ]

    server_config = DeploymentConfig(
        name=names.server,
        workspace=resolved.deployment.workspace,
        containers=server_config_containers,
        initContainers=init_containers,
        labels=_labels(resolved, engine, "server"),
        restartPolicy="Always",
    )
    return CompiledModelDeployment(
        names=names,
        volume=volume,
        scratch_volume=scratch_volume,
        puller_config=puller_config,
        server_config=server_config,
        puller_prerequisite=puller_config is not None,
    )
