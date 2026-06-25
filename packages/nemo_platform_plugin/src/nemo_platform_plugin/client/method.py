# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Optional convenience layer: turn endpoint methods into client methods.

Plugin authors define endpoints once in a collection class, then use
``method()`` to bridge them onto a client class::

    class _ExampleMethods:
        hello = method(ExampleEndpoints.hello)
        create_item = method(ExampleEndpoints.create_item)

    class ExampleClient(_ExampleMethods, NemoClient): pass
    class AsyncExampleClient(_ExampleMethods, AsyncNemoClient): pass

    client = ExampleClient(base_url="...", workspace="default")
    resp = client.hello(name="alice")  # NemoResponse[HelloResponse]

The descriptor dispatches sync vs async based on the client type.
The ``method()`` function is overloaded so that the return type of the
bound callable matches what ``send()`` returns for each response-type
marker (``BinaryContent``, ``Stream[T]``, ``Paginated[T]``, plain model).

Note: ``ty`` shows ``Unknown |`` on the method types due to unannotated
class attributes (astral-sh/ty#3254). The types themselves are correct
and ``pyright`` resolves them cleanly.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, Coroutine, Generic, TypeVar, overload

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.response import (
    AsyncNemoBinaryResponse,
    AsyncNemoPaginatedResponse,
    AsyncNemoStreamResponse,
    NemoBinaryResponse,
    NemoPaginatedResponse,
    NemoResponse,
    NemoStreamResponse,
)
from nemo_platform_plugin.client.types import (
    BinaryContent,
    ModelT,
    P,
    Paginated,
    PreparedRequest,
    ResponseT,
    Stream,
)

# TypeVar for the sync return type of the bound callable.
SyncReturnT = TypeVar("SyncReturnT")
# TypeVar for the async return type of the bound callable.
AsyncReturnT = TypeVar("AsyncReturnT")


class EndpointMethod(Generic[P, SyncReturnT, AsyncReturnT]):
    """Descriptor that binds an endpoint to a client instance.

    When accessed on a :class:`NemoClient`, returns a sync callable
    with return type ``SyncReturnT``.
    When accessed on an :class:`AsyncNemoClient`, returns an async callable
    with return type ``AsyncReturnT``.

    The type parameters are set by the ``method()`` overloads to match
    the response type that ``send()`` returns for each endpoint marker.
    """

    def __init__(self, endpoint_fn: Callable[P, PreparedRequest]) -> None:
        self._endpoint_fn = endpoint_fn

    @overload
    def __get__(self, obj: NemoClient, objtype: type | None = None) -> Callable[P, SyncReturnT]: ...
    @overload
    def __get__(
        self, obj: AsyncNemoClient, objtype: type | None = None
    ) -> Callable[P, Coroutine[Any, Any, AsyncReturnT]]: ...

    def __get__(self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None) -> object:
        assert obj is not None
        if isinstance(obj, AsyncNemoClient):

            @functools.wraps(self._endpoint_fn)
            async def async_bound(*args: P.args, **kwargs: P.kwargs) -> AsyncReturnT:
                return await obj.send(self._endpoint_fn(*args, **kwargs))  # type: ignore[return-value]

            return async_bound

        @functools.wraps(self._endpoint_fn)
        def sync_bound(*args: P.args, **kwargs: P.kwargs) -> SyncReturnT:
            return obj.send(self._endpoint_fn(*args, **kwargs))  # type: ignore[return-value]

        return sync_bound


# ---------------------------------------------------------------------------
# method() overloads — one per response-type marker
# ---------------------------------------------------------------------------


@overload
def method(
    endpoint_fn: Callable[P, PreparedRequest[BinaryContent]],
) -> EndpointMethod[P, NemoBinaryResponse, AsyncNemoBinaryResponse]: ...


@overload
def method(
    endpoint_fn: Callable[P, PreparedRequest[Stream[ModelT]]],
) -> EndpointMethod[P, NemoStreamResponse[ModelT], AsyncNemoStreamResponse[ModelT]]: ...


@overload
def method(
    endpoint_fn: Callable[P, PreparedRequest[Paginated[ModelT, Any]]],
) -> EndpointMethod[P, NemoPaginatedResponse[ModelT], AsyncNemoPaginatedResponse[ModelT]]: ...


@overload
def method(
    endpoint_fn: Callable[P, PreparedRequest[None]],
) -> EndpointMethod[P, NemoResponse[None], NemoResponse[None]]: ...


@overload
def method(
    endpoint_fn: Callable[P, PreparedRequest[ResponseT]],
) -> EndpointMethod[P, NemoResponse[ResponseT], NemoResponse[ResponseT]]: ...


def method(endpoint_fn: Callable[P, PreparedRequest]) -> EndpointMethod:
    """Create an :class:`EndpointMethod` descriptor from an endpoint function.

    The return type of the bound callable is determined by the endpoint's
    response-type marker via overloads, matching the dispatch in ``send()``.

    Usage::

        class _MyMethods:
            create_item = method(MyEndpoints.create_item)   # NemoResponse[Item]
            list_items = method(MyEndpoints.list_items)      # NemoPaginatedResponse[Item]
            download = method(MyEndpoints.download)          # NemoBinaryResponse
    """
    return EndpointMethod(endpoint_fn)
