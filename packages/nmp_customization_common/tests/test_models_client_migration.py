# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Model-entity resolution through the typed Models client, over a mocked httpx transport.

Driving a real ``NemoClient`` -> ``client_from_platform`` -> ``ModelsClient``
chain asserts the wire contract (method, path, query string, parsed model and
error mapping) rather than restating the call the implementation happens to make.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.errors import NemoTransportError
from nemo_platform_plugin.models.types import ModelEntity
from nmp.customization_common.service.platform_client import fetch_model_entity
from nmp.customization_common.tasks.model_entity.run import (
    TRANSIENT_RETRYABLE_EXCEPTIONS,
    ModelEntityCreationError,
    ModelEntityRunner,
)

BASE = "http://test:8000"


def _model_json(name: str = "model", workspace: str = "other", **extra: object) -> dict:
    base = {
        "id": f"model-{name}",
        "name": name,
        "workspace": workspace,
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-01T00:00:00Z",
    }
    base.update(extra)
    return base


def _recording_transport(
    status: int = 200, payload: dict | None = None
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, request=request, json=payload if payload is not None else _model_json())

    return httpx.MockTransport(handler), seen


@pytest.mark.asyncio
async def test_fetch_model_entity_requests_verbose_model() -> None:
    transport, seen = _recording_transport()
    sdk = AsyncNemoClient(base_url=BASE, workspace="default", http_client=httpx.AsyncClient(transport=transport))

    result = await fetch_model_entity("other/model", "default", sdk)

    assert isinstance(result, ModelEntity)
    assert (result.workspace, result.name) == ("other", "model")
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/apis/models/v2/workspaces/other/models/model"
    assert seen[0].url.params["verbose"] == "true"


@pytest.mark.asyncio
async def test_fetch_model_entity_maps_403_to_permission_error() -> None:
    transport, _ = _recording_transport(403, {"detail": "denied"})
    sdk = AsyncNemoClient(base_url=BASE, workspace="default", http_client=httpx.AsyncClient(transport=transport))

    with pytest.raises(PermissionError, match="other/model"):
        await fetch_model_entity("other/model", "default", sdk)


@pytest.mark.asyncio
async def test_fetch_model_entity_maps_404_to_value_error() -> None:
    transport, _ = _recording_transport(404, {"detail": "missing"})
    sdk = AsyncNemoClient(base_url=BASE, workspace="default", http_client=httpx.AsyncClient(transport=transport))

    with pytest.raises(ValueError, match="other/model"):
        await fetch_model_entity("other/model", "default", sdk)


def test_model_entity_runner_resolves_qualified_ref() -> None:
    transport, seen = _recording_transport()
    sdk = NemoClient(base_url=BASE, workspace="default", http_client=httpx.Client(transport=transport))

    result = ModelEntityRunner(sdk, MagicMock()).get_model_entity("other/model", "default")

    assert isinstance(result, ModelEntity)
    assert (result.workspace, result.name) == ("other", "model")
    assert len(seen) == 1
    assert seen[0].url.path == "/apis/models/v2/workspaces/other/models/model"


def test_model_entity_runner_falls_back_to_fileset_workspace() -> None:
    """A bare ``name`` resolves against the fileset workspace, not the client default."""
    transport, seen = _recording_transport(payload=_model_json(workspace="fs-ws"))
    sdk = NemoClient(base_url=BASE, workspace="default", http_client=httpx.Client(transport=transport))

    ModelEntityRunner(sdk, MagicMock()).get_model_entity("model", "fs-ws")

    assert seen[0].url.path == "/apis/models/v2/workspaces/fs-ws/models/model"


def test_model_entity_runner_maps_404_to_creation_error() -> None:
    transport, _ = _recording_transport(404, {"detail": "missing"})
    sdk = NemoClient(base_url=BASE, workspace="default", http_client=httpx.Client(transport=transport))

    with pytest.raises(ModelEntityCreationError, match="other/model not found"):
        ModelEntityRunner(sdk, MagicMock()).get_model_entity("other/model", "default")


def test_transport_failures_surface_as_retryable_nemo_errors() -> None:
    """A dropped connection must arrive as a member of the runner's retry tuple.

    The migration dropped the raw ``httpx`` exceptions from that tuple, so this
    pins the replacement actually covering them.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    sdk = NemoClient(
        base_url=BASE,
        workspace="default",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(NemoTransportError) as exc:
        ModelEntityRunner(sdk, MagicMock()).get_model_entity("other/model", "default")

    assert isinstance(exc.value, TRANSIENT_RETRYABLE_EXCEPTIONS)
