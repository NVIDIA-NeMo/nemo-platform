# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

import data_designer.config as dd
import nemo_data_designer_plugin.testing.utils as u
import pytest
from data_designer_nemo.errors import NDDInvalidConfigError
from data_designer_nemo.model_provider import (
    make_local_first_model_provider_registry,
    make_model_provider_registry,
    make_null_registry,
)


@pytest.mark.asyncio
async def test_local_first_provider_cannot_be_none() -> None:
    """When a local-first registry build sees a missing provider, it must fail fast
    *before* hitting the local-provider lookup helper.
    """
    bad_model_configs = [dd.ModelConfig(alias="no-provider-specified", model="some-model")]

    with u.make_mock_client_context() as client_context:
        with (
            patch("data_designer_nemo.model_provider.get_default_providers") as default_lookup,
            pytest.raises(NDDInvalidConfigError) as exc_info,
        ):
            await make_local_first_model_provider_registry(
                bad_model_configs,
                sdk=client_context.async_sdk,
                default_workspace=u.WORKSPACE_NAME,
            )

    default_lookup.assert_not_called()
    assert "explicit provider defined" in str(exc_info.value)


@pytest.mark.asyncio
async def test_no_model_configs_returns_none() -> None:
    """``make_model_provider_registry`` returns None for an empty model-config list,
    which the engine treats as 'no LLMs in this config'.
    """
    with u.make_mock_client_context() as client_context:
        registry = await make_model_provider_registry(
            [], sdk=client_context.async_sdk, default_workspace=u.WORKSPACE_NAME
        )
    assert registry is None


def test_null_registry() -> None:
    """Configs with no LLM columns get a one-provider 'no-op' registry so the
    Data Designer engine can run without rejecting an empty registry.
    """
    registry = make_null_registry()

    assert len(registry.providers) == 1
    assert registry.default == "no-op"
