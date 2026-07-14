# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve models API objects into compiler inputs."""

from dataclasses import dataclass
from urllib.parse import urljoin

from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.config import Runtime, get_platform_config
from nmp.core.models.app import ModelWeightsType, get_model_weights_type, parse_model_name_revision
from nmp.core.models.controllers.backends.common import DeploymentConfigView, deployment_config_view
from nmp.core.models.controllers.context import ModelContext


@dataclass(frozen=True)
class ResolvedPluginDeployment:
    """All API-object data required to compile plugin entities."""

    deployment: ModelDeployment
    config: ModelDeploymentConfig
    model_entity: ModelEntity | None
    view: DeploymentConfigView
    weights_type: ModelWeightsType
    model_namespace: str | None
    model_name: str | None
    model_revision: str | None
    files_hf_url: str
    huggingface_model_puller: str
    runtime: Runtime


def resolve_model_source(
    model_entity: ModelEntity | None, view: DeploymentConfigView
) -> tuple[str | None, str | None, str | None]:
    """Resolve file-set-backed model sources before config fallback."""
    namespace, name, revision = parse_model_name_revision(
        model_namespace=view.model_namespace, model_name=view.model_name, model_revision=view.model_revision
    )
    if model_entity and model_entity.fileset:
        parts = str(model_entity.fileset).removeprefix("hf://").removeprefix("fileset://").split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1], revision
    return namespace, name, revision


def resolve_plugin_deployment(ctx: ModelContext, huggingface_model_puller: str) -> ResolvedPluginDeployment:
    """Build compiler input from a model reconciliation context."""
    if ctx.model_deployment is None or ctx.model_deployment_config is None:
        raise ValueError("Model deployment and deployment config are required.")
    view = deployment_config_view(ctx.model_deployment_config)
    namespace, name, revision = resolve_model_source(ctx.model_entity, view)
    platform_config = get_platform_config()
    files_service_url = platform_config.service_discovery.get("files") or platform_config.base_url
    files_hf_url = urljoin(files_service_url.rstrip("/") + "/", "apis/files/v2/hf")
    return ResolvedPluginDeployment(
        deployment=ctx.model_deployment,
        config=ctx.model_deployment_config,
        model_entity=ctx.model_entity,
        view=view,
        weights_type=get_model_weights_type(
            model_deployment=ctx.model_deployment,
            model_deployment_config=ctx.model_deployment_config,
            model_entity=ctx.model_entity,
        ),
        model_namespace=namespace,
        model_name=name,
        model_revision=revision,
        files_hf_url=files_hf_url,
        huggingface_model_puller=huggingface_model_puller,
        runtime=platform_config.runtime,
    )
