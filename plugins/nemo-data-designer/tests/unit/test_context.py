# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


from contextlib import contextmanager
from unittest.mock import AsyncMock, Mock, patch

import data_designer.config as dd
import nemo_data_designer_plugin.testing.utils as u
import pandas as pd
import pytest
from data_designer_nemo.context import LocalDataDesignerContext, RemoteDataDesignerContext
from data_designer_nemo.errors import NDDInvalidConfigError
from data_designer_nemo.model_provider import make_noop_provider
from nemo_platform import AsyncNeMoPlatform

LOCAL_PROVIDER_A = "local-provider-a"
LOCAL_PROVIDER_B = "local-provider-b"


@pytest.fixture
def local_providers() -> dict[str, dd.ModelProvider]:
    return {
        LOCAL_PROVIDER_A: dd.ModelProvider(
            name=LOCAL_PROVIDER_A,
            endpoint="http://example.com",
        ),
        LOCAL_PROVIDER_B: dd.ModelProvider(
            name=LOCAL_PROVIDER_B,
            endpoint="http://example.com",
        ),
    }


@contextmanager
def patch_local_lookup(providers: dict[str, dd.ModelProvider] | None = None):
    with patch("data_designer_nemo.model_provider.get_default_providers") as default_lookup:
        if providers:
            default_lookup.return_value = list(providers.values())
        yield default_lookup


def _simple_config(
    *,
    tool_configs: list[dd.ToolConfig] | None = None,
    seed_source: dd.DataFrameSeedSource | None = None,
) -> dd.DataDesignerConfig:
    return dd.DataDesignerConfig(
        columns=[dd.ExpressionColumnConfig(name="value", expr="'ok'")],
        model_configs=[],
        tool_configs=tool_configs or [],
        seed_config=dd.SeedConfig(source=seed_source) if seed_source is not None else None,
    )


async def test_local_validate_does_not_apply_remote_only_tool_validation() -> None:
    tool_config = dd.ToolConfig(tool_alias="hello", providers=["provider"])
    config = _simple_config(tool_configs=[tool_config])
    dd_ctx = LocalDataDesignerContext(Mock(), u.WORKSPACE_NAME)

    errors = await dd_ctx.validate(config)
    assert errors == []


async def test_local_validate_rejects_dataframe_seed_config() -> None:
    config = _simple_config(seed_source=dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})))
    dd_ctx = LocalDataDesignerContext(Mock(), u.WORKSPACE_NAME)

    errors = await dd_ctx.validate(config)

    assert len(errors) == 1
    assert isinstance(errors[0], NDDInvalidConfigError)
    assert "Dataframe seed sources" in str(errors[0])


async def test_remote_validate_runs_remote_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    config = _simple_config()
    sdk = AsyncMock(spec=AsyncNeMoPlatform)

    def validate_tools(validated_config: dd.DataDesignerConfig) -> None:
        assert validated_config is config
        calls.append("tools")

    def validate_seed_type(validated_config: dd.DataDesignerConfig, *, is_local: bool) -> None:
        assert validated_config is config
        assert is_local is False
        calls.append("seed-type")

    async def validate_seed(
        validated_config: dd.DataDesignerConfig, workspace: str, async_sdk: AsyncNeMoPlatform
    ) -> None:
        assert validated_config is config
        assert workspace == u.WORKSPACE_NAME
        assert async_sdk is sdk
        calls.append("seed")

    async def validate_personas(validated_config: dd.DataDesignerConfig, async_sdk: AsyncNeMoPlatform) -> None:
        assert validated_config is config
        assert async_sdk is sdk
        calls.append("personas")

    monkeypatch.setattr("data_designer_nemo.context.validate_no_tool_configs", validate_tools)
    monkeypatch.setattr("data_designer_nemo.context.validate_seed_config_for_execution_context", validate_seed_type)
    monkeypatch.setattr("data_designer_nemo.context.validate_seed", validate_seed)
    monkeypatch.setattr("data_designer_nemo.context.ensure_nemotron_personas_filesets", validate_personas)

    errors = await RemoteDataDesignerContext(sdk, u.WORKSPACE_NAME).validate(config)

    assert errors == []
    assert calls == ["tools", "seed-type", "seed", "personas"]


async def test_remote_validate_rejects_unsupported_seed_config() -> None:
    config = _simple_config(seed_source=dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})))
    dd_ctx = RemoteDataDesignerContext(AsyncMock(spec=AsyncNeMoPlatform), u.WORKSPACE_NAME)

    errors = await dd_ctx.validate(config)

    assert len(errors) == 1
    assert isinstance(errors[0], NDDInvalidConfigError)
    assert "seed data" in str(errors[0])


async def test_remote_validate_aggregates_multiple_failures() -> None:
    """Tool configs *and* an unsupported seed type both surface from a single pass."""
    config = _simple_config(
        tool_configs=[dd.ToolConfig(tool_alias="hello", providers=["provider"])],
        seed_source=dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})),
    )
    sdk = AsyncMock(spec=AsyncNeMoPlatform)
    dd_ctx = RemoteDataDesignerContext(sdk, u.WORKSPACE_NAME)

    errors = await dd_ctx.validate(config)

    messages = [str(e) for e in errors]
    assert all(isinstance(e, NDDInvalidConfigError) for e in errors)
    # We expect at least the tool-config and seed-type messages; both must surface
    # in a single pass (no short-circuiting on the first failure).
    assert any("Tool configs" in m for m in messages)
    assert any("seed data" in m or "df" in m for m in messages)
    assert len(errors) >= 2


async def test_local_model_providers_all_local(local_providers: dict[str, dd.ModelProvider]):
    sdk = Mock()
    dd_ctx = LocalDataDesignerContext(sdk, u.WORKSPACE_NAME)

    model_configs = [
        dd.ModelConfig(provider=LOCAL_PROVIDER_A, alias="a", model="model"),
        dd.ModelConfig(provider=LOCAL_PROVIDER_B, alias="b", model="model"),
    ]

    with patch_local_lookup(local_providers):
        providers = await dd_ctx.get_model_providers(model_configs)

    assert len(providers) == len(local_providers)
    sdk.assert_not_called()


async def test_local_model_providers_all_igw(local_providers: dict[str, dd.ModelProvider]):
    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
        patch_local_lookup(),
    ):
        sdk = client_context.async_sdk
        dd_ctx = LocalDataDesignerContext(sdk, u.WORKSPACE_NAME)

        model_configs = [
            dd.ModelConfig(provider=u.OPEN_PROVIDER_NAME, alias="a", model="model"),
        ]

        providers = await dd_ctx.get_model_providers(model_configs)

    assert len(providers) == 1


async def test_local_model_providers_no_models():
    sdk = Mock()
    dd_ctx = LocalDataDesignerContext(sdk, u.WORKSPACE_NAME)

    with patch_local_lookup() as local_lookup:
        providers = await dd_ctx.get_model_providers([])

    assert len(providers) == 1
    assert providers[0] == make_noop_provider()
    local_lookup.assert_not_called()
    sdk.assert_not_called()


async def test_local_model_providers_mixed_local_and_igw(local_providers: dict[str, dd.ModelProvider]):
    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
        patch_local_lookup(local_providers),
    ):
        sdk = client_context.async_sdk
        dd_ctx = LocalDataDesignerContext(sdk, u.WORKSPACE_NAME)

        model_configs = [
            dd.ModelConfig(provider=LOCAL_PROVIDER_A, alias="a", model="model"),
            dd.ModelConfig(provider=LOCAL_PROVIDER_B, alias="b", model="model"),
            dd.ModelConfig(provider=u.OPEN_PROVIDER_NAME, alias="a", model="model"),
        ]

        providers = await dd_ctx.get_model_providers(model_configs)

    assert len(providers) == 3


async def test_local_model_providers_igw_error():
    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
        patch_local_lookup(),
        pytest.raises(NDDInvalidConfigError) as exc_info,
    ):
        sdk = client_context.async_sdk
        dd_ctx = LocalDataDesignerContext(sdk, u.WORKSPACE_NAME)

        inaccessible_provider_name = "inaccessible/provider"

        model_configs = [
            dd.ModelConfig(provider=inaccessible_provider_name, alias="a", model="model"),
        ]

        await dd_ctx.get_model_providers(model_configs)

    assert "Cannot access provider" in str(exc_info.value)
    assert inaccessible_provider_name in str(exc_info.value)
    assert "Ensure all referenced providers are either" in str(exc_info.value)
