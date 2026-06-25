# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authentication protocols and helpers for NemoClient.

Defines the protocols that any token provider must satisfy, plus simple
concrete implementations.

OIDC-specific machinery lives in :mod:`~.oidc` (token provider, token set,
discovery) and :mod:`~.oidc_factory` (provider caching, config persistence).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class TokenProvider(Protocol):
    """Sync protocol for objects that can supply an access token."""

    def get_access_token(self) -> str: ...


@runtime_checkable
class AsyncTokenProvider(Protocol):
    """Async protocol for objects that can supply an access token."""

    async def get_access_token(self) -> str: ...


# ---------------------------------------------------------------------------
# StaticToken
# ---------------------------------------------------------------------------


class StaticToken:
    """Wraps a plain token string into a TokenProvider."""

    def __init__(self, token: str) -> None:
        self._token = token

    def get_access_token(self) -> str:
        return self._token

    async def get_access_token_async(self) -> str:
        return self._token


# ---------------------------------------------------------------------------
# Auth errors
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Authentication-related error."""
