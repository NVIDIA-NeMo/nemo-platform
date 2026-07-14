# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Static return-type contracts for the typed client.

The functions in this module are checked by ``ty`` but intentionally not
collected by pytest. They ensure endpoint annotations flow through prepared
requests and both client implementations without being erased to ``Any``.
"""

from typing import assert_type

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient, _parse_json_body
from nemo_platform_plugin.client.endpoint import get
from nemo_platform_plugin.client.response import (
    AsyncNemoPaginatedResponse,
    AsyncNemoStreamResponse,
    NemoPaginatedResponse,
    NemoResponse,
    NemoStreamResponse,
)
from nemo_platform_plugin.client.types import Paginated, PreparedRequest, Stream
from pydantic import BaseModel


class Item(BaseModel):
    name: str


@get("/items/{name}")
def get_item(*, name: str) -> Item:
    raise NotImplementedError


@get("/items")
def get_item_list() -> list[Item]:
    raise NotImplementedError


@get("/items/pages")
def get_item_pages() -> Paginated[Item]:
    raise NotImplementedError


@get("/items/stream")
def get_item_stream() -> Stream[Item]:
    raise NotImplementedError


def _check_sync_return_types(client: NemoClient) -> None:
    item_request = get_item(name="one")
    assert_type(item_request, PreparedRequest[Item])
    assert_type(client.send(item_request), NemoResponse[Item])

    list_request = get_item_list()
    assert_type(list_request, PreparedRequest[list[Item]])
    assert_type(client.send(list_request), NemoResponse[list[Item]])
    assert_type(client.send(get_item_pages()), NemoPaginatedResponse[Item])
    assert_type(client.send(get_item_stream()), NemoStreamResponse[Item])

    assert_type(_parse_json_body(Item, {"name": "one"}), Item)
    assert_type(_parse_json_body(list[Item], [{"name": "one"}]), list[Item])


async def _check_async_return_types(client: AsyncNemoClient) -> None:
    assert_type(await client.send(get_item(name="one")), NemoResponse[Item])
    assert_type(await client.send(get_item_list()), NemoResponse[list[Item]])
    assert_type(await client.send(get_item_pages()), AsyncNemoPaginatedResponse[Item])
    assert_type(await client.send(get_item_stream()), AsyncNemoStreamResponse[Item])
