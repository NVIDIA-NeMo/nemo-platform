# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Model entity task entry point.

Handles creating model entities in the Models service after customization completes.

The task reads configuration and creates a Model Entity that references the
uploaded model artifacts in the Files service.

Usage:
    export NEMO_JOB_STEP_CONFIG_FILE_PATH=<path to job_step_config.json>
    python -m nmp.customizer.tasks.model_entity
"""

import json
import logging
import re
import time
from pathlib import Path

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
from nmp.common.sdk_factory import get_task_sdk
from nmp.customizer.app.constants import SERVICE_NAME
from nmp.customizer.app.jobs.context import NMPJobContext
from nmp.customizer.app.jobs.model_entity.schemas import (
    DeploymentParameters,
    ModelEntityCreationError,
    ModelEntityTaskConfig,
)
from nmp.customizer.entities.values import FinetuningType
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

ACTIVE_DEPLOYMENT_STATUSES = frozenset({"CREATED", "PENDING", "READY"})

SPEC_POLL_INTERVAL_SECONDS = 10
SPEC_POLL_TIMEOUT_SECONDS = 600


def get_config(config_path: Path) -> ModelEntityTaskConfig:
    """Get typed task configuration from a config file.

    Loads the JSON config file and validates it against the ModelEntityTaskConfig schema.

    Args:
        config_path: Path to the JSON configuration file.

    Returns:
        Validated ModelEntityTaskConfig.
    """
    with open(config_path) as f:
        data = json.load(f)
        return ModelEntityTaskConfig.model_validate(data)


def sanitize_name(prefix: str, name: str) -> str:
    """Sanitize model_name: keep only allowed chars, replace invalid with hyphen, avoid consecutive/trailing hyphens

    Must be compatible with - {'pattern': '^[a-z](?!.*--)[a-z0-9\\-@.+_]{1,62}(?<!-)$'}
    """
    sanitized = re.sub(r"[^a-z0-9@.+_-]", "-", name.lower())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return f"{prefix}-{sanitized}"[:59].rstrip("-")  # backend is adding `-v1` to names


class ModelEntityRunner:
    """Runner for creating model entities."""

    def __init__(self, sdk: NeMoPlatform, job_ctx: NMPJobContext):
        self.sdk = sdk
        self.job_ctx = job_ctx

    def _wait_for_spec(self, workspace: str, name: str) -> ModelEntity:
        """Poll until the model_spec task has populated the model's spec.

        The spec must be populated before creating a deployment because the
        inference service relies on ``spec.family`` and ``spec.base_num_parameters``
        to select the correct NIM profile.

        Raises:
            ModelEntityCreationError: If the spec is not populated within the timeout.
        """
        logger.info(f"Waiting for model_spec to populate spec on {workspace}/{name}")
        start = time.monotonic()

        while time.monotonic() - start < SPEC_POLL_TIMEOUT_SECONDS:
            try:
                target = self.sdk.models.retrieve(name=name, workspace=workspace)
                if target.spec:
                    logger.info(f"Spec populated on {workspace}/{name}")
                    return target
            except (APIConnectionError, APITimeoutError, InternalServerError) as e:
                logger.warning(f"Transient error polling spec for {workspace}/{name}: {e}")
            time.sleep(SPEC_POLL_INTERVAL_SECONDS)

        raise ModelEntityCreationError(
            f"Timed out waiting for model spec on {workspace}/{name} "
            f"after {SPEC_POLL_TIMEOUT_SECONDS}s. The platform could not auto-detect the "
            f"model's specifications. Verify the model checkpoint is valid and in a supported format."
        )

    def get_model_entity(self, model_entity: str, fileset_workspace: str) -> ModelEntity:
        parts = model_entity.split("/")
        if len(parts) == 1:
            me_workspace = fileset_workspace
            me_name = parts[0]
        else:
            me_workspace = parts[0]
            me_name = parts[1]

        try:
            me: ModelEntity = self.sdk.models.retrieve(name=me_name, workspace=me_workspace)
        except NotFoundError as e:
            raise ModelEntityCreationError(f"Model entity {me_workspace}/{me_name} not found") from e

        return me

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=INITIAL_BACKOFF_SECONDS, max=MAX_BACKOFF_SECONDS),
        retry=retry_if_exception_type((InternalServerError, APITimeoutError, APIConnectionError)),
        reraise=True,
    )
    def create_model_entity(self, config: ModelEntityTaskConfig) -> tuple[dict, ModelEntity]:
        """Create a model entity in the Models service.

        Args:
            config: Configuration for the model entity to create.

        Returns:
            Tuple of (result dict, deploy target). For LoRA the deploy target is the
            base model entity; for SFT it is the newly created output model entity.

        Raises:
            ModelEntityCreationError: If creation fails.
        """
        workspace = self.job_ctx.workspace
        logger.info(f"Creating model entity: {workspace}/{config.name}")

        fileset_workspace = config.fileset.workspace or workspace
        fileset_ref = f"{fileset_workspace}/{config.fileset.name}"

        logger.info(f"Validating fileset exists: {fileset_workspace}/{config.fileset.name}")
        try:
            self.sdk.files.filesets.retrieve(workspace=fileset_workspace, name=config.fileset.name)
            logger.info(f"Fileset validation successful: {fileset_workspace}/{config.fileset.name}")
        except Exception as e:
            logger.error(f"Fileset validation failed: {fileset_workspace}/{config.fileset.name}")
            raise ModelEntityCreationError(
                f"Cannot create model entity: fileset '{fileset_workspace}/{config.fileset.name}' does not exist or is not accessible"
            ) from e

        base_me: ModelEntity = self.get_model_entity(config.model_entity, fileset_workspace)

        if config.peft is not None and config.peft.type == FinetuningType.LORA:
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
                    f"adapter {base_me.workspace}/{config.name} already exists for model {base_me.workspace}/{base_me.name}, updating with new fileset"
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
                        f"Successfully updated adapter: {base_me.workspace}/{config.name} for base model {base_me.workspace}/{base_me.name}"
                    )
                    return output_me.model_dump(), base_me
                except (InternalServerError, APITimeoutError, APIConnectionError):
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
        else:
            ft_type = config.peft.type.value if config.peft else FinetuningType.ALL_WEIGHTS.value

            request_body = {
                "name": config.name,
                "description": config.description,
                "fileset": fileset_ref,
                "finetuning_type": ft_type,
                "trust_remote_code": base_me.trust_remote_code,
            }

            if config.base_model:
                request_body["base_model"] = config.base_model

            try:
                output_me = self.sdk.models.create(
                    workspace=workspace,
                    **request_body,
                )
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
                except (InternalServerError, APITimeoutError, APIConnectionError):
                    raise
                except Exception as update_error:
                    logger.exception(f"Failed to update existing model entity: {update_error}")
                    raise ModelEntityCreationError(
                        f"Model entity '{config.name}' already exists and update failed: {update_error}"
                    ) from update_error

            except Exception as e:
                logger.exception(f"Failed to create model entity: {e}")
                raise ModelEntityCreationError(f"Failed to create model entity: {e}") from e

    def launch_model(self, config: ModelEntityTaskConfig, me: ModelEntity):
        """Deploy a model entity after creation.

        For LoRA jobs, ``me`` should be the base model entity.
        For SFT jobs, ``me`` should be the output model entity.
        """
        dc = config.deployment_config
        if dc is None:
            return

        # LORA_MERGED produces a full-weight model, so it is deployed like SFT
        # and intentionally excluded from LoRA-specific checks below.
        is_lora = config.peft is not None and config.peft.type == FinetuningType.LORA
        if is_lora and self._has_active_deployment(me):
            return

        if is_lora and isinstance(dc, DeploymentParameters) and not dc.lora_enabled:
            logger.warning(f"Deployment requested but lora_enabled is false for a LoRA job: {dc}")
            return

        # Resolve an existing config or create a new one from inline params.
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
        """Resolve a ``name`` or ``workspace/name`` reference to a ModelDeploymentConfig."""
        parts = config_ref.split("/")
        if len(parts) == 2:
            workspace = parts[0]
            name = parts[1]
        elif len(parts) == 1:
            workspace = me_workspace
            name = parts[0]
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
        """Create (or update) a ModelDeploymentConfig from inline parameters."""
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
        """Create a deployment from the given ModelDeploymentConfig."""
        logger.info(f"Deployment config: {deployment_config}")

        if not me.spec:
            _ = self._wait_for_spec(me.workspace, me.name)

        deployment_name = sanitize_name("sft-deploy", me.name)
        try:
            deployment = self.sdk.inference.deployments.create(
                workspace=deployment_config.workspace,
                name=deployment_name,
                config=deployment_config.name,
            )
            logger.info(f"Deployment created: {deployment}")
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
        logger.info(f"Deployment status: {deployment_status}")


def run(*, sdk: NeMoPlatform | None = None, job_ctx: NMPJobContext | None = None) -> int:
    """Execute the model entity creation task.

    Args:
        sdk: Optional SDK instance for dependency injection (for testing).
            If None, creates one via get_task_sdk().
        job_ctx: Optional job context for dependency injection (for testing).
            If None, creates one via NMPJobContext.from_env().

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    job_ctx = job_ctx or NMPJobContext.from_env()

    sdk_owned = sdk is None
    try:
        sdk = sdk or get_task_sdk(SERVICE_NAME).with_options(workspace=job_ctx.workspace)
        runner = ModelEntityRunner(sdk=sdk, job_ctx=job_ctx)

        config = get_config(job_ctx.config_path)

        logger.info(f"Starting model entity task with job context: {job_ctx}")
        logger.info(f"Config: {config.model_dump_json(indent=2)}")
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
