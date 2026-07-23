# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for bridging sync and async NeMo Platform SDK entry points.

``sync_to_async_sdk`` exists because Data Designer validation and provider
resolution are async-first: they call platform services to validate filesets,
secrets, personas, and model providers before handing work to the upstream
Data Designer engine, and in the case of preview this work happens within the
FastAPI process with an injected ``AsyncNeMoPlatform``. However, some legitimate
callers still start with a sync ``NeMoPlatform`` instance, notably sync SDK/CLI
validation and job-container runtime code, so those paths need an async sibling
that preserves the same base URL, workspace, headers, query defaults, timeout,
and retry settings.

``async_to_sync_sdk`` is the inverse boundary used by Data Designer's fileset
filesystem integration. DuckDB and upstream Data Designer seed/person readers
call fsspec synchronously, so the fileset filesystem must be constructed in
sync fsspec mode even when the API process starts with an injected
``AsyncNeMoPlatform``.
"""

import httpx
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform


def sync_to_async_sdk(sdk: NeMoPlatform) -> AsyncNeMoPlatform:
    """Build an async :class:`AsyncNeMoPlatform` mirroring the sync SDK's config."""
    async_sdk = AsyncNeMoPlatform(
        base_url=sdk.base_url,
        default_headers=dict(sdk._custom_headers) if sdk._custom_headers else None,
        default_query=dict(sdk._custom_query) if sdk._custom_query else None,
        timeout=sdk.timeout,
        max_retries=sdk.max_retries,
        workspace=sdk.workspace,
    )
    _attach_transport_and_router(original=sdk, clone=async_sdk)
    return async_sdk


def async_to_sync_sdk(async_sdk: AsyncNeMoPlatform) -> NeMoPlatform:
    """Build a sync :class:`NeMoPlatform` mirroring an async SDK's config."""
    sdk = NeMoPlatform(
        base_url=async_sdk.base_url,
        default_headers=dict(async_sdk._custom_headers) if async_sdk._custom_headers else None,
        default_query=dict(async_sdk._custom_query) if async_sdk._custom_query else None,
        timeout=async_sdk.timeout,
        max_retries=async_sdk.max_retries,
        workspace=async_sdk.workspace,
    )
    _attach_transport_and_router(original=async_sdk, clone=sdk)
    return sdk


def _attach_transport_and_router(
    *, clone: NeMoPlatform | AsyncNeMoPlatform, original: NeMoPlatform | AsyncNeMoPlatform
) -> None:
    transport = getattr(original._client, "_transport", None)
    if isinstance(transport, httpx.ASGITransport):
        setattr(clone._client, "asgi_app", transport.app)
    if router := getattr(original, "_nmp_request_router", None):
        setattr(clone, "_nmp_request_router", router)
        clone._prepare_url = router.resolve
