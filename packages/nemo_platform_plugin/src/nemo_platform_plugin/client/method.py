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

Note: ``ty`` shows ``Unknown |`` on the method types due to unannotated
class attributes (astral-sh/ty#3254). The types themselves are correct
and ``pyright`` resolves them cleanly.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, Coroutine, Generic, overload

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.response import (
    AsyncNemoPaginatedResponse,
    NemoPaginatedResponse,
    NemoResponse,
)
from nemo_platform_plugin.client.types import ModelT, P, Paginated, PreparedRequest, ResponseT


class EndpointMethod(Generic[P, ResponseT]):
    """Descriptor that binds an endpoint to a client instance.

    When accessed on a :class:`NemoClient`, returns a sync callable.
    When accessed on an :class:`AsyncNemoClient`, returns an async callable.
    Both preserve the endpoint's full ``ParamSpec`` signature.
    """

    def __init__(self, endpoint_fn: Callable[P, PreparedRequest[ResponseT]]) -> None:
        self._endpoint_fn = endpoint_fn

    @overload
    def __get__(self, obj: NemoClient, objtype: type | None = None) -> Callable[P, NemoResponse[ResponseT]]: ...
    @overload
    def __get__(
        self, obj: AsyncNemoClient, objtype: type | None = None
    ) -> Callable[P, Coroutine[Any, Any, NemoResponse[ResponseT]]]: ...

    def __get__(self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None) -> object:
        assert obj is not None
        if isinstance(obj, AsyncNemoClient):

            @functools.wraps(self._endpoint_fn)
            async def async_bound(*args: P.args, **kwargs: P.kwargs) -> NemoResponse[ResponseT]:
                return await obj.send(self._endpoint_fn(*args, **kwargs))

            return async_bound

        @functools.wraps(self._endpoint_fn)
        def sync_bound(*args: P.args, **kwargs: P.kwargs) -> NemoResponse[ResponseT]:
            return obj.send(self._endpoint_fn(*args, **kwargs))  # type: ignore[return-value]

        return sync_bound


class PaginatedEndpointMethod(Generic[P, ModelT]):
    """Descriptor for endpoints that return ``Paginated[T]``.

    Like :class:`EndpointMethod` but returns
    :class:`~nemo_platform_plugin.client.response.NemoPaginatedResponse`
    instead of :class:`~nemo_platform_plugin.client.response.NemoResponse`.
    """

    def __init__(self, endpoint_fn: Callable[P, PreparedRequest]) -> None:
        self._endpoint_fn = endpoint_fn

    @overload
    def __get__(self, obj: NemoClient, objtype: type | None = None) -> Callable[P, NemoPaginatedResponse[ModelT]]: ...
    @overload
    def __get__(
        self, obj: AsyncNemoClient, objtype: type | None = None
    ) -> Callable[P, Coroutine[Any, Any, AsyncNemoPaginatedResponse[ModelT]]]: ...

    def __get__(self, obj: NemoClient | AsyncNemoClient | None, objtype: type | None = None) -> object:
        assert obj is not None
        if isinstance(obj, AsyncNemoClient):

            @functools.wraps(self._endpoint_fn)
            async def async_bound(*args: P.args, **kwargs: P.kwargs) -> AsyncNemoPaginatedResponse[ModelT]:
                return await obj.send(self._endpoint_fn(*args, **kwargs))  # type: ignore[return-value]

            return async_bound

        @functools.wraps(self._endpoint_fn)
        def sync_bound(*args: P.args, **kwargs: P.kwargs) -> NemoPaginatedResponse[ModelT]:
            return obj.send(self._endpoint_fn(*args, **kwargs))  # type: ignore[return-value]

        return sync_bound


@overload
def method(endpoint_fn: Callable[P, PreparedRequest[Paginated[ModelT, Any]]]) -> PaginatedEndpointMethod[P, ModelT]: ...
@overload
def method(endpoint_fn: Callable[P, PreparedRequest[ResponseT]]) -> EndpointMethod[P, ResponseT]: ...


def method(
    endpoint_fn: Callable[P, PreparedRequest[ResponseT]],
) -> EndpointMethod[P, ResponseT] | PaginatedEndpointMethod:
    """Create a descriptor from an endpoint function.

    Returns :class:`PaginatedEndpointMethod` for endpoints with a
    ``Paginated[T]`` return type, :class:`EndpointMethod` for everything
    else.

    Usage::

        class _MyMethods:
            create_item = method(MyEndpoints.create_item)
            list_items = method(MyEndpoints.list_items)   # Paginated
    """
    # Inspect the endpoint's return type at wiring time to pick the right
    # descriptor class.
    import inspect
    from typing import get_args, get_origin

    hints = inspect.signature(endpoint_fn).return_annotation
    # The endpoint_fn is already wrapped by @get/@post — its return annotation
    # is PreparedRequest[ResponseT].  We need to check the inner ResponseT.
    origin = get_origin(hints)
    if origin is PreparedRequest:
        inner_args = get_args(hints)
        if inner_args and get_origin(inner_args[0]) is Paginated:
            return PaginatedEndpointMethod(endpoint_fn)  # type: ignore[return-value]

    return EndpointMethod(endpoint_fn)
