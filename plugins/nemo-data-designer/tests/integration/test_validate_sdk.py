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
from nemo_data_designer_plugin.sdk.validation import ValidationReport, validate_config

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


async def test_validate_local_only_succeeds_with_igw_provider() -> None:
    """The regression we are explicitly fixing: an IGW-only provider reference
    must validate cleanly under the local execution context.
    """
    builder = _llm_builder(u.make_model_config(provider=u.OPEN_PROVIDER_NAME))

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder, execution_context="local")

    assert isinstance(report, ValidationReport)
    assert report.ok
    assert len(report.results) == 1
    assert report.results[0].context == "local"
    assert report.results[0].errors == []


async def test_validate_local_only_rejects_unrecognized_alias() -> None:
    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config(provider=u.OPEN_PROVIDER_NAME)])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="topic",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )
    builder.add_column(
        column_config=dd.LLMTextColumnConfig(
            name="description",
            model_alias="unknown-alias",
            prompt="Describe {{ topic }}",
        )
    )

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder, execution_context="local")

    assert not report.ok
    [result] = report.results
    assert result.context == "local"
    assert any("unknown-alias" in err.message for err in result.errors)


async def test_validate_remote_only_aggregates_seed_and_tool_errors() -> None:
    """Remote-only validation surfaces unsupported seed type *and* tool configs
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
        # by ``test_sdk_validate_method_aggregates_df_seed_with_other_remote_errors``.
        report = await validate_config(
            builder,
            async_sdk=client_context.async_sdk,
            workspace=u.WORKSPACE_NAME,
            execution_context="remote",
        )

    assert not report.ok
    [result] = report.results
    assert result.context == "remote"
    messages = [err.message for err in result.errors]
    assert any("Tool configs" in m for m in messages)
    assert any(("seed" in m.lower()) or ("df" in m) for m in messages)


async def test_sdk_validate_method_aggregates_df_seed_with_other_remote_errors() -> None:
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
        report = await dd_client.validate(builder, execution_context="remote")

    assert not report.ok
    [result] = report.results
    assert result.context == "remote"
    messages = [err.message for err in result.errors]
    # Both messages must surface in a single pass.
    assert any("Tool configs" in m for m in messages)
    # Remote rejects everything outside the {hf, nmp} whitelist; the message
    # mentions both supported types rather than calling out "df" specifically.
    assert any("seed_type=hf" in m and "seed_type=nmp" in m for m in messages)


async def test_sdk_validate_method_rejects_df_seed_for_local() -> None:
    """A ``df``-seed config is invalid for local execution too — preview
    serializes the config across the worker-thread boundary, which a
    pandas DataFrame can't survive — but the diagnostic must come from
    the validate pass (with a helpful message), not from an eager
    pre-flight rejection.
    """
    builder = dd.DataDesignerConfigBuilder(
        model_configs=[u.make_model_config(provider=u.OPEN_PROVIDER_NAME)],
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
        report = await dd_client.validate(builder, execution_context="local")

    assert not report.ok
    [result] = report.results
    assert result.context == "local"
    assert any("Dataframe seed sources" in err.message for err in result.errors)


async def test_validate_remote_only_rejects_unknown_provider() -> None:
    builder = _llm_builder(u.make_model_config(provider="some-unknown-provider"))

    with u.make_mock_client_context() as client_context:
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder, execution_context="remote")

    assert not report.ok
    [result] = report.results
    assert any("Cannot access provider" in err.message for err in result.errors)


async def test_validate_default_runs_every_context() -> None:
    """Omitting ``execution_context`` runs both local and remote, reports each independently."""
    builder = _llm_builder(u.make_model_config(provider=u.OPEN_PROVIDER_NAME))

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder)

    assert report.ok
    contexts = [r.context for r in report.results]
    assert contexts == ["local", "remote"]


async def test_validate_report_round_trips_through_pydantic() -> None:
    builder = _llm_builder(u.make_model_config(provider=u.OPEN_PROVIDER_NAME))

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = AsyncDataDesignerResource(client_context.async_sdk)
        report = await dd_client.validate(builder, execution_context="local")

    payload = report.model_dump_json()
    rehydrated = ValidationReport.model_validate_json(payload)
    assert rehydrated.results[0].context == "local"
    # Successful pass has no errors; the model itself is round-trippable either way.
    assert rehydrated.results[0].errors == []
