# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nemo_platform_plugin.models.client import AsyncModelsClient
from nmp.automodel.app.jobs.compiler import _resolve_deployment_config_ref


@pytest.mark.asyncio
async def test_resolve_deployment_config_uses_models_client() -> None:
    sdk = MagicMock()
    deployment_config = MagicMock()
    response = MagicMock()
    response.data.return_value = deployment_config
    models = MagicMock()
    models.get_deployment_config = AsyncMock(return_value=response)

    with patch("nmp.automodel.app.jobs.compiler.client_from_platform", return_value=models) as make_client:
        result = await _resolve_deployment_config_ref("other/config", "default", sdk)

    make_client.assert_called_once_with(sdk, AsyncModelsClient)
    models.get_deployment_config.assert_awaited_once_with(name="config", workspace="other")
    assert result is deployment_config
