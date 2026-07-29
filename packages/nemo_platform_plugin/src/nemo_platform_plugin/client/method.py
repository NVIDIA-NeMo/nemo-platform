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
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar, overload

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
    StrategyT,
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
        # Carry the endpoint's identity onto the descriptor so class-level
        # introspection (inspect.signature, help(), autodoc) resolves through
        # __wrapped__ to the real parameter list instead of stopping here.
        # Set directly rather than via functools.update_wrapper, which expects a
        # callable wrapper; a descriptor is not one.
        self.__wrapped__ = endpoint_fn
        for attr in functools.WRAPPER_ASSIGNMENTS:
            try:
                setattr(self, attr, getattr(endpoint_fn, attr))
            except AttributeError:
                pass

    @property
    def endpoint(self) -> Callable[P, PreparedRequest]:
        """The endpoint function this descriptor binds."""
        return self._endpoint_fn

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> EndpointMethod[P, SyncReturnT, AsyncReturnT]: ...
    @overload
    def __get__(self, obj: NemoClient, objtype: type | None = None) -> Callable[P, SyncReturnT]: ...
    @overload
    def __get__(self, obj: AsyncNemoClient, objtype: type | None = None) -> Callable[P, Awaitable[AsyncReturnT]]: ...

    def __get__(self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None) -> object:
        if obj is None:
            # Class-level access. Anything that inspects a client class rather than
            # an instance -- Mock(spec=...), inspect, help(), autodoc -- lands here,
            # and the descriptor protocol says to hand back the descriptor itself.
            return self
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
    endpoint_fn: Callable[P, PreparedRequest[Paginated[ModelT, StrategyT]]],
) -> EndpointMethod[
    P,
    NemoPaginatedResponse[ModelT, StrategyT],
    AsyncNemoPaginatedResponse[ModelT, StrategyT],
]: ...


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
