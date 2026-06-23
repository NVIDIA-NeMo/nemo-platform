# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bound callables returned by endpoint descriptors.

When an endpoint is accessed as an attribute on a :class:`NemoClient` or
:class:`AsyncNemoClient` instance, its ``__get__`` returns one of these
bound callables.  The self-type overloads on ``__call__`` dispatch the
correct argument signature and return type based on ``RequestT`` and
``ResponseT``.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Callable, Iterable
from typing import Generic, Unpack, overload

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.response import (
    AsyncNemoBinaryResponse,
    AsyncNemoStreamResponse,
    NemoBinaryResponse,
    NemoResponse,
    NemoStreamResponse,
)
from nemo_platform_plugin.client.types import (
    BinaryContent,
    BodyRequestT,
    ModelT,
    PathT,
    PreparedRequest,
    RequestT,
    ResponseT,
    Stream,
)


class SyncBoundCall(Generic[PathT, RequestT, ResponseT]):
    """Sync callable returned when an :class:`Endpoint` is accessed on a :class:`NemoClient`."""

    def __init__(self, client: NemoClient, request_fn: Callable[..., PreparedRequest[ResponseT]]) -> None:
        self._client = client
        self._request_fn = request_fn

    # -- Body (RequestT is BaseModel) × response variants --

    @overload
    def __call__(
        self: SyncBoundCall[PathT, BodyRequestT, BinaryContent], payload: BodyRequestT, **kw: Unpack[PathT]
    ) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundCall[PathT, BodyRequestT, Stream[ModelT]], payload: BodyRequestT, **kw: Unpack[PathT]
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(
        self: SyncBoundCall[PathT, BodyRequestT, ResponseT], payload: BodyRequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT]: ...

    # -- Binary (RequestT is BinaryContent) × response variants --

    @overload
    def __call__(
        self: SyncBoundCall[PathT, BinaryContent, BinaryContent],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundCall[PathT, BinaryContent, Stream[ModelT]],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(
        self: SyncBoundCall[PathT, BinaryContent, ResponseT],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[ResponseT]: ...

    # -- No body (RequestT is None) × response variants --

    @overload
    def __call__(self: SyncBoundCall[PathT, None, BinaryContent], **kw: Unpack[PathT]) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundCall[PathT, None, Stream[ModelT]], **kw: Unpack[PathT]
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(self: SyncBoundCall[PathT, None, ResponseT], **kw: Unpack[PathT]) -> NemoResponse[ResponseT]: ...

    def __call__(self, *args: object, **kw: object) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        return self._client.send(self._request_fn(*args, **kw))


class AsyncBoundCall(Generic[PathT, RequestT, ResponseT]):
    """Async callable returned when an :class:`Endpoint` is accessed on an :class:`AsyncNemoClient`."""

    def __init__(self, client: AsyncNemoClient, request_fn: Callable[..., PreparedRequest[ResponseT]]) -> None:
        self._client = client
        self._request_fn = request_fn

    # -- Body (RequestT is BaseModel) × response variants --

    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, BodyRequestT, BinaryContent], payload: BodyRequestT, **kw: Unpack[PathT]
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, BodyRequestT, Stream[ModelT]], payload: BodyRequestT, **kw: Unpack[PathT]
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, BodyRequestT, ResponseT], payload: BodyRequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT]: ...

    # -- Binary (RequestT is BinaryContent) × response variants --

    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, BinaryContent, BinaryContent],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, BinaryContent, Stream[ModelT]],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, BinaryContent, ResponseT],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[ResponseT]: ...

    # -- No body (RequestT is None) × response variants --

    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, None, BinaryContent], **kw: Unpack[PathT]
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, None, Stream[ModelT]], **kw: Unpack[PathT]
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(
        self: AsyncBoundCall[PathT, None, ResponseT], **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT]: ...

    async def __call__(
        self, *args: object, **kw: object
    ) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        return await self._client.send(self._request_fn(*args, **kw))
