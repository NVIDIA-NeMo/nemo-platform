# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Model entity task entry point.

Usage:
    export NEMO_JOB_STEP_CONFIG_FILE_PATH=<path to job_step_config.json>
    python -m nmp.customization_common.tasks.model_entity --service-name customizer
"""

import json
import logging
import re
import time
from pathlib import Path

import httpx
from nemo_platform import (
    APIConnectionError,
    APITimeoutError,
    ConflictError,
    InternalServerError,
    NeMoPlatform,
    NotFoundError,
)
from nemo_platform.types.inference import (
    ContainerExecutorConfigParam,
    ModelDeploymentConfig,
    ModelDeploymentConfigFilterParam,
    ModelDeploymentConfigModelSpecParam,
    ModelDeploymentFilterParam,
)
from nemo_platform.types.models import LoraParam, ModelEntity
from nemo_platform.types.shared_params.tool_call_config import ToolCallConfig as ToolCallConfigParam
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import InternalServerError as ClientInternalServerError
from nemo_platform_plugin.files.client import FilesClient
from nmp.common.sdk_factory import get_task_sdk
from nmp.customization_common.schemas.model_entity import (
    DeploymentParameters,
    ModelEntityCreationError,
    ModelEntityTaskConfig,
)
from nmp.customization_common.schemas.values import FinetuningType
from nmp.customization_common.service.context import NMPJobContext
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

ACTIVE_DEPLOYMENT_STATUSES = frozenset({"CREATED", "PENDING", "READY"})

SPEC_POLL_INTERVAL_SECONDS = 10
SPEC_POLL_TIMEOUT_SECONDS = 600

TRANSIENT_RETRYABLE_EXCEPTIONS = (
    InternalServerError,
    APITimeoutError,
    APIConnectionError,
    ClientInternalServerError,
    httpx.TimeoutException,
    httpx.ConnectError,
)


def get_config(config_path: Path) -> ModelEntityTaskConfig:
    """Load and validate the model_entity step config from disk."""
    with open(config_path) as f:
        return ModelEntityTaskConfig.model_validate(json.load(f))


def sanitize_name(prefix: str, name: str) -> str:
    """Build a deployment-safe name from a free-form model name."""
    sanitized = re.sub(r"[^a-z0-9@.+_-]", "-", name.lower())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return f"{prefix}-{sanitized}"[:59].rstrip("-")


class ModelEntityRunner:
    """Runner for creating (and optionally deploying) model entities."""

    def __init__(self, sdk: NeMoPlatform, job_ctx: NMPJobContext):
        self.sdk = sdk
        self.job_ctx = job_ctx

    def _wait_for_spec(self, workspace: str, name: str) -> ModelEntity:
        """Poll until the model_spec task has populated the model's spec."""
        logger.info(f"Waiting for model_spec to populate spec on {workspace}/{name}")
        start = time.monotonic()

        while time.monotonic() - start < SPEC_POLL_TIMEOUT_SECONDS:
            try:
                target = self.sdk.models.retrieve(name=name, workspace=workspace)
                spec = target.spec
                if spec is not None:
                    family = getattr(spec, "family", None)
                    base_num_parameters = getattr(spec, "base_num_parameters", None)
                    if family and base_num_parameters is not None:
                        logger.info(f"Spec populated on {workspace}/{name}")
                        return target
                    raise ModelEntityCreationError(
                        f"Model spec on {workspace}/{name} is missing required fields: "
                        "family and base_num_parameters must be set (typically by the "
                        "platform model_spec task). Verify the model checkpoint is valid "
                        "and in a supported format."
                    )
            except ModelEntityCreationError:
                raise
            except TRANSIENT_RETRYABLE_EXCEPTIONS as e:
                logger.warning(f"Transient error polling spec for {workspace}/{name}: {e}")
            time.sleep(SPEC_POLL_INTERVAL_SECONDS)

        raise ModelEntityCreationError(
            f"Timed out waiting for model spec on {workspace}/{name} "
            f"after {SPEC_POLL_TIMEOUT_SECONDS}s. The platform could not auto-detect the "
            f"model's specifications. Verify the model checkpoint is valid and in a supported format."
        )

    def get_model_entity(self, model_entity: str, fileset_workspace: str) -> ModelEntity:
        """Resolve ``"workspace/name"`` (or bare ``"name"``) to a ``ModelEntity``."""
        parts = model_entity.split("/")
        if len(parts) == 1 and parts[0]:
            me_workspace, me_name = fileset_workspace, parts[0]
        elif len(parts) == 2 and all(parts):
            me_workspace, me_name = parts[0], parts[1]
        else:
            raise ModelEntityCreationError(
                f"Invalid model entity reference '{model_entity}': expected 'name' or 'workspace/name'."
            )

        try:
            me: ModelEntity = self.sdk.models.retrieve(name=me_name, workspace=me_workspace)
        except NotFoundError as e:
            raise ModelEntityCreationError(f"Model entity {me_workspace}/{me_name} not found") from e

        return me

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=INITIAL_BACKOFF_SECONDS, max=MAX_BACKOFF_SECONDS),
        retry=retry_if_exception_type(TRANSIENT_RETRYABLE_EXCEPTIONS),
        reraise=True,
    )
    def create_model_entity(self, config: ModelEntityTaskConfig) -> tuple[dict, ModelEntity]:
        """Create a model entity in the Models service."""
        output_workspace = config.workspace
        logger.info(f"Creating model entity: {output_workspace}/{config.name}")

        fileset_workspace = config.fileset.workspace or self.job_ctx.workspace
        fileset_ref = f"{fileset_workspace}/{config.fileset.name}"

        logger.info(f"Validating fileset exists: {fileset_workspace}/{config.fileset.name}")
        try:
            client_from_platform(self.sdk, FilesClient).get_fileset(
                workspace=fileset_workspace, name=config.fileset.name
            )
            logger.info(f"Fileset validation successful: {fileset_workspace}/{config.fileset.name}")
        except TRANSIENT_RETRYABLE_EXCEPTIONS:
            raise
        except Exception as e:
            logger.error(f"Fileset validation failed: {fileset_workspace}/{config.fileset.name}")
            raise ModelEntityCreationError(
                f"Cannot create model entity: fileset '{fileset_workspace}/{config.fileset.name}' "
                "does not exist or is not accessible"
            ) from e

        base_me: ModelEntity = self.get_model_entity(config.model_entity, fileset_workspace)

        if config.peft is not None and config.peft.type == FinetuningType.LORA:
            return self._create_or_update_adapter(config, base_me, fileset_ref)
        return self._create_or_update_full_entity(config, fileset_ref, output_workspace)

    def _create_or_update_adapter(
        self,
        config: ModelEntityTaskConfig,
        base_me: ModelEntity,
        fileset_ref: str,
    ) -> tuple[dict, ModelEntity]:
        """Create or update a LoRA adapter on ``base_me``. Returns (result, base_me)."""
        assert config.peft is not None
        try:
            output_me = self.sdk.models.adapters.create(
                model_name=base_me.name,
                workspace=base_me.workspace,
                name=config.name,
                description=config.description,
                fileset=fileset_ref,
                finetuning_type=config.peft.type.value,
                lora_config=LoraParam(
                    alpha=config.peft.alpha,
                    rank=config.peft.rank,
                ),
                enabled=True,
            )
            return output_me.model_dump(), base_me
        except ConflictError:
            logger.warning(
                f"Adapter {base_me.workspace}/{config.name} already exists for model "
                f"{base_me.workspace}/{base_me.name}, updating with new fileset"
            )
            try:
                output_me = self.sdk.models.adapters.update(
                    adapter=config.name,
                    model_name=base_me.name,
                    workspace=base_me.workspace,
                    fileset=fileset_ref,
                    description=config.description,
                    enabled=True,
                )
                logger.info(
                    f"Successfully updated adapter: {base_me.workspace}/{config.name} "
                    f"for base model {base_me.workspace}/{base_me.name}"
                )
                return output_me.model_dump(), base_me
            except TRANSIENT_RETRYABLE_EXCEPTIONS:
                raise
            except Exception as update_error:
                logger.exception(
                    f"Failed to update existing adapter, {base_me.workspace}/{config.name}: {update_error}"
                )
                raise ModelEntityCreationError(
                    f"Adapter '{config.name}' already exists but update failed: {update_error}"
                ) from update_error
        except Exception as e:
            logger.exception(f"Failed to create model adapter: {e}")
            raise ModelEntityCreationError(f"Failed to create model adapter: {e}") from e

    def _create_or_update_full_entity(
        self,
        config: ModelEntityTaskConfig,
        fileset_ref: str,
        workspace: str,
    ) -> tuple[dict, ModelEntity]:
        """Create or update a full / merged model entity. Returns (result, output_me)."""
        ft_type = config.peft.type.value if config.peft else FinetuningType.ALL_WEIGHTS.value

        request_body: dict = {
            "name": config.name,
            "description": config.description,
            "fileset": fileset_ref,
            "finetuning_type": ft_type,
            "trust_remote_code": config.trust_remote_code,
        }
        if config.base_model:
            request_body["base_model"] = config.base_model

        try:
            output_me = self.sdk.models.create(workspace=workspace, **request_body)
            logger.info(f"Successfully created model entity: {output_me.workspace}/{output_me.name}")
            return output_me.model_dump(), output_me
        except ConflictError:
            logger.warning(f"Model entity already exists: {workspace}/{config.name}, updating existing model")
            try:
                update_body = {k: v for k, v in request_body.items() if k != "name"}
                output_me = self.sdk.models.update(
                    name=config.name,
                    workspace=workspace,
                    **update_body,
                )
                logger.info(f"Successfully updated model entity: {output_me.workspace}/{output_me.name}")
                return output_me.model_dump(), output_me
            except TRANSIENT_RETRYABLE_EXCEPTIONS:
                raise
            except Exception as update_error:
                logger.exception(f"Failed to update existing model entity: {update_error}")
                raise ModelEntityCreationError(
                    f"Model entity '{config.name}' already exists and update failed: {update_error}"
                ) from update_error
        except Exception as e:
            logger.exception(f"Failed to create model entity: {e}")
            raise ModelEntityCreationError(f"Failed to create model entity: {e}") from e

    def launch_model(self, config: ModelEntityTaskConfig, me: ModelEntity) -> None:
        """Deploy a model entity after creation."""
        dc = config.deployment_config
        if dc is None:
            return

        is_lora = config.peft is not None and config.peft.type == FinetuningType.LORA
        if is_lora and self._has_active_deployment(me):
            return

        if is_lora and isinstance(dc, DeploymentParameters) and not dc.lora_enabled:
            logger.warning(f"Deployment requested but lora_enabled is false for a LoRA job: {dc}")
            return

        if isinstance(dc, str):
            logger.info(f"Resolving deployment config reference: {dc}")
            deployment_config = self._resolve_config_ref(dc, me.workspace)
            logger.info(f"Using deployment config: {deployment_config.workspace}/{deployment_config.name}")
        else:
            deployment_config = self._create_deployment_config(dc, me)

        self._create_deployment(deployment_config, me)

    def _has_active_deployment(self, me: ModelEntity) -> bool:
        """Check if the model entity already has an active deployment."""
        deployment_configs = self.sdk.inference.deployment_configs.list(
            workspace=me.workspace,
            filter=ModelDeploymentConfigFilterParam(model_entity_id=f"{me.workspace}/{me.name}"),
        ).data

        for c in deployment_configs:
            deployments = self.sdk.inference.deployments.list(
                filter=ModelDeploymentFilterParam(config=c.name, workspace=me.workspace)
            ).data
            for d in deployments:
                if d.status in ACTIVE_DEPLOYMENT_STATUSES:
                    logger.info(f"Active deployment (status={d.status}) exists for config {c.name}, skipping")
                    return True

        return False

    def _resolve_config_ref(self, config_ref: str, me_workspace: str) -> ModelDeploymentConfig:
        """Resolve a ``name`` or ``workspace/name`` reference to a ``ModelDeploymentConfig``."""
        parts = config_ref.split("/")
        if len(parts) == 2:
            workspace, name = parts[0], parts[1]
        elif len(parts) == 1:
            workspace, name = me_workspace, parts[0]
        else:
            raise ModelEntityCreationError(
                f"Invalid deployment config reference '{config_ref}': expected 'name' or 'workspace/name'"
            )

        try:
            return self.sdk.inference.deployment_configs.retrieve(workspace=workspace, name=name)
        except Exception as e:
            raise ModelEntityCreationError(
                f"Failed to resolve deployment config '{config_ref}' in workspace '{workspace}': {e}"
            ) from e

    def _create_deployment_config(self, deploy_params: DeploymentParameters, me: ModelEntity) -> ModelDeploymentConfig:
        """Create (or update) a ``ModelDeploymentConfig`` from inline parameters."""
        model_spec = ModelDeploymentConfigModelSpecParam(
            model_name=me.name,
            model_namespace=me.workspace,
            lora_enabled=deploy_params.lora_enabled,
        )
        executor_config = ContainerExecutorConfigParam(
            image_name=deploy_params.image_name,
            image_tag=deploy_params.image_tag,
            gpu=deploy_params.gpu,
            additional_envs=deploy_params.additional_envs,
        )

        if deploy_params.tool_call_config:
            model_spec["tool_call_config"] = ToolCallConfigParam(
                **deploy_params.tool_call_config.model_dump(exclude_none=True)
            )

        deployment_cfg_name = sanitize_name("sft-cfg", me.name)
        try:
            return self.sdk.inference.deployment_configs.create(
                workspace=me.workspace,
                name=deployment_cfg_name,
                engine="nim",
                model_spec=model_spec,
                executor_config=executor_config,
            )
        except ConflictError:
            logger.info(f"Deployment config {me.workspace}/{deployment_cfg_name} already exists, updating")
            return self.sdk.inference.deployment_configs.update(
                workspace=me.workspace,
                name=deployment_cfg_name,
                engine="nim",
                model_spec=model_spec,
                executor_config=executor_config,
            )

    def _create_deployment(self, deployment_config: ModelDeploymentConfig, me: ModelEntity) -> None:
        """Create a deployment from the given ``ModelDeploymentConfig``."""
        logger.info(f"Using deployment config: {deployment_config.workspace}/{deployment_config.name}")

        if not me.spec:
            _ = self._wait_for_spec(me.workspace, me.name)

        deployment_name = sanitize_name("sft-deploy", me.name)
        try:
            deployment = self.sdk.inference.deployments.create(
                workspace=deployment_config.workspace,
                name=deployment_name,
                config=deployment_config.name,
            )
            logger.info(f"Deployment created: {deployment.workspace}/{deployment.name}")
        except ConflictError:
            logger.info(f"Deployment {deployment_config.workspace}/{deployment_name} already exists")
            deployment = self.sdk.inference.deployments.retrieve(
                workspace=deployment_config.workspace,
                name=deployment_name,
            )

        deployment_status = self.sdk.inference.deployments.retrieve(
            workspace=deployment.workspace,
            name=deployment.name,
        )
        logger.info(
            f"Deployment {deployment_status.workspace}/{deployment_status.name} status: {deployment_status.status}"
        )


def run(
    sdk: NeMoPlatform | None = None,
    job_ctx: NMPJobContext | None = None,
    *,
    service_name: str,
) -> int:
    """Execute the model entity creation task."""
    job_ctx = job_ctx or NMPJobContext.from_env()

    sdk_owned = sdk is None
    try:
        sdk = sdk or get_task_sdk(service_name).with_options(workspace=job_ctx.workspace)
        runner = ModelEntityRunner(sdk=sdk, job_ctx=job_ctx)

        config = get_config(job_ctx.config_path)

        logger.info(
            "Starting model entity task: job_id=%s, name=%s, workspace=%s, fileset=%s/%s, deployment_configured=%s",
            job_ctx.job_id,
            config.name,
            config.workspace,
            config.fileset.workspace or job_ctx.workspace,
            config.fileset.name,
            config.deployment_config is not None,
        )
        logger.info(f"NeMo Platform service URL: {sdk.base_url}")

        result, deploy_target = runner.create_model_entity(config)
        logger.info(f"Model entity creation complete: {result}")

        runner.launch_model(config, deploy_target)
        return 0

    except ModelEntityCreationError as e:
        logger.exception(f"Model entity creation failed: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Model entity task failed: {e}")
        return 1
    finally:
        if sdk_owned and sdk is not None:
            sdk.close()
