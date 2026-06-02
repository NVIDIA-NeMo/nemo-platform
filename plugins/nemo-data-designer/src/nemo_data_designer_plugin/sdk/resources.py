# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import logging
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Generic, TypeVar

import data_designer.config as dd
import httpx
import pandas as pd
from data_designer.config.analysis.dataset_profiler import DatasetProfilerResults
from data_designer.config.dataset_metadata import DatasetMetadata
from data_designer.config.preview_results import PreviewResults
from data_designer.config.utils.info import InterfaceInfo
from data_designer.logging import RandomEmoji
from data_designer_nemo.errors import NDDInvalidConfigError
from data_designer_nemo.unsupported_features import validate_remote_seed_type
from nemo_data_designer_plugin.functions._types import (
    AnalysisFrame,
    DatasetFrame,
    DatasetMetadataFrame,
    LogFrame,
    PreviewFrame,
    PreviewSpec,
    ProcessorOutputFrame,
)
from nemo_data_designer_plugin.jobs.spec import DataDesignerJobConfig
from nemo_data_designer_plugin.sdk import http
from nemo_data_designer_plugin.sdk.errors import (
    DataDesignerClientError,
    DataDesignerConfigValidationError,
    DataDesignerPreviewError,
    extract_http_error_info,
)
from nemo_data_designer_plugin.sdk.job_resources import AsyncDataDesignerJobResource, DataDesignerJobResource
from nemo_data_designer_plugin.sdk.logging import with_logging
from nemo_data_designer_plugin.sdk.validation import (
    ExecutionContext,
    ValidationReport,
    validate_config,
    validate_config_sync,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.models.resources import AsyncModelsResource, ModelsResource
from nemo_platform.types.inference import ModelProvider as NMPModelProvider
from nemo_platform_plugin.functions.frames import Done, Error, Heartbeat
from nemo_platform_plugin.sdk import NemoPluginSDKResources
from pydantic import BaseModel, TypeAdapter

logger = logging.getLogger(__name__)

PlatformResourceClient = NeMoPlatform | AsyncNeMoPlatform
PlatformResourceClientT = TypeVar("PlatformResourceClientT", NeMoPlatform, AsyncNeMoPlatform)

_PREVIEW_FRAME_ADAPTER = TypeAdapter(PreviewFrame)
_KNOWN_PREVIEW_FRAME_KINDS = {
    "analysis",
    "dataset",
    "dataset_metadata",
    "done",
    "error",
    "heartbeat",
    "log",
    "processor_output",
}


def _decode_preview_frame(line: str) -> PreviewFrame | None:
    payload = json.loads(line)
    if not isinstance(payload, dict):
        logger.debug("Ignoring non-object preview frame: %r", payload)
        return None
    return _parse_preview_payload(payload)


def _parse_preview_frame(frame: BaseModel) -> PreviewFrame | None:
    return _parse_preview_payload(frame.model_dump(mode="json"))


def _parse_preview_payload(payload: Mapping[str, Any]) -> PreviewFrame | None:
    kind = payload.get("kind")
    if kind not in _KNOWN_PREVIEW_FRAME_KINDS:
        logger.debug("Ignoring unknown preview frame kind: %s", kind)
        return None
    return _PREVIEW_FRAME_ADAPTER.validate_python(payload)


@dataclass
class _PreviewFrameCollector:
    """Collect and validate frames from the streaming preview response."""

    dataset: pd.DataFrame | None = None
    dataset_metadata: DatasetMetadata | None = None
    analysis: DatasetProfilerResults | None = None
    processor_artifacts: dict[str, list[dict]] = field(default_factory=dict)
    log_levels_seen: set[str] = field(default_factory=set)

    def __enter__(self):
        logger.info("🚀 Starting preview generation")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        if isinstance(exc_val, DataDesignerPreviewError):
            raise exc_val
        if exc_val:
            raise _get_error(exc_val)
        if self.dataset is None:
            raise DataDesignerPreviewError("No dataset generated. Check the logs for details about what failed.")
        if self.dataset_metadata is None:
            raise DataDesignerPreviewError(
                "No dataset metadata received. Check the logs for details about what failed."
            )
        if self.analysis is None:
            raise DataDesignerPreviewError("No analysis received. Check the logs for details about what failed.")
        self._log_end_preview()

    def accept(self, frame: BaseModel) -> None:
        preview_frame = _parse_preview_frame(frame)
        if preview_frame is None:
            return

        match preview_frame:
            case LogFrame():
                self._accept_log(preview_frame)
            case DatasetFrame():
                self._accept_dataset(preview_frame)
            case DatasetMetadataFrame():
                self._accept_dataset_metadata(preview_frame)
            case AnalysisFrame():
                self._accept_analysis(preview_frame)
            case ProcessorOutputFrame():
                self._accept_processor_output(preview_frame)
            case Error():
                raise DataDesignerPreviewError(preview_frame.message)
            case Heartbeat() | Done():
                pass

    def _accept_log(self, frame: LogFrame) -> None:
        level = frame.level

        self.log_levels_seen.add(level)

        if level == "debug":
            logger.debug(frame.message)
        elif level == "info":
            logger.info(frame.message)
        elif level in {"warning", "warn"}:
            logger.warning(frame.message)
        elif level == "error":
            logger.error(frame.message)

    def _accept_dataset(self, frame: DatasetFrame) -> None:
        # The dataset is mission-critical. If we can't load it from the message,
        # or we can but the dataset is empty, raise a preview error.
        try:
            self.dataset = pd.DataFrame(frame.records).convert_dtypes(dtype_backend="pyarrow")
        except Exception as e:
            raise DataDesignerPreviewError(f"🛑 Error generating preview dataset: {e}") from e

        if len(self.dataset) == 0:
            raise DataDesignerPreviewError(
                "🛑 Dataset is empty — all records were dropped due to generation or processing failures. "
                "Check the warnings above for details on which columns failed."
            )

    def _accept_dataset_metadata(self, frame: DatasetMetadataFrame) -> None:
        # Dataset metadata is mission-critical. If we can't load it, raise a preview error.
        try:
            self.dataset_metadata = frame.metadata
        except Exception as e:
            raise DataDesignerPreviewError(f"🛑 Error loading dataset metadata: {e}") from e

    def _accept_analysis(self, frame: AnalysisFrame) -> None:
        # Analysis is mission-critical. If we can't load it, raise a preview error.
        try:
            self.analysis = frame.analysis
        except Exception as e:
            raise DataDesignerPreviewError(f"🛑 Error profiling preview dataset: {e}") from e

    def _accept_processor_output(self, frame: ProcessorOutputFrame) -> None:
        # If a processor artifact fails to deserialize, log it but keep the preview result.
        try:
            self.processor_artifacts[frame.processor_name] = frame.records
        except Exception as e:
            logger.error(f"🛑 Error loading processor output: {e}")
            self.log_levels_seen.add("error")

    def get_processor_artifacts(self) -> dict[str, list[dict]] | None:
        return self.processor_artifacts or None

    def _log_end_preview(self) -> None:
        if "error" in self.log_levels_seen:
            logger.error("🛑 Preview completed with errors.")
        elif "warning" in self.log_levels_seen or "warn" in self.log_levels_seen:
            logger.warning("⚠️ Preview completed with warnings.")
        else:
            logger.info(f"{RandomEmoji.success()} Preview complete!")


class _BaseDataDesignerResource(Generic[PlatformResourceClientT]):
    """Shared HTTP helpers for the sync and async plugin SDK resources."""

    def __init__(self, platform: PlatformResourceClientT) -> None:
        self._platform = platform

    def _headers(self) -> dict[str, str]:
        return http.headers(self._platform)

    def _url(self, path: str, workspace: str | None) -> str:
        return http.url(self._platform, workspace, path)

    def _client(self):
        return self._platform._client


@with_logging
class DataDesignerResource(_BaseDataDesignerResource[NeMoPlatform]):
    """High-level sync client for the Data Designer plugin service."""

    def preview(
        self,
        config_builder: dd.DataDesignerConfigBuilder,
        *,
        num_records: int | None = None,
        workspace: str | None = None,
    ) -> PreviewResults:
        """Generate a set of preview records based on your current Data Designer configuration.

        This method is meant for fast iteration on your Data Designer configuration.

        Args:
            config_builder: Data Designer configuration builder.
            num_records: The number of records to generate. Must be less than or equal to the
                service-side configured max number of preview records.
            workspace: The workspace to run the request in. If not supplied, uses the workspace
                of the base NeMoPlatform object.
            timeout: The timeout for the preview call in seconds.

        Returns:
            An object containing the preview dataset and tools for inspecting the results.
        """
        config = _get_config_for_api_call(config_builder)
        request = PreviewSpec(config=config, num_records=num_records)

        with _PreviewFrameCollector() as message_collector:
            for frame in self._preview(request=request, workspace=workspace):
                message_collector.accept(frame)
            return PreviewResults(
                config_builder=config_builder,
                dataset=message_collector.dataset,
                dataset_metadata=message_collector.dataset_metadata,
                analysis=message_collector.analysis,
                processor_artifacts=message_collector.get_processor_artifacts(),
            )

    def _preview(
        self,
        *,
        request: PreviewSpec,
        workspace: str | None,
    ) -> Iterator[PreviewFrame]:
        with self._client().stream(
            "POST",
            self._url("/preview", workspace),
            headers=self._headers(),
            json=request.model_dump(mode="json", exclude_none=True),
        ) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                resp.read()
                raise
            for line in resp.iter_lines():
                if line:
                    frame = _decode_preview_frame(line)
                    if frame is not None:
                        yield frame

    def create(
        self,
        config_builder: dd.DataDesignerConfigBuilder,
        *,
        num_records: int = 100,
        workspace: str | None = None,
        wait_until_done: bool = False,
    ) -> DataDesignerJobResource:
        """Create a Data Designer generation job.

        Args:
            config_builder: Data Designer configuration builder.
            num_records: The number of records to generate.
            workspace: The workspace in which to run the job. If not supplied, uses
                the workspace of the base NeMoPlatform object.
            wait_until_done: Set to True to poll the job status and block until the
                job reaches a terminal state.

        Returns:
            An object with methods for querying the job's status and results.
        """
        config = _get_config_for_api_call(config_builder)
        request = DataDesignerJobConfig(config=config, num_records=num_records)
        try:
            resp = self._client().post(
                self._url("/jobs/create", workspace),
                headers=self._headers(),
                json={"spec": request.model_dump(mode="json")},
            )
            resp.raise_for_status()
            job = resp.json()
            logger.info(f"  |-- job name: {job['name']}")
            job_client = DataDesignerJobResource(job_name=job["name"], platform=self._platform, workspace=workspace)
            if wait_until_done:
                job_client.wait_until_done()
            return job_client
        except Exception as e:
            raise _get_error(e) from e

    def get_job_resource(self, job_name: str, workspace: str | None = None) -> DataDesignerJobResource:
        """Get a high-level resource for an existing data generation job.

        Args:
            job_name: The name of the job.
            workspace: The workspace in which the job ran.

        Returns:
            An object containing methods for querying job status,
            retrieving the generated dataset, and accessing job metadata.

        Raises:
            ValueError: If the job ID provided is empty.
        """
        resp = self._client().get(self._url(f"/jobs/create/{job_name}", workspace), headers=self._headers())
        resp.raise_for_status()
        return DataDesignerJobResource(job_name=job_name, platform=self._platform, workspace=workspace)

    def get_default_model_configs(self) -> list[dd.ModelConfig]:
        """Default model configs are not supported in the NeMo Platform Data Designer service."""

        return []

    def get_default_model_providers(self) -> list[dd.ModelProvider]:
        """Get the model providers available for inference.

        Returns:
            A list of ModelProvider objects available for inference.
        """
        nmp_providers = self._platform.inference.providers.list(workspace="-")
        return [_nmp_provider_to_ndd_provider(self._platform.models, provider) for provider in nmp_providers]

    def get_info(self) -> InterfaceInfo:
        return InterfaceInfo(model_providers=self.get_default_model_providers())

    def validate(
        self,
        config_builder: dd.DataDesignerConfigBuilder,
        *,
        execution_context: ExecutionContext | None = None,
        workspace: str | None = None,
    ) -> ValidationReport:
        """Validate a Data Designer config against one or every execution context.

        This runs the same client-side checks ``preview`` / ``create`` perform
        internally, but never short-circuits — every detectable problem is
        reported. The remote pass is a client-side simulation and does not
        contact the data-designer service.

        Args:
            config_builder: Data Designer configuration builder.
            execution_context: ``"local"``, ``"remote"``, or ``None``.
                ``None`` (the default) runs every applicable context.
            workspace: Workspace used to resolve provider references and seed
                sources for the remote pass. Falls back to the platform
                client's default workspace, then to ``"default"``.

        Returns:
            A :class:`ValidationReport` whose ``ok`` property is true iff
            every requested context validated cleanly.
        """
        # Don't apply the eager ``_get_config_for_api_call`` rejection that
        # ``preview`` / ``create`` use — the validate pass is *meant* to
        # surface unsupported-seed errors as part of its report, alongside
        # any other problems. Short-circuiting on the first eager check would
        # break aggregation and would also reject ``df``-seed configs that
        # are surfaced cleanly with a helpful message by the validate pass
        # itself (see ``_validate_seed_type_for_execution_context``).
        resolved_workspace = workspace or self._platform.workspace or "default"
        return validate_config_sync(
            config_builder,
            sdk=self._platform,
            workspace=resolved_workspace,
            execution_context=execution_context,
        )


@with_logging
class AsyncDataDesignerResource(_BaseDataDesignerResource[AsyncNeMoPlatform]):
    """High-level async client for the Data Designer plugin service."""

    async def preview(
        self,
        config_builder: dd.DataDesignerConfigBuilder,
        *,
        num_records: int | None = None,
        workspace: str | None = None,
    ) -> PreviewResults:
        """Generate a set of preview records based on your current Data Designer configuration.

        This method is meant for fast iteration on your Data Designer configuration.

        Args:
            config_builder: Data Designer configuration builder.
            num_records: The number of records to generate. Must be less than or equal to the
                service-side configured max number of preview records.
            workspace: The workspace to run the request in. If not supplied, uses the workspace
                of the base NeMoPlatform object.
            timeout: The timeout for the preview call in seconds.

        Returns:
            An object containing the preview dataset and tools for inspecting the results.
        """
        config = _get_config_for_api_call(config_builder)
        request = PreviewSpec(config=config, num_records=num_records)

        with _PreviewFrameCollector() as message_collector:
            async for frame in self._preview(request=request, workspace=workspace):
                message_collector.accept(frame)
            return PreviewResults(
                config_builder=config_builder,
                dataset=message_collector.dataset,
                dataset_metadata=message_collector.dataset_metadata,
                analysis=message_collector.analysis,
                processor_artifacts=message_collector.get_processor_artifacts(),
            )

    async def _preview(
        self,
        *,
        request: PreviewSpec,
        workspace: str | None,
    ) -> AsyncIterator[PreviewFrame]:
        async with self._client().stream(
            "POST",
            self._url("/preview", workspace),
            headers=self._headers(),
            json=request.model_dump(mode="json", exclude_none=True),
        ) as resp:
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                await resp.aread()
                raise
            async for line in resp.aiter_lines():
                if line:
                    frame = _decode_preview_frame(line)
                    if frame is not None:
                        yield frame

    async def create(
        self,
        config_builder: dd.DataDesignerConfigBuilder,
        *,
        num_records: int = 100,
        workspace: str | None = None,
        wait_until_done: bool = False,
    ) -> AsyncDataDesignerJobResource:
        """Create a Data Designer generation job.

        Args:
            config_builder: Data Designer configuration builder.
            num_records: The number of records to generate.
            workspace: The workspace in which to run the job. If not supplied, uses
                the workspace of the base NeMoPlatform object.
            wait_until_done: Set to True to poll the job status and block until the
                job reaches a terminal state.

        Returns:
            An object with methods for querying the job's status and results.
        """
        config = _get_config_for_api_call(config_builder)
        request = DataDesignerJobConfig(config=config, num_records=num_records)
        try:
            resp = await self._client().post(
                self._url("/jobs/create", workspace),
                headers=self._headers(),
                json={"spec": request.model_dump(mode="json")},
            )
            resp.raise_for_status()
            job = resp.json()
            logger.info(f"  |-- job name: {job['name']}")
            job_client = AsyncDataDesignerJobResource(
                job_name=job["name"], platform=self._platform, workspace=workspace
            )
            if wait_until_done:
                await job_client.wait_until_done()
            return job_client
        except Exception as e:
            raise _get_error(e) from e

    async def get_job_resource(self, job_name: str, workspace: str | None = None) -> AsyncDataDesignerJobResource:
        """Get a high-level resource for an existing data generation job.

        Args:
            job_name: The name of the job.
            workspace: The workspace in which the job ran.

        Returns:
            An object containing methods for querying job status,
            retrieving the generated dataset, and accessing job metadata.

        Raises:
            ValueError: If the job ID provided is empty.
        """
        resp = await self._client().get(self._url(f"/jobs/create/{job_name}", workspace), headers=self._headers())
        resp.raise_for_status()
        return AsyncDataDesignerJobResource(job_name=job_name, platform=self._platform, workspace=workspace)

    async def get_default_model_configs(self) -> list[dd.ModelConfig]:
        """Default model configs are not supported in the NeMo Platform Data Designer service."""

        return []

    async def get_default_model_providers(self) -> list[dd.ModelProvider]:
        """Get the model providers available for inference.

        Returns:
            A list of ModelProvider objects available for inference.
        """
        nmp_providers = await self._platform.inference.providers.list(workspace="-")
        return [_nmp_provider_to_ndd_provider(self._platform.models, provider) async for provider in nmp_providers]

    async def get_info(self) -> InterfaceInfo:
        return InterfaceInfo(model_providers=await self.get_default_model_providers())

    async def validate(
        self,
        config_builder: dd.DataDesignerConfigBuilder,
        *,
        execution_context: ExecutionContext | None = None,
        workspace: str | None = None,
    ) -> ValidationReport:
        """Async equivalent of :meth:`DataDesignerResource.validate`."""
        # See the sync ``DataDesignerResource.validate`` docstring for why we
        # bypass ``_get_config_for_api_call`` here.
        resolved_workspace = workspace or self._platform.workspace or "default"
        return await validate_config(
            config_builder,
            async_sdk=self._platform,
            workspace=resolved_workspace,
            execution_context=execution_context,
        )


def _get_config_for_api_call(config_builder: dd.DataDesignerConfigBuilder) -> dd.DataDesignerConfig:
    """Build the config and reject unsupported local-only seed source types."""

    if (seed_config := config_builder.get_seed_config()) is not None:
        try:
            validate_remote_seed_type(seed_config.source.seed_type)
        except NDDInvalidConfigError as exc:
            raise DataDesignerConfigValidationError(str(exc)) from exc
    return config_builder.build()


def _get_error(e: BaseException) -> DataDesignerClientError:
    if isinstance(e, httpx.HTTPStatusError):
        status_code, detail = extract_http_error_info(e)
        if status_code == 422:
            return DataDesignerConfigValidationError(f"‼️ Config validation failed!\n{detail}", status_code=status_code)
        return DataDesignerClientError(f"‼️ Something went wrong!\n{detail}", status_code=status_code)
    return DataDesignerClientError(f"‼️ Something went wrong!\n{e}")


def _nmp_provider_to_ndd_provider(
    models: ModelsResource | AsyncModelsResource,
    nmp_provider: NMPModelProvider,
) -> dd.ModelProvider:
    return dd.ModelProvider(
        name=f"{nmp_provider.workspace}/{nmp_provider.name}",
        endpoint=models.get_provider_route_openai_url(nmp_provider),
    )


data_designer_sdk_resources = NemoPluginSDKResources(
    sync_resource=DataDesignerResource,
    async_resource=AsyncDataDesignerResource,
)
