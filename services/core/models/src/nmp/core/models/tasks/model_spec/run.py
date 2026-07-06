# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Model Spec task entry point.

Handles populating model spec in the Model Entity after entity creation.

The task downloads and reads the configuration files, analyzes the checkpoint, and updates the ModelSpec after
analysis

Usage:
    export NEMO_JOB_STEP_CONFIG_FILE_PATH=<path to job_step_config.json>
    python -m nmp.core.models.tasks.model_spec
"""

import json
import logging
import os
from pathlib import Path

from nemo_platform import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    NeMoPlatform,
    NeMoPlatformError,
    NotFoundError,
)
from nemo_platform.types.models import ModelEntity
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient
from nemo_platform_plugin.files.storage_config import HuggingfaceStorageConfig, LocalStorageConfig, NGCStorageConfig
from nemo_platform_plugin.files.types import FilesetOutput
from nmp.common.entities.utils import parse_entity_ref
from nmp.common.model_utils import is_embedding_model
from nmp.common.sdk_factory import get_platform_sdk
from nmp.core.models.config import config as models_config
from nmp.core.models.schemas import ModelSpec, ToolCallConfig
from nmp.core.models.tasks.model_spec.schemas import ModelSpecTaskConfig, NMPJobContext
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

DOWNLOAD_TIMEOUT: float = 2 * 60 * 60  # 2 hours for downloads
DEFAULT_MAX_SEQ_LENGTH = 4096


class ModelSpecCreationError(Exception):
    pass


def get_config(config_path: Path) -> ModelSpecTaskConfig:
    """Get typed task configuration from a config file.

    Loads the JSON config file and validates it against the ModelSpecTaskConfig schema.

    Args:
        config_path: Path to the JSON configuration file.

    Returns:
        Validated ModelSpecTaskConfig.
    """
    with open(config_path) as f:
        data = json.load(f)
        return ModelSpecTaskConfig.model_validate(data)


class ModelSpecRunner:
    """Runner for creating model entities."""

    def __init__(self, sdk: NeMoPlatform, job_ctx: NMPJobContext):
        self.sdk = sdk
        self.job_ctx = job_ctx

    @staticmethod
    def _merge_fileset_metadata(fs: FilesetOutput, model_spec: ModelSpec) -> None:
        """Merge tool calling metadata from fileset into model spec.

        Users can set these values on the fileset at creation time via metadata:
            files = client_from_platform(sdk, FilesClient)
            files.create_fileset(
                body=CreateFilesetRequest(
                    ...,
                    metadata={
                        "model": {
                            "tool_calling": {
                                "chat_template": "<jinja2 template>",
                                "tool_call_parser": "llama3_json",
                                "tool_call_plugin": "default/my-plugin-fileset",
                                "auto_tool_choice": True,
                            },
                        },
                    },
                ),
            )

        The model spec task then merges these into the auto-generated ModelSpec so
        that downstream backends (Docker / K8s) can read them from model_entity.spec.

        Args:
            fs: The fileset object retrieved from the Files API.
            model_spec: The ModelSpec being built — modified in place.
        """
        if not fs.metadata:
            return

        if not fs.metadata.model:
            return

        tc = fs.metadata.model.tool_calling
        if not tc:
            return

        if tc.chat_template:
            model_spec.chat_template = tc.chat_template
            logger.info("Merged chat_template from fileset metadata into model spec")

        plugin = tc.tool_call_plugin
        if plugin and not models_config.tool_call_plugin.enabled:
            logger.warning(
                "Ignoring tool_call_plugin from fileset metadata — tool_call_plugin is disabled at the platform level"
            )
            plugin = None

        if tc.tool_call_parser or plugin or tc.auto_tool_choice is not None:
            model_spec.tool_call_config = ToolCallConfig(
                tool_call_parser=tc.tool_call_parser,
                tool_call_plugin=plugin,
                auto_tool_choice=tc.auto_tool_choice,
            )
            logger.info("Merged tool_call_config from fileset metadata into model spec")

    @staticmethod
    def _merge_existing_spec(me: ModelEntity, model_spec: ModelSpec) -> None:
        """Preserve user-set fields from the model entity's existing spec.

        The auto-generated spec and fileset metadata take precedence. This only
        fills in fields that are still None after those steps, so anything the
        user (or another task) previously set on the entity is not lost.
        """
        if me.spec is None:
            return

        if model_spec.chat_template is None and me.spec.chat_template:
            model_spec.chat_template = me.spec.chat_template
            logger.info("Preserved chat_template from existing model spec")

        if model_spec.tool_call_config is None and me.spec.tool_call_config:
            model_spec.tool_call_config = ToolCallConfig.model_validate(me.spec.tool_call_config.model_dump())
            logger.info("Preserved tool_call_config from existing model spec")

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=INITIAL_BACKOFF_SECONDS, max=MAX_BACKOFF_SECONDS),
        retry=retry_if_exception_type((InternalServerError, APITimeoutError, APIConnectionError)),
        reraise=True,
    )
    def analyze_checkpoint(self, config: ModelSpecTaskConfig) -> ModelEntity:
        """Downloads the checkpoint, validates the
         checkpoint and populates the ModelSpec on the model entity

        Args:
            config: Configuration for the model entity to create.

        Returns:
            Created model entity data.

        Raises:
            ModelSpecCreationError: If creation fails.
        """
        from nmp.core.models.parallelism.api import find_minimum_gpus_from_metadata, infer_model_cfg_from_hf

        logger.info(f"Fetching model entity: {config.workspace}/{config.name}")

        try:
            me = self.sdk.models.retrieve(config.name, workspace=config.workspace, verbose=True)
        except NotFoundError as err:
            raise ModelSpecCreationError(
                f"Failed to create model spec: model entity {config.workspace}/{config.name} does not exist"
            ) from err
        except NeMoPlatformError as err:
            raise ModelSpecCreationError(
                f"Failed to create model spec: model entity {config.workspace}/{config.name} unable to be fetched"
            ) from err

        if not me.fileset:
            raise ModelSpecCreationError(
                f"Cannot create model spec: fileset for model entity undefined '{config.workspace}/{config.name}' does not exist or is not accessible"
            )

        fileset_ref = me.fileset.removeprefix("fileset://")
        try:
            parsed_ref = parse_entity_ref(fileset_ref, config.workspace)
        except ValueError as err:
            raise ModelSpecCreationError(
                f"Cannot create model spec: fileset reference '{me.fileset}' is invalid: {err}"
            ) from err
        fileset_workspace = parsed_ref.workspace
        fileset_name = parsed_ref.name

        # Validate that the fileset exists before creating the model entity
        logger.info(f"Validating fileset exists: {fileset_workspace}/{fileset_name}")
        try:
            files = client_from_platform(self.sdk, FilesClient)
            fs = files.get_fileset(workspace=fileset_workspace, name=fileset_name).data()
            logger.info(f"Fileset validation successful: {fileset_workspace}/{fileset_name}")
        except Exception as e:
            logger.error(f"Fileset validation failed: {fileset_workspace}/{fileset_name}")
            raise ModelSpecCreationError(
                f"Cannot create model entity: fileset '{fileset_workspace}/{fileset_name}' does not exist or is not accessible"
            ) from e

        dest_dir: Path = self.job_ctx.storage_path / "model"

        response = self.sdk.files.list(
            fileset=fs.name,
            workspace=fs.workspace,
        )
        all_file_paths = [f.path for f in response.data]
        non_tensor_files = []
        binary_suffixes = (
            ".safetensor",
            ".safetensors",
            ".bin",
            ".pkl",
            ".npy",
            ".onnx",
            ".pth",
        )
        for f in response.data:
            if f.path.endswith(binary_suffixes):
                logger.warning(f"Skipping binary file {f.path}")
                continue

            non_tensor_files.append(f.path)

        self.sdk.files.download(
            remote_path=non_tensor_files,
            local_path=dest_dir,
            fileset=fs.name,
            workspace=fs.workspace,
        )

        logger.info(os.listdir(dest_dir))
        is_trusted = me.trust_remote_code if me.trust_remote_code is not None else False
        model_spec = infer_model_cfg_from_hf(dest_dir, is_trusted=is_trusted, file_listing=all_file_paths)
        # Embedding if model name or storage path contains "embed"; use or to avoid
        # overwriting a correct True from model name when storage path lacks "embed"
        model_spec.is_embedding_model = is_embedding_model(me.name)
        if isinstance(fs.storage, LocalStorageConfig):
            model_spec.is_embedding_model = model_spec.is_embedding_model or is_embedding_model(fs.storage.path)
        elif isinstance(fs.storage, NGCStorageConfig):
            model_spec.is_embedding_model = model_spec.is_embedding_model or is_embedding_model(fs.storage.target)
        elif isinstance(fs.storage, HuggingfaceStorageConfig):
            model_spec.is_embedding_model = model_spec.is_embedding_model or is_embedding_model(fs.storage.repo_id)

        minimum_gpus_all_weights, _ = find_minimum_gpus_from_metadata(
            model_spec,
            gpu_mem_gb=float(os.getenv("GPU_MEM_GB", "80")),
            seq_len=int(DEFAULT_MAX_SEQ_LENGTH),
            is_trusted=is_trusted,
        )

        minimum_gpus_lora, _ = find_minimum_gpus_from_metadata(
            model_spec,
            gpu_mem_gb=float(os.getenv("GPU_MEM_GB", "80")),
            seq_len=int(DEFAULT_MAX_SEQ_LENGTH),
            is_trusted=is_trusted,
            lora=True,
            lora_r=int(os.getenv("LORA_R", "32")),
        )

        model_spec.minimum_gpus_all_weights = minimum_gpus_all_weights
        model_spec.minimum_gpus_lora = minimum_gpus_lora

        # Merge tool calling metadata from fileset into model spec
        self._merge_fileset_metadata(fs, model_spec)

        # Preserve user-set fields from the existing spec that the auto-generated
        # spec doesn't cover (e.g. tool_call_config set before the task ran).
        self._merge_existing_spec(me, model_spec)

        try:
            me: ModelEntity = self.sdk.models.update(
                name=config.name, workspace=config.workspace, spec=model_spec, verbose=True
            )
        except NotFoundError as err:
            raise ModelSpecCreationError(
                f"Failed to update model spec: model entity {config.workspace}/{config.name} does not exist"
            ) from err
        except NeMoPlatformError as err:
            raise ModelSpecCreationError(
                f"Failed to update model spec: model entity {config.workspace}/{config.name} unable to be fetched"
            ) from err

        return me


def run(*, sdk: NeMoPlatform | None = None, job_ctx: NMPJobContext | None = None) -> int:
    """Execute the model entity creation task.

    Args:
        sdk: Optional SDK instance for dependency injection (for testing).
            If None, creates one via get_platform_sdk().
        job_ctx: Optional job context for dependency injection (for testing).
            If None, creates one via NMPJobContext.from_env().

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    job_ctx = job_ctx or NMPJobContext.from_env()

    sdk_owned = sdk is None
    try:
        sdk = sdk or get_platform_sdk(
            as_service="models",
            internal=True,
        ).with_options(workspace=job_ctx.workspace)
        runner = ModelSpecRunner(sdk=sdk, job_ctx=job_ctx)

        config = get_config(job_ctx.config_path)

        logger.info(f"Starting model spec task with job context: {job_ctx}")
        logger.info(f"Config: {config.model_dump_json(indent=2)}")
        logger.info(f"NeMo Platform service URL: {sdk.base_url}")

        # Create the model spec
        result = runner.analyze_checkpoint(config)

        logger.info(
            f"Model spec creation complete: {result.spec.model_dump_json(indent=2) if result.spec else 'No spec'}"
        )
        return 0

    except Exception as e:
        logger.exception(f"Model spec task failed: {e}")
        return 1
    finally:
        if sdk_owned and sdk is not None:
            sdk.close()
