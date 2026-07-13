# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pure-logic unit tests for ``DataDesignerResource``.

These tests cover the SDK seams that don't need a server:
- URL construction (``sdk_http.url``)
- The streaming-preview state machine (``_PreviewFrameCollector``) and its
  decode helpers (``_decode_preview_frame`` / ``_parse_preview_payload``)
- The client-side seed-source validation gate (``_get_config_for_api_call``)
- The HTTP-error to typed-exception translator (``_get_error``)

Round-trip tests against the real preview/jobs endpoints live in
``tests/integration/`` (``test_preview.py``, ``test_jobs.py``,
``test_validation.py``, ``test_model_providers.py``).
"""

from collections.abc import AsyncIterator
from typing import Any, cast
from unittest.mock import patch

import data_designer.config as dd
import httpx
import pandas as pd
import pytest
from data_designer.config.analysis.column_statistics import GeneralColumnStatistics
from data_designer.config.analysis.dataset_profiler import DatasetProfilerResults
from data_designer.config.dataset_metadata import DatasetMetadata
from nemo_data_designer_plugin.functions._types import (
    AnalysisFrame,
    DatasetFrame,
    DatasetMetadataFrame,
    LogFrame,
    ProcessorOutputFrame,
)
from nemo_data_designer_plugin.sdk import http as sdk_http
from nemo_data_designer_plugin.sdk.errors import (
    DataDesignerClientError,
    DataDesignerConfigValidationError,
    DataDesignerPreviewError,
)
from nemo_data_designer_plugin.sdk.resources import (
    AsyncDataDesignerResource,
    DataDesignerResource,
    _decode_preview_frame,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.functions.frames import Done, Error, Heartbeat
from pydantic import BaseModel


@pytest.fixture
def platform() -> NeMoPlatform:
    return NeMoPlatform(base_url="http://testserver", workspace="default", access_token="token")


@pytest.fixture
def async_platform() -> AsyncNeMoPlatform:
    return AsyncNeMoPlatform(base_url="http://testserver", workspace="default", access_token="token")


@pytest.fixture
def resource(platform: NeMoPlatform) -> DataDesignerResource:
    return DataDesignerResource(platform)


@pytest.fixture
def async_resource(async_platform: AsyncNeMoPlatform) -> AsyncDataDesignerResource:
    return AsyncDataDesignerResource(async_platform)


@pytest.fixture
def config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder(
        model_configs=[dd.ModelConfig(alias="text", model="model", provider="default/nvidia")]
    )
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )
    return builder


def _make_basic_dataset() -> pd.DataFrame:
    return pd.DataFrame(data={"foo": [1, 2, 3]}).convert_dtypes(dtype_backend="pyarrow")


async def _async_iter(frames: list[BaseModel]) -> AsyncIterator[BaseModel]:
    for frame in frames:
        yield frame


def _make_successful_preview_frames() -> list[BaseModel]:
    dataset = _make_basic_dataset()
    dataset_dict = cast(list[dict[str, Any]], dataset.to_dict(orient="records"))
    dataset_metadata = DatasetMetadata()
    analysis = DatasetProfilerResults(
        num_records=3,
        target_num_records=3,
        column_statistics=[
            GeneralColumnStatistics(
                column_name="foo",
                num_records=3,
                num_null=0,
                num_unique=3,
                pyarrow_dtype="int",
                simple_dtype="int",
                column_type="general",
            )
        ],
    )
    return [
        LogFrame(level="info", message="Some message"),
        Heartbeat(),
        DatasetMetadataFrame(metadata=dataset_metadata),
        DatasetFrame(records=dataset_dict),
        ProcessorOutputFrame(processor_name="processor", records=[{"foo": "bar"}]),
        AnalysisFrame(analysis=analysis),
        Done(),
    ]


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["preview", "/preview", "///preview"])
def test_http_url_normalizes_leading_slashes(platform: NeMoPlatform, path: str) -> None:
    assert sdk_http.url(platform, None, path) == "http://testserver/apis/data-designer/v2/workspaces/default/preview"


def test_http_url_normalizes_empty_path(platform: NeMoPlatform) -> None:
    assert sdk_http.url(platform, None, "") == "http://testserver/apis/data-designer/v2/workspaces/default/"


# ---------------------------------------------------------------------------
# Preview frame decoding
# ---------------------------------------------------------------------------


def test_decode_preview_frame_returns_typed_frame_for_known_kind() -> None:
    frame = _decode_preview_frame('{"kind":"log","level":"info","message":"hello"}')
    assert isinstance(frame, LogFrame)
    assert frame.message == "hello"


def test_decode_preview_frame_returns_none_for_unknown_kind() -> None:
    """Unknown frame kinds are forward-compat: dropped silently so older clients can talk to
    newer servers without crashing."""
    assert _decode_preview_frame('{"kind":"future","payload":1}') is None


def test_decode_preview_frame_returns_none_for_non_object_payload() -> None:
    """Defensive: a JSON scalar / list isn't a frame and shouldn't crash the parser."""
    assert _decode_preview_frame("[]") is None
    assert _decode_preview_frame('"oops"') is None


# ---------------------------------------------------------------------------
# _PreviewFrameCollector behavior (driven via patched _preview)
# ---------------------------------------------------------------------------


def test_preview_collector_assembles_dataset_metadata_and_processor_artifacts(
    resource: DataDesignerResource, config_builder: dd.DataDesignerConfigBuilder
) -> None:
    with patch.object(resource, "_preview", return_value=_make_successful_preview_frames()):
        preview_results = resource.preview(config_builder)

    assert isinstance(preview_results.dataset, pd.DataFrame)
    pd.testing.assert_frame_equal(preview_results.dataset, _make_basic_dataset())
    assert preview_results.processor_artifacts == {"processor": [{"foo": "bar"}]}


@pytest.mark.asyncio
async def test_preview_collector_assembles_dataset_async(
    async_resource: AsyncDataDesignerResource, config_builder: dd.DataDesignerConfigBuilder
) -> None:
    with patch.object(async_resource, "_preview", return_value=_async_iter(_make_successful_preview_frames())):
        preview_results = await async_resource.preview(config_builder)

    assert isinstance(preview_results.dataset, pd.DataFrame)
    pd.testing.assert_frame_equal(preview_results.dataset, _make_basic_dataset())


def test_preview_collector_raises_when_dataset_frame_is_empty(
    resource: DataDesignerResource, config_builder: dd.DataDesignerConfigBuilder
) -> None:
    """``_PreviewFrameCollector._accept_dataset`` rejects empty record batches because the
    real failure mode is silent column-generation failures, not legitimate empty datasets.
    """
    with patch.object(resource, "_preview", return_value=[DatasetFrame(records=[])]):
        with pytest.raises(DataDesignerPreviewError):
            resource.preview(config_builder)


def test_preview_collector_propagates_error_frame_message(
    resource: DataDesignerResource, config_builder: dd.DataDesignerConfigBuilder
) -> None:
    with patch.object(resource, "_preview", return_value=[Error(message="boom")]):
        with pytest.raises(DataDesignerPreviewError, match="boom"):
            resource.preview(config_builder)


# ---------------------------------------------------------------------------
# Client-side seed-source validation gate (_get_config_for_api_call)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed_kind", ["df", "local", "directory", "file_contents"])
def test_preview_rejects_local_only_seed_sources_before_sending_request(
    resource: DataDesignerResource,
    config_builder: dd.DataDesignerConfigBuilder,
    seed_kind: str,
    tmp_path,
) -> None:
    """The validation gate inside ``_get_config_for_api_call`` rejects seed sources that
    only make sense locally (DataFrame, LocalFile, Directory, FileContents), so the SDK
    fails fast with a typed error instead of letting the server emit a 422 round-trip
    later. Patching ``_preview`` to raise an AssertionError catches any regression where
    the request is sent anyway.
    """
    if seed_kind == "df":
        seed_source = dd.DataFrameSeedSource(df=pd.DataFrame(data={"foo": [1, 2, 3]}))
    elif seed_kind == "local":
        seed_file = tmp_path / "seed.parquet"
        _make_basic_dataset().to_parquet(seed_file)
        seed_source = dd.LocalFileSeedSource(path=str(seed_file))
    elif seed_kind == "directory":
        seed_source = dd.DirectorySeedSource(path=str(tmp_path))
    else:
        seed_source = dd.FileContentsSeedSource(path=str(tmp_path))

    config_builder.with_seed_dataset(seed_source)

    with (
        patch.object(resource, "_preview", side_effect=AssertionError("preview request should not be sent")),
        pytest.raises(DataDesignerConfigValidationError) as exc_info,
    ):
        resource.preview(config_builder)

    assert "only supports seed data" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Default model surfaces
# ---------------------------------------------------------------------------


def test_get_default_model_configs_returns_empty_list(resource: DataDesignerResource) -> None:
    """Default model configs aren't supported on the NeMo Platform; the resource returns an
    empty list rather than raising, so callers can still build a config without LLMs."""
    assert resource.get_default_model_configs() == []


# ---------------------------------------------------------------------------
# HTTP-error translation (_get_error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_error_translates_422_to_config_validation_error(
    async_resource: AsyncDataDesignerResource, config_builder: dd.DataDesignerConfigBuilder
) -> None:
    request = httpx.Request("POST", "http://testserver")
    response = httpx.Response(422, request=request, json={"detail": "bad config"})

    with patch.object(
        async_resource, "_preview", side_effect=httpx.HTTPStatusError("bad", request=request, response=response)
    ):
        with pytest.raises(DataDesignerConfigValidationError) as exc_info:
            await async_resource.preview(config_builder)

    assert exc_info.value.status_code == 422
    assert "bad config" in str(exc_info.value)


@pytest.mark.asyncio
async def test_http_error_translates_5xx_to_generic_client_error(
    async_resource: AsyncDataDesignerResource, config_builder: dd.DataDesignerConfigBuilder
) -> None:
    request = httpx.Request("POST", "http://testserver")
    response = httpx.Response(500, request=request, text="boom")

    with patch.object(
        async_resource, "_preview", side_effect=httpx.HTTPStatusError("bad", request=request, response=response)
    ):
        with pytest.raises(DataDesignerClientError) as exc_info:
            await async_resource.preview(config_builder)

    assert exc_info.value.status_code == 500
    # 5xx is *not* a config validation error — make sure we didn't accidentally widen the 422 branch.
    assert not isinstance(exc_info.value, DataDesignerConfigValidationError)
