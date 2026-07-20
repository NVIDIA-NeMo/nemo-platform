# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""VirtualModelsClient sync and async transport tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from nemo_platform_plugin.client.errors import ConflictError, NotFoundError
from nemo_platform_plugin.inference_middleware import VirtualModel
from nemo_platform_plugin.virtual_models.client import AsyncVirtualModelsClient, VirtualModelsClient
from nemo_platform_plugin.virtual_models.types import CreateVirtualModelRequest, UpdateVirtualModelRequest
from pydantic import TypeAdapter

BASE = "http://test:8000"
PATH = "/apis/inference-gateway/v2/workspaces/default/virtual-models"


def _virtual_model_json(name: str) -> dict[str, object]:
    return {
        "id": f"vm-{name}",
        "name": name,
        "workspace": "default",
        "project": None,
        "default_model_entity": "default/llama",
        "autoprovisioned": False,
        "models": [{"model": "default/llama", "backend_format": None}],
        "request_middleware": [],
        "response_middleware": [],
        "post_response_middleware": [],
        "override_proxy": None,
        "created_at": "2026-01-01T00:00:00Z",
        "created_by": "creator",
        "updated_at": "2026-01-02T00:00:00Z",
        "updated_by": "updater",
        "parent": "parent-id",
    }


def _page(data: list[dict[str, object]], page: int, total_pages: int) -> dict[str, object]:
    return {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": 1,
            "current_page_size": len(data),
            "total_pages": total_pages,
            "total_results": total_pages,
        },
        "sort": "-created_at",
        "filter": None,
    }


def test_type_adapter_retains_virtual_model_wire_metadata() -> None:
    result = TypeAdapter(VirtualModel).validate_python(_virtual_model_json("router"))

    assert result.id == "vm-router"
    assert result.created_at is not None
    assert result.created_by == "creator"
    assert result.updated_at is not None
    assert result.updated_by == "updater"
    assert result.parent == "parent-id"


def test_sync_create_returns_typed_virtual_model_and_sends_exact_request() -> None:
    http = MagicMock(spec=httpx.Client)
    http.request.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", BASE + PATH),
        json=_virtual_model_json("router"),
    )
    client = VirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    result = client.create_virtual_model(
        body=CreateVirtualModelRequest(name="router", default_model_entity="default/llama")
    ).data()

    assert isinstance(result, VirtualModel)
    assert result.id == "vm-router"
    assert result.name == "router"
    assert result.created_at is not None
    args, kwargs = http.request.call_args
    assert args == ("POST", BASE + PATH)
    assert kwargs["content"] == b'{"default_model_entity":"default/llama","name":"router"}'
    assert kwargs["params"] is None


def test_sync_list_paginates_and_preserves_filter_query() -> None:
    http = MagicMock(spec=httpx.Client)
    http.request.side_effect = [
        httpx.Response(200, request=httpx.Request("GET", BASE + PATH), json=_page([_virtual_model_json("a")], 1, 2)),
        httpx.Response(200, request=httpx.Request("GET", BASE + PATH), json=_page([_virtual_model_json("b")], 2, 2)),
    ]
    client = VirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    names = [
        model.name
        for model in client.list_virtual_models(
            query_params={"page_size": 1, "filter": "name:a", "exclude_autoprovisioned": True}
        ).items()
    ]

    assert names == ["a", "b"]
    assert http.request.call_args_list[0].kwargs["params"] == {
        "page_size": 1,
        "filter": "name:a",
        "exclude_autoprovisioned": True,
    }
    assert http.request.call_args_list[1].kwargs["params"] == {
        "page_size": 1,
        "filter": "name:a",
        "exclude_autoprovisioned": True,
        "page": 2,
    }


def test_sync_update_returns_typed_virtual_model() -> None:
    http = MagicMock(spec=httpx.Client)
    http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("PATCH", BASE + PATH + "/router"),
        json=_virtual_model_json("router") | {"default_model_entity": None},
    )
    client = VirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    result = client.update_virtual_model(
        name="router", body=UpdateVirtualModelRequest(default_model_entity=None)
    ).data()

    assert isinstance(result, VirtualModel)
    assert result.default_model_entity is None
    assert http.request.call_args.args == ("PATCH", BASE + PATH + "/router")
    assert http.request.call_args.kwargs["content"] == b'{"default_model_entity":null}'


def test_sync_delete_204_returns_none() -> None:
    http = MagicMock(spec=httpx.Client)
    http.request.return_value = httpx.Response(
        204,
        request=httpx.Request("DELETE", BASE + PATH + "/router"),
    )
    client = VirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    response = client.delete_virtual_model(name="router")

    assert response.data() is None
    assert response.http_response.status_code == 204


def test_sync_get_not_found_maps_error() -> None:
    http = MagicMock(spec=httpx.Client)
    http.request.return_value = httpx.Response(
        404,
        request=httpx.Request("GET", BASE + PATH + "/missing"),
        json={"detail": "VirtualModel not found"},
    )
    client = VirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    with pytest.raises(NotFoundError) as exc:
        client.get_virtual_model(name="missing")

    assert exc.value.status_code == 404


def test_sync_create_conflict_maps_error() -> None:
    http = MagicMock(spec=httpx.Client)
    http.request.return_value = httpx.Response(
        409,
        request=httpx.Request("POST", BASE + PATH),
        json={"detail": "VirtualModel already exists"},
    )
    client = VirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    with pytest.raises(ConflictError) as exc:
        client.create_virtual_model(body=CreateVirtualModelRequest(name="router"))

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_async_create_returns_typed_virtual_model() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.request.return_value = httpx.Response(
        201,
        request=httpx.Request("POST", BASE + PATH),
        json=_virtual_model_json("router"),
    )
    client = AsyncVirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    result = (
        await client.create_virtual_model(
            body=CreateVirtualModelRequest(name="router", default_model_entity="default/llama")
        )
    ).data()

    assert isinstance(result, VirtualModel)
    assert result.name == "router"
    assert http.request.call_args.args == ("POST", BASE + PATH)


@pytest.mark.asyncio
async def test_async_get_returns_typed_virtual_model_with_wire_metadata() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", BASE + PATH + "/router"),
        json=_virtual_model_json("router"),
    )
    client = AsyncVirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    result = (await client.get_virtual_model(name="router")).data()

    assert isinstance(result, VirtualModel)
    assert result.id == "vm-router"
    assert result.created_at is not None
    assert result.created_by == "creator"
    assert result.updated_at is not None
    assert result.updated_by == "updater"
    assert result.parent == "parent-id"
    assert http.request.call_args.args == ("GET", BASE + PATH + "/router")


@pytest.mark.asyncio
async def test_async_list_paginates() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.request.side_effect = [
        httpx.Response(200, request=httpx.Request("GET", BASE + PATH), json=_page([_virtual_model_json("a")], 1, 2)),
        httpx.Response(200, request=httpx.Request("GET", BASE + PATH), json=_page([_virtual_model_json("b")], 2, 2)),
    ]
    client = AsyncVirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    response = await client.list_virtual_models(query_params={"page_size": 1})
    names = [model.name async for model in response.items()]

    assert names == ["a", "b"]
    assert http.request.call_args_list[1].kwargs["params"] == {"page_size": 1, "page": 2}


@pytest.mark.asyncio
async def test_async_update_excludes_unset_and_preserves_explicit_null_and_list() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.request.return_value = httpx.Response(
        200,
        request=httpx.Request("PATCH", BASE + PATH + "/router"),
        json=_virtual_model_json("router") | {"default_model_entity": None, "request_middleware": []},
    )
    client = AsyncVirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    result = (
        await client.update_virtual_model(
            name="router",
            body=UpdateVirtualModelRequest(default_model_entity=None, request_middleware=[]),
        )
    ).data()

    assert isinstance(result, VirtualModel)
    assert result.default_model_entity is None
    assert result.request_middleware == []
    assert http.request.call_args.args == ("PATCH", BASE + PATH + "/router")
    assert http.request.call_args.kwargs["content"] == b'{"default_model_entity":null,"request_middleware":[]}'


@pytest.mark.asyncio
async def test_async_delete_204_returns_none() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.request.return_value = httpx.Response(
        204,
        request=httpx.Request("DELETE", BASE + PATH + "/router"),
    )
    client = AsyncVirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    response = await client.delete_virtual_model(name="router")

    assert response.data() is None
    assert response.http_response.status_code == 204


@pytest.mark.asyncio
async def test_async_get_not_found_maps_error() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.request.return_value = httpx.Response(
        404,
        request=httpx.Request("GET", BASE + PATH + "/missing"),
        json={"detail": "VirtualModel not found"},
    )
    client = AsyncVirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    with pytest.raises(NotFoundError) as exc:
        await client.get_virtual_model(name="missing")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_async_create_conflict_maps_error() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.request.return_value = httpx.Response(
        409,
        request=httpx.Request("POST", BASE + PATH),
        json={"detail": "VirtualModel already exists"},
    )
    client = AsyncVirtualModelsClient(base_url=BASE, workspace="default", http_client=http)

    with pytest.raises(ConflictError) as exc:
        await client.create_virtual_model(body=CreateVirtualModelRequest(name="router"))

    assert exc.value.status_code == 409
