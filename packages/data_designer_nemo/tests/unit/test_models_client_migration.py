# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from data_designer_nemo.model_provider import get_nmp_provider, get_nmp_provider_async
from nemo_platform_plugin.models.client import AsyncModelsClient, ModelsClient


def test_get_nmp_provider_uses_models_client() -> None:
    sdk = MagicMock()
    provider = MagicMock()
    response = MagicMock()
    response.data.return_value = provider
    models = MagicMock()
    models.get_provider.return_value = response

    with patch("data_designer_nemo.model_provider.client_from_platform", return_value=models) as make_client:
        result = get_nmp_provider(sdk, "workspace", "provider")

    make_client.assert_called_once_with(sdk, ModelsClient)
    models.get_provider.assert_called_once_with(workspace="workspace", name="provider")
    assert result is provider


@pytest.mark.asyncio
async def test_get_nmp_provider_async_uses_models_client() -> None:
    sdk = MagicMock()
    provider = MagicMock()
    response = MagicMock()
    response.data.return_value = provider
    models = MagicMock()
    models.get_provider = AsyncMock(return_value=response)

    with patch("data_designer_nemo.model_provider.client_from_platform", return_value=models) as make_client:
        result = await get_nmp_provider_async(sdk, "workspace", "provider")

    make_client.assert_called_once_with(sdk, AsyncModelsClient)
    models.get_provider.assert_awaited_once_with(workspace="workspace", name="provider")
    assert result is provider
