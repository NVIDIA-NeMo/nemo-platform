# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nemo_platform_plugin.client.errors import NotFoundError
from nemo_platform_plugin.files.client import AsyncFilesClient
from nemo_platform_plugin.models.client import AsyncModelsClient
from nmp.customization_common.service.platform_client import fetch_model_entity


def _not_found() -> NotFoundError:
    return NotFoundError(httpx.Response(404, request=httpx.Request("GET", "http://platform/resource")))


def _clients(
    model: SimpleNamespace,
    *,
    fileset_error: Exception | None = None,
) -> tuple[MagicMock, MagicMock, Callable[[object, type], MagicMock]]:
    models = MagicMock()
    models.get_model = AsyncMock(return_value=SimpleNamespace(data=lambda: model))
    files = MagicMock()
    files.get_fileset = AsyncMock()
    if fileset_error is not None:
        files.get_fileset.side_effect = fileset_error

    def dispatch(_sdk: object, client_type: type):
        if client_type is AsyncModelsClient:
            return models
        if client_type is AsyncFilesClient:
            return files
        raise AssertionError(f"Unexpected client type: {client_type}")

    return models, files, dispatch


async def test_fetch_model_entity_verifies_weights_fileset() -> None:
    model = SimpleNamespace(name="base", workspace="default", fileset="weights/default-base")
    models, files, dispatch = _clients(model)

    with patch(
        "nmp.customization_common.service.platform_client.client_from_platform",
        side_effect=dispatch,
    ):
        result = await fetch_model_entity("default/base", "default", MagicMock())

    assert result is model
    models.get_model.assert_awaited_once_with(
        name="base",
        workspace="default",
        query_params={"verbose": True},
    )
    files.get_fileset.assert_awaited_once_with(workspace="weights", name="default-base")


async def test_fetch_model_entity_rejects_missing_weights_fileset() -> None:
    model = SimpleNamespace(name="base", workspace="default", fileset="default/missing")
    _, _, dispatch = _clients(model, fileset_error=_not_found())

    with (
        patch(
            "nmp.customization_common.service.platform_client.client_from_platform",
            side_effect=dispatch,
        ),
        pytest.raises(ValueError, match="Weights for model 'default/base' fileset 'missing' not found"),
    ):
        await fetch_model_entity("default/base", "default", MagicMock())


async def test_fetch_model_entity_without_weights_fileset_skips_files_service() -> None:
    model = SimpleNamespace(name="api-model", workspace="default", fileset=None)
    _, files, dispatch = _clients(model)

    with patch(
        "nmp.customization_common.service.platform_client.client_from_platform",
        side_effect=dispatch,
    ):
        result = await fetch_model_entity("api-model", "default", MagicMock())

    assert result is model
    files.get_fileset.assert_not_awaited()
