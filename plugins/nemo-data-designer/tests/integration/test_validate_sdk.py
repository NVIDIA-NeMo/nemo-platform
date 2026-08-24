# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for ``DataDesignerResource.validate`` and its async sibling.

The validate SDK is a thin shell over
:func:`nemo_data_designer_plugin.sdk.validation.validate_config`; these tests
assert the public behavior of the SDK entry points against an in-process
mock platform.

We exercise the **async** SDK (``AsyncDataDesignerResource``) because the
in-process test transport lives on ``client_context.async_sdk``. The sync
SDK's ``validate`` method rebuilds an async sibling via ``sync_to_async_sdk``,
which (correctly, in production) makes real HTTP calls — but those don't
reach the in-process services in tests.
"""

from __future__ import annotations

import data_designer.config as dd
import nemo_data_designer_plugin.testing.utils as u
import pandas as pd
import pytest
from nemo_data_designer_plugin.sdk.resources import AsyncDataDesignerResource
from nemo_data_designer_plugin.sdk.validation import validate_config

pytestmark = pytest.mark.integration


def _llm_builder(model_config: dd.ModelConfig) -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder(model_configs=[model_config])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )
    builder.add_column(
        column_config=dd.LLMTextColumnConfig(
            name="story", prompt="Write a story about {{ foo }}", model_alias=model_config.alias
        )
    )
    return builder


async def test_validate_aggregates_seed_and_tool_errors() -> None:
    """Validation surfaces unsupported seed type *and* tool configs
    in a single pass — exercising the §5.0 aggregation end-to-end.
    """
    builder = dd.DataDesignerConfigBuilder(
        model_configs=[u.make_model_config(provider=u.OPEN_PROVIDER_NAME)],
        tool_configs=[dd.ToolConfig(tool_alias="hello", providers=[u.OPEN_PROVIDER_NAME])],
    )
    builder.with_seed_dataset(dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})))
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        # Exercise the validation core directly so the contract is documented
        # without going through the SDK shell. The SDK-shell path is covered
        # by ``test_sdk_validate_method_aggregates_df_seed_with_other_errors``.
        report = await validate_config(
            builder,
            async_sdk=client_context.async_sdk,
            workspace=u.WORKSPACE_NAME,
        )

    assert not report.ok
    messages = [err.message for err in report.errors]
    assert any("Tool configs" in m for m in messages)
    assert any(("seed" in m.lower()) or ("df" in m) for m in messages)


async def test_validate_rejects_empty_fileset_root_seed() -> None:
    builder = dd.DataDesignerConfigBuilder()
    builder.with_seed_dataset(dd.DirectorySeedSource(path=f"{u.WORKSPACE_NAME}/{u.FILESET_NAME}"))
    builder.add_column(column_config=dd.ExpressionColumnConfig(name="full_name", expr=u.FULL_NAME_EXPR))

    with u.make_mock_client_context() as client_context:
        client_context.sdk.files.filesets.create(name=u.FILESET_NAME, workspace=u.WORKSPACE_NAME)
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder)

    assert not report.ok
    assert any("contains no files to use as seed data" in err.message for err in report.errors)


async def test_sdk_validate_method_aggregates_df_seed_with_other_errors() -> None:
    """Regression: ``DataDesignerResource.validate`` itself (not just the
    underlying ``validate_config`` core) must accept a ``df``-seed config and
    aggregate the unsupported-seed error with every other detected problem.

    Earlier versions of the SDK applied an eager
    ``_get_config_for_api_call`` rejection (the same one ``preview`` /
    ``create`` use) and short-circuited with a single error before the
    validate pass could run.
    """
    builder = dd.DataDesignerConfigBuilder(
        model_configs=[u.make_model_config(provider=u.OPEN_PROVIDER_NAME)],
        tool_configs=[dd.ToolConfig(tool_alias="hello", providers=[u.OPEN_PROVIDER_NAME])],
    )
    builder.with_seed_dataset(dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})))
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder)

    assert not report.ok
    messages = [err.message for err in report.errors]
    # Both messages must surface in a single pass.
    assert any("Tool configs" in m for m in messages)
    assert any("seed sources" in m and "Files service" in m for m in messages)


async def test_sdk_validate_method_rejects_custom_columns() -> None:
    @dd.custom_column_generator(required_columns=["foo"])
    def append_custom_value(row: dict) -> dict:
        row["custom_value"] = f"{row['foo']} custom"
        return row

    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config(provider=u.OPEN_PROVIDER_NAME)])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )
    builder.add_column(column_config=dd.CustomColumnConfig(name="custom_value", generator_function=append_custom_value))

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder)

    assert not report.ok
    messages = [err.message for err in report.errors]
    assert any("Custom columns are not supported" in m for m in messages)


async def test_validate_rejects_unknown_provider() -> None:
    builder = _llm_builder(u.make_model_config(provider="some-unknown-provider"))

    with u.make_mock_client_context() as client_context:
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder)

    assert not report.ok
    assert any("Cannot access provider" in err.message for err in report.errors)
