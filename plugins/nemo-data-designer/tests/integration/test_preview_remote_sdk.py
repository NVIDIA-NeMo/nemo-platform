# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import data_designer.config as dd
import nemo_data_designer_plugin.testing.utils as u
import pandas as pd
import pytest
from data_designer_nemo.fileset_file_seed_source import FilesetFileSeedSource
from nemo_data_designer_plugin.config import get_config
from nemo_data_designer_plugin.sdk.errors import DataDesignerConfigValidationError, DataDesignerPreviewError

pytestmark = pytest.mark.integration


def test_request_too_many_records() -> None:
    too_many_records = get_config().preview_num_records.max + 1

    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )

    with (
        u.make_mock_client_context() as client_context,
        pytest.raises(DataDesignerConfigValidationError) as exc_info,
    ):
        dd_client = u.make_dd_client(client_context)
        dd_client.preview(builder, num_records=too_many_records)
    assert "Max num records" in str(exc_info.value)


def test_happy_path_preview() -> None:
    column_name = "column-name"
    value = "a"

    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name=column_name,
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=[value]),
        )
    )

    with (
        u.make_mock_client_context() as client_context,
        capture_sdk_preview_log_messages() as log_messages,
    ):
        dd_client = u.make_dd_client(client_context)
        preview_results = dd_client.preview(builder, num_records=3)

    expected_dataset = pd.DataFrame(data={column_name: [value, value, value]}).convert_dtypes(dtype_backend="pyarrow")
    assert preview_results.dataset is not None
    pd.testing.assert_frame_equal(preview_results.dataset, expected_dataset)
    assert preview_results.dataset_metadata is not None
    assert preview_results.analysis is not None

    assert_message_with(log_messages, fuzzy=column_name)
    assert_message_with(log_messages, fuzzy="Preview generation in progress")


def test_hf_seed_dataset() -> None:
    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.with_seed_dataset(
        dd.HuggingFaceSeedSource(path="my-ws/my-fileset#path/to/data.parquet", token=u.SECRET_NAME)
    )
    builder.add_column(column_config=dd.ExpressionColumnConfig(name="full_name", expr=u.FULL_NAME_EXPR))

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_secret(client_context),
        u.mock_hf_seed_reader(),
    ):
        dd_client = u.make_dd_client(client_context)
        preview_results = dd_client.preview(builder, num_records=3)

    assert preview_results.dataset is not None
    assert set(preview_results.dataset["full_name"].values) == u.FULL_NAMES


def test_fileset_file_seed_dataset_plugin() -> None:
    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.with_seed_dataset(FilesetFileSeedSource(path=u.FILESET_FILE_SEED_SOURCE_PATH))  # ty: ignore[invalid-argument-type]
    builder.add_column(column_config=dd.ExpressionColumnConfig(name="full_name", expr=u.FULL_NAME_EXPR))

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_file(client_context),
    ):
        dd_client = u.make_dd_client(client_context)
        preview_results = dd_client.preview(builder, num_records=3)

    assert preview_results.dataset is not None
    assert set(preview_results.dataset["full_name"].values) == u.FULL_NAMES


def test_nemotron_personas_dataset() -> None:
    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="customer",
            sampler_type=dd.SamplerType.PERSON,
            params=dd.PersonSamplerParams(locale="en_US", age_range=[25, 45]),
        )
    )
    builder.add_column(column_config=dd.ExpressionColumnConfig(name="demo", expr="Customer is {{ customer.age }}"))

    sample_persona_data = pd.DataFrame(
        data={"first_name": ["Charlie"] * 100, "last_name": ["Parker"] * 100, "age": list(range(100))}
    )

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_nemotron_personas_data(client_context, sample_persona_data),
    ):
        dd_client = u.make_dd_client(client_context)
        preview_results = dd_client.preview(builder, num_records=3)

    assert preview_results.dataset is not None

    def _parse_age(v: str) -> int:
        return int(v.removeprefix("Customer is "))

    demo_values = preview_results.dataset["demo"].values
    demo_ages = [_parse_age(value) for value in demo_values]
    assert all(25 <= age <= 45 for age in demo_ages)


def test_preview_with_schema_transform_processor() -> None:
    column_name = "school_subject"
    processor_name = "chat_format"

    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name=column_name,
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["math", "science", "history"]),
        )
    )
    builder.add_processor(
        dd.SchemaTransformProcessorConfig(
            name=processor_name,
            template={
                "messages": [
                    {"role": "user", "content": "{{school_subject}}"},
                    {"role": "assistant", "content": "{{school_subject}}"},
                ],
            },
        )
    )

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        preview_results = dd_client.preview(builder, num_records=3)

    assert preview_results.dataset is not None
    assert preview_results.processor_artifacts is not None
    assert processor_name in preview_results.processor_artifacts
    processor_records = preview_results.processor_artifacts[processor_name]
    assert isinstance(processor_records, list)
    assert len(processor_records) == 3
    assert "messages" in processor_records[0]


def test_preview_surfaces_worker_error_through_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the preview worker thread raises, the function emits a ``LogFrame`` and an
    ``Error`` frame instead of ``Done``; the SDK's ``_PreviewFrameCollector`` translates
    that ``Error`` into a typed ``DataDesignerPreviewError`` with the original message.
    """
    from nemo_data_designer_plugin.functions import preview as preview_module

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("forced worker failure")

    monkeypatch.setattr(preview_module, "make_preview_dataset", boom)

    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a"]),
        )
    )

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        with pytest.raises(DataDesignerPreviewError, match="forced worker failure"):
            dd_client.preview(builder, num_records=3)


def assert_message_with(messages: list[str], exact: str | None = None, fuzzy: str | None = None) -> None:
    match (exact, fuzzy):
        case (None, None):
            raise ValueError("Must set 'exact' OR 'fuzzy', not both")
        case (some_exact, None):
            assert some_exact in messages
        case (None, some_fuzzy):
            assert any(some_fuzzy in message for message in messages), (
                f"Did not find a message with expected content: {some_fuzzy}"
            )
        case (_, _):
            raise ValueError("Must set 'exact' OR 'fuzzy', not both")


class _MessageCaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextmanager
def capture_sdk_preview_log_messages() -> Iterator[list[str]]:
    preview_logger = logging.getLogger("nemo_data_designer_plugin.sdk.resources")
    previous_level = preview_logger.level
    handler = _MessageCaptureHandler()

    preview_logger.addHandler(handler)
    preview_logger.setLevel(logging.INFO)
    try:
        yield handler.messages
    finally:
        preview_logger.removeHandler(handler)
        preview_logger.setLevel(previous_level)
