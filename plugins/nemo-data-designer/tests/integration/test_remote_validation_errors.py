# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import data_designer.config as dd
import nemo_data_designer_plugin.testing.utils as u
import pandas as pd
import pytest
from nemo_data_designer_plugin.sdk.errors import DataDesignerClientError, DataDesignerConfigValidationError

pytestmark = pytest.mark.integration


def _assert_error(
    dd_client,
    builder: dd.DataDesignerConfigBuilder,
    expected_error_message_fragments: list[str],
    expected_error_type: type[BaseException] = DataDesignerConfigValidationError,
) -> None:
    with pytest.raises(expected_error_type) as exc_info:
        dd_client.preview(builder)
    for fragment in expected_error_message_fragments:
        assert fragment in str(exc_info.value)

    with pytest.raises(expected_error_type) as exc_info:
        dd_client.create(builder)
    for fragment in expected_error_message_fragments:
        assert fragment in str(exc_info.value)


def _builder_with_llm_column(model_config: dd.ModelConfig) -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder(model_configs=[model_config])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo", sampler_type=dd.SamplerType.CATEGORY, params=dd.CategorySamplerParams(values=["a", "b"])
        )
    )
    builder.add_column(
        column_config=dd.LLMTextColumnConfig(
            name="story", prompt="Write a story about {{ foo }}", model_alias=model_config.alias
        )
    )
    return builder


def test_unknown_provider_in_request() -> None:
    unknown_provider = "some-unknown-provider"
    bad_model_config = u.make_model_config(provider=unknown_provider)
    builder = _builder_with_llm_column(bad_model_config)

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        _assert_error(dd_client, builder, ["Cannot access provider", unknown_provider])


def test_malformed_provider_reference_is_rejected() -> None:
    alias = "too-many-slashes"
    malformed_provider_name = "foo/bar/baz"
    bad_model_config = dd.ModelConfig(alias=alias, model="some-model", provider=malformed_provider_name)
    builder = _builder_with_llm_column(bad_model_config)

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        _assert_error(dd_client, builder, ["Malformed model provider", alias, malformed_provider_name])


def test_invalid_models_provided() -> None:
    disallowed_model = "this-model-is-not-allowed"
    bad_model_config = u.make_model_config(provider=u.RESTRICTED_PROVIDER_NAME, model=disallowed_model)
    builder = _builder_with_llm_column(bad_model_config)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        dd_client = u.make_dd_client(client_context)
        _assert_error(dd_client, builder, [disallowed_model, "not enabled for provider", u.RESTRICTED_PROVIDER_NAME])


def test_unrecognized_model_alias() -> None:
    model_alias = "unknown-model-alias"

    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="school_subject",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["math", "science", "history"]),
        )
    )
    builder.add_column(
        column_config=dd.LLMTextColumnConfig(
            name="school_subject_description",
            model_alias=model_alias,
            prompt="Describe the school subject {{ school_subject }}.",
        )
    )

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        _assert_error(dd_client, builder, ["Unrecognized", model_alias])


def test_mcp_tools_not_allowed() -> None:
    provider = u.OPEN_PROVIDER_NAME
    model_config = u.make_model_config(provider=provider)
    tool_config = dd.ToolConfig(tool_alias="hello", providers=[provider])
    builder = dd.DataDesignerConfigBuilder(model_configs=[model_config], tool_configs=[tool_config])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="school_subject",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["math", "science", "history"]),
        )
    )

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        _assert_error(dd_client, builder, ["Tool configs are not supported"])


def test_seed_dataset_bad_token() -> None:
    bad_token_secret = "unrecognized-secret-ref"
    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.with_seed_dataset(
        dd.HuggingFaceSeedSource(path="my-ws/my-fileset#path/to/data.parquet", token=bad_token_secret)
    )
    builder.add_column(column_config=dd.ExpressionColumnConfig(name="full_name", expr=u.FULL_NAME_EXPR))

    with (
        u.make_mock_client_context() as client_context,
        u.mock_hf_seed_reader(),
    ):
        dd_client = u.make_dd_client(client_context)
        _assert_error(dd_client, builder, [bad_token_secret])


def test_nemotron_personas_dataset_failure() -> None:
    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="customer",
            sampler_type=dd.SamplerType.PERSON,
            params=dd.PersonSamplerParams(locale="en_US", age_range=[25, 45]),
        )
    )
    builder.add_column(column_config=dd.ExpressionColumnConfig(name="demo", expr="Customer is {{ customer.age }}"))

    with u.make_mock_client_context() as client_context:
        dd_client = u.make_dd_client(client_context)
        _assert_error(dd_client, builder, ["Nemotron personas filesets"], DataDesignerClientError)


def test_server_side_unsupported_seed_type_validation() -> None:
    builder = dd.DataDesignerConfigBuilder(model_configs=[u.make_model_config()])
    builder.with_seed_dataset(dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})))
    builder.add_column(column_config=dd.ExpressionColumnConfig(name="full_name", expr=u.FULL_NAME_EXPR))
    config = builder.build().model_dump(exclude_unset=False)

    with (
        u.make_mock_client_context() as client_context,
        u.mock_hf_seed_reader(),
    ):
        preview_resp = client_context.test_client.post(
            f"/apis/data-designer/v2/workspaces/{u.WORKSPACE_NAME}/preview",
            json={"config": config},
        )
        assert preview_resp.status_code == 422
        assert "seed data" in preview_resp.text

        jobs_resp = client_context.test_client.post(
            f"/apis/data-designer/v2/workspaces/{u.WORKSPACE_NAME}/jobs/create",
            json={"spec": {"config": config, "num_records": 100}},
        )
        assert jobs_resp.status_code == 422
        assert "seed data" in jobs_resp.text
