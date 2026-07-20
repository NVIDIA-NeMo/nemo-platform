# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nemo_platform_plugin.client.errors import NemoTransportError
from nemo_platform_plugin.models.client import AsyncModelsClient, ModelsClient
from nmp.customization_common.service.platform_client import fetch_model_entity
from nmp.customization_common.tasks.model_entity.run import (
    TRANSIENT_RETRYABLE_EXCEPTIONS,
    ModelEntityRunner,
)


@pytest.mark.asyncio
async def test_fetch_model_entity_uses_async_models_client() -> None:
    sdk = MagicMock()
    entity = MagicMock()
    response = MagicMock()
    response.data.return_value = entity
    models = MagicMock()
    models.get_model = AsyncMock(return_value=response)

    with patch(
        "nmp.customization_common.service.platform_client.client_from_platform",
        return_value=models,
    ) as make_client:
        result = await fetch_model_entity("other/model", "default", sdk)

    make_client.assert_called_once_with(sdk, AsyncModelsClient)
    models.get_model.assert_awaited_once_with(
        name="model",
        workspace="other",
        query_params={"verbose": True},
    )
    assert result is entity


def test_model_entity_runner_uses_models_client() -> None:
    sdk = MagicMock()
    entity = MagicMock()
    response = MagicMock()
    response.data.return_value = entity
    models = MagicMock()
    models.get_model.return_value = response

    with patch(
        "nmp.customization_common.tasks.model_entity.run.client_from_platform",
        return_value=models,
    ) as make_client:
        runner = ModelEntityRunner(sdk, MagicMock())
        result = runner.get_model_entity("other/model", "default")

    make_client.assert_called_once_with(sdk, ModelsClient)
    models.get_model.assert_called_once_with(name="model", workspace="other")
    assert result is entity


def test_models_transport_errors_remain_retryable() -> None:
    assert NemoTransportError in TRANSIENT_RETRYABLE_EXCEPTIONS
