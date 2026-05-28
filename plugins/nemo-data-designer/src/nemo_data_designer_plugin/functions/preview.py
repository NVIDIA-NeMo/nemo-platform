# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

import anyio
import anyio.from_thread
import anyio.to_thread
import data_designer.config as dd
from anyio.lowlevel import current_token
from data_designer.config.utils.constants import DEFAULT_NUM_RECORDS
from data_designer_nemo.context import DataDesignerContext, create_data_designer_context
from data_designer_nemo.errors import NDDError, NDDInternalError, NDDInvalidConfigError
from data_designer_nemo.fileset_file_seed_reader import workspace_cvar
from data_designer_nemo.model_configs import get_model_configs
from nemo_data_designer_plugin.config import get_config
from nemo_data_designer_plugin.functions._preview_worker import make_preview_dataset
from nemo_data_designer_plugin.functions._types import (
    LogFrame,
    PreviewSpec,
)
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.function_context import FunctionContext
from nemo_platform_plugin.functions.frames import Done, Error
from pydantic import BaseModel


class PreviewMessageDeliveryError(Exception): ...


class PreviewFunction(NemoFunction[PreviewSpec]):
    name: ClassVar[str] = "preview"
    description: ClassVar[str] = "Generate a small preview dataset by streaming NDJSON frames."
    spec_schema: ClassVar[type[PreviewSpec]] = PreviewSpec

    async def run(
        self,
        spec: PreviewSpec,
        *,
        ctx: FunctionContext,
        async_sdk: AsyncNeMoPlatform,
        is_local: bool = False,
    ) -> AsyncIterator[BaseModel]:
        dd_ctx = create_data_designer_context(is_local, async_sdk, ctx.workspace)

        # Extract/set all necessary values, validating along the way. Raise if any errors were collected.
        errors: list[NDDError] = []
        num_records = _validate_and_get_num_records(spec.num_records, is_local, errors)
        model_configs, model_providers = await _get_model_configs_and_providers(dd_ctx, spec.config, errors)
        errors.extend(await dd_ctx.validate(spec.config))
        _raise_if_errors(errors)

        workspace_cvar.set(ctx.workspace)

        send_stream, receive_stream = anyio.create_memory_object_stream[BaseModel]()
        token = current_token()

        def send_from_thread(frame: BaseModel) -> None:
            try:
                anyio.from_thread.run(send_stream.send, frame, token=token)
            except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                raise PreviewMessageDeliveryError(
                    "Caught an anyio resource error. Most likely the request was canceled."
                ) from None

        config_builder = dd.DataDesignerConfigBuilder.from_config(spec.config.to_dict())

        async def _worker() -> None:
            try:
                await anyio.to_thread.run_sync(
                    make_preview_dataset,
                    config_builder,
                    dd_ctx,
                    send_from_thread,
                    spec,
                    model_providers,
                    model_configs,
                    num_records,
                )
            except Exception as exc:
                try:
                    await send_stream.send(LogFrame(level="error", message=f"An error occurred: {exc}"))
                    await send_stream.send(Error(message=str(exc), details={"type": type(exc).__name__}))
                except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                    pass
            finally:
                await send_stream.aclose()

        completed_with_error = False
        async with anyio.create_task_group() as tg:
            tg.start_soon(_worker)
            async with receive_stream:
                async for frame in receive_stream:
                    if isinstance(frame, Error):
                        completed_with_error = True
                    yield frame
            if not completed_with_error:
                yield Done()


def _validate_and_get_num_records(
    requested_num_records: int | None,
    is_local: bool,
    errors: list[NDDError],
) -> int:
    """Resolve the effective ``num_records``, appending to ``errors`` on overflow."""
    if is_local:
        return requested_num_records or DEFAULT_NUM_RECORDS

    config = get_config()
    num_records = config.preview_num_records.default
    if requested_num_records:
        if requested_num_records > config.preview_num_records.max:
            errors.append(
                NDDInvalidConfigError(f"Max num records for preview requests is {config.preview_num_records.max}")
            )
        num_records = requested_num_records

    return num_records


async def _get_model_configs_and_providers(
    dd_ctx: DataDesignerContext,
    config: dd.DataDesignerConfig,
    errors: list[NDDError],
) -> tuple[list[dd.ModelConfig], list[dd.ModelProvider]]:
    """Resolve referenced model configs / providers, appending failures to ``errors``."""
    model_configs: list[dd.ModelConfig] = []
    model_providers: list[dd.ModelProvider] = []

    try:
        model_configs = get_model_configs(config)
    except NDDInvalidConfigError as e:
        errors.append(e)
    else:
        try:
            model_providers = await dd_ctx.get_model_providers(model_configs)
        except (NDDInvalidConfigError, NDDInternalError) as e:
            errors.append(e)

    return model_configs, model_providers


def _raise_if_errors(errors: list[NDDError]) -> None:
    """Raise an aggregated NDD error if ``errors`` is non-empty.

    Any config-level error wins (422 path); only when *every* error is internal
    do we raise ``NDDInternalError`` (500 path).
    """
    if not errors:
        return
    aggregated_message = "\n".join(str(e) for e in errors)
    if any(isinstance(e, NDDInvalidConfigError) for e in errors):
        raise NDDInvalidConfigError(aggregated_message)
    raise NDDInternalError(aggregated_message)
