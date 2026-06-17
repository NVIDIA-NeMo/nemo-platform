# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bound callables returned by endpoint descriptors.

When an endpoint is accessed as an attribute on a :class:`NemoClient` or
:class:`AsyncNemoClient` instance, its ``__get__`` returns one of these
bound callables.  The bound callable's ``__call__`` constructs a
:class:`PreparedRequest` via the endpoint and sends it via the client.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
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
    BinaryBodyRequestable,
    BinaryContent,
    BodyRequestable,
    ModelT,
    NoBodyRequestable,
    PathT,
    RequestT,
    ResponseT,
    ResponseT_JSON,
    Stream,
)


# ---------------------------------------------------------------------------
# Sync bound callables
# ---------------------------------------------------------------------------


class SyncBoundBodyCall(Generic[PathT, RequestT, ResponseT]):
    """Sync callable returned when a :class:`BodyEndpoint` is accessed on a :class:`NemoClient`."""

    def __init__(self, client: NemoClient, endpoint: BodyRequestable[PathT, RequestT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, BinaryContent], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, Stream[ModelT]], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, None], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[None]: ...
    @overload
    def __call__(
        self: SyncBoundBodyCall[PathT, RequestT, ResponseT_JSON], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    def __call__(
        self, payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        return self._client.send(self._endpoint.request(payload, **kw))


class SyncBoundBinaryBodyCall(Generic[PathT, ResponseT]):
    """Sync callable returned when a :class:`BinaryBodyEndpoint` is accessed on a :class:`NemoClient`."""

    def __init__(self, client: NemoClient, endpoint: BinaryBodyRequestable[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, BinaryContent],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, Stream[ModelT]],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, None],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[None]: ...
    @overload
    def __call__(
        self: SyncBoundBinaryBodyCall[PathT, ResponseT_JSON],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[ResponseT_JSON]: ...

    def __call__(
        self, content: bytes | Iterable[bytes] | AsyncIterable[bytes], **kw: Unpack[PathT]
    ) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        return self._client.send(self._endpoint.request(content, **kw))


class SyncBoundNoBodyCall(Generic[PathT, ResponseT]):
    """Sync callable returned when a :class:`NoBodyEndpoint` is accessed on a :class:`NemoClient`."""

    def __init__(self, client: NemoClient, endpoint: NoBodyRequestable[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    def __call__(self: SyncBoundNoBodyCall[PathT, BinaryContent], **kw: Unpack[PathT]) -> NemoBinaryResponse: ...
    @overload
    def __call__(
        self: SyncBoundNoBodyCall[PathT, Stream[ModelT]], **kw: Unpack[PathT]
    ) -> NemoStreamResponse[ModelT]: ...
    @overload
    def __call__(self: SyncBoundNoBodyCall[PathT, None], **kw: Unpack[PathT]) -> NemoResponse[None]: ...
    @overload
    def __call__(
        self: SyncBoundNoBodyCall[PathT, ResponseT_JSON], **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    def __call__(self, **kw: Unpack[PathT]) -> NemoResponse | NemoBinaryResponse | NemoStreamResponse:
        return self._client.send(self._endpoint.request(**kw))


# ---------------------------------------------------------------------------
# Async bound callables
# ---------------------------------------------------------------------------


class AsyncBoundBodyCall(Generic[PathT, RequestT, ResponseT]):
    """Async callable returned when a :class:`BodyEndpoint` is accessed on an :class:`AsyncNemoClient`."""

    def __init__(self, client: AsyncNemoClient, endpoint: BodyRequestable[PathT, RequestT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, BinaryContent], payload: RequestT, **kw: Unpack[PathT]
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, Stream[ModelT]], payload: RequestT, **kw: Unpack[PathT]
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, None], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[None]: ...
    @overload
    async def __call__(
        self: AsyncBoundBodyCall[PathT, RequestT, ResponseT_JSON], payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    async def __call__(
        self, payload: RequestT, **kw: Unpack[PathT]
    ) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        return await self._client.send(self._endpoint.request(payload, **kw))


class AsyncBoundBinaryBodyCall(Generic[PathT, ResponseT]):
    """Async callable returned when a :class:`BinaryBodyEndpoint` is accessed on an :class:`AsyncNemoClient`."""

    def __init__(self, client: AsyncNemoClient, endpoint: BinaryBodyRequestable[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, BinaryContent],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, Stream[ModelT]],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, None],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[None]: ...
    @overload
    async def __call__(
        self: AsyncBoundBinaryBodyCall[PathT, ResponseT_JSON],
        content: bytes | Iterable[bytes] | AsyncIterable[bytes],
        **kw: Unpack[PathT],
    ) -> NemoResponse[ResponseT_JSON]: ...

    async def __call__(
        self, content: bytes | Iterable[bytes] | AsyncIterable[bytes], **kw: Unpack[PathT]
    ) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        return await self._client.send(self._endpoint.request(content, **kw))


class AsyncBoundNoBodyCall(Generic[PathT, ResponseT]):
    """Async callable returned when a :class:`NoBodyEndpoint` is accessed on an :class:`AsyncNemoClient`."""

    def __init__(self, client: AsyncNemoClient, endpoint: NoBodyRequestable[PathT, ResponseT]) -> None:
        self._client = client
        self._endpoint = endpoint

    @overload
    async def __call__(
        self: AsyncBoundNoBodyCall[PathT, BinaryContent], **kw: Unpack[PathT]
    ) -> AsyncNemoBinaryResponse: ...
    @overload
    async def __call__(
        self: AsyncBoundNoBodyCall[PathT, Stream[ModelT]], **kw: Unpack[PathT]
    ) -> AsyncNemoStreamResponse[ModelT]: ...
    @overload
    async def __call__(self: AsyncBoundNoBodyCall[PathT, None], **kw: Unpack[PathT]) -> NemoResponse[None]: ...
    @overload
    async def __call__(
        self: AsyncBoundNoBodyCall[PathT, ResponseT_JSON], **kw: Unpack[PathT]
    ) -> NemoResponse[ResponseT_JSON]: ...

    async def __call__(self, **kw: Unpack[PathT]) -> NemoResponse | AsyncNemoBinaryResponse | AsyncNemoStreamResponse:
        return await self._client.send(self._endpoint.request(**kw))
