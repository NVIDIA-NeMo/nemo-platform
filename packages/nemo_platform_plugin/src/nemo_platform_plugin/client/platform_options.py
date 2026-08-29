# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed options exported by the platform SDK for typed client construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx
from nemo_platform_plugin.client.auth import AsyncTokenProvider, TokenProvider
from nemo_platform_plugin.client.types import RetryPolicy

URLResolver = Callable[[str], str | httpx.URL]


@dataclass(frozen=True)
class SyncPlatformClientOptions:
    base_url: str
    workspace: str | None
    default_headers: Mapping[str, str] | None
    timeout: float | httpx.Timeout | None
    retry: RetryPolicy
    http_client: httpx.Client
    url_resolver: URLResolver
    auth: TokenProvider | None = None


@dataclass(frozen=True)
class AsyncPlatformClientOptions:
    base_url: str
    workspace: str | None
    default_headers: Mapping[str, str] | None
    timeout: float | httpx.Timeout | None
    retry: RetryPolicy
    http_client: httpx.AsyncClient
    url_resolver: URLResolver
    auth: TokenProvider | AsyncTokenProvider | None = None
