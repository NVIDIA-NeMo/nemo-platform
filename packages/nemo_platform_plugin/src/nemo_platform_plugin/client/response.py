# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP response wrapper that preserves transport metadata alongside the parsed body."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel

ResponseT = TypeVar("ResponseT", bound=BaseModel | None)


@dataclass(frozen=True, slots=True)
class NemoResponse(Generic[ResponseT]):
    """Typed HTTP response — carries the parsed body and the raw httpx response.

    The type parameter ``ResponseT`` is inferred from the :class:`~.endpoint.Endpoint`
    definition, so ``resp.body`` is fully typed without casts.

    Example::

        resp = client.send(CREATE_USER(CreateUserRequest(name="alice"), workspace="default"))
        resp.body             # UserResponse(name="alice", id=42)
        resp.http_response    # full httpx.Response — status, headers, etc.

        # Shorthand for the common case:
        user = resp.data()  # raises on non-2xx, otherwise returns body
    """

    http_response: httpx.Response
    body: ResponseT

    def data(self) -> ResponseT:
        """Return the body if the status is 2xx, otherwise raise."""
        if not (200 <= self.http_response.status_code < 300):
            raise NemoHTTPError(self.http_response, self.body)
        return self.body


class NemoHTTPError(Exception):
    """Raised by :meth:`NemoResponse.data` on non-2xx responses."""

    def __init__(self, http_response: httpx.Response, body: object) -> None:
        self.http_response = http_response
        self.body = body
        super().__init__(f"HTTP {http_response.status_code}")
