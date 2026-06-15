# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Execution profile resolution for plugin compilers.

Provides :func:`resolve_profile_kind` which queries the Jobs service's
execution profiles endpoint to determine what executor payload shape
(``"container"`` or ``"subprocess"``) a given ``(provider, profile)``
pair expects.

Plugin compilers use this to emit the correct executor type without
hardcoding profile-name-to-kind mappings::

    from nemo_platform_plugin.jobs.profiles import resolve_profile_kind

    kind = await resolve_profile_kind(async_sdk, "cpu", profile or "default")
    if kind == "subprocess":
        executor = SubprocessExecutionProviderSpec(...)
    else:
        executor = ContainerExecutionProviderSpec(...)

.. note::

    **Not the long-term strategy.** This client-side resolution is a
    pragmatic bridge. The end-state (Razvan's ``compile_default`` design
    from AIRCORE-397) moves compilation to the Jobs service backend
    itself — the backend knows its own kind and constructs the executor
    server-side. When that lands, plugins will post a ``PluginJobSpec``
    (just the domain payload + metadata) and this helper becomes
    unnecessary. See ``plan-default-compilation.md`` in the AIRCORE-397
    architecture plans.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.jobs.job_list_execution_profiles_response import JobListExecutionProfilesResponseItem
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError

ExecutorKind = Literal["container", "subprocess"]
"""Executor payload shape: ``"container"`` for image-backed work, ``"subprocess"`` for host commands."""

logger = logging.getLogger(__name__)

# TODO(AIRCORE-397): Remove this module when compile_default() lands on
# the backend classes. At that point the Jobs service resolves the
# profile kind server-side and plugin compilers no longer need to query
# execution profiles.

_CACHE_TTL_SECONDS = 300  # 5 minutes
_cached_profiles: list[JobListExecutionProfilesResponseItem] | None = None
_cached_at: float = 0.0


async def _fetch_execution_profiles(sdk: AsyncNeMoPlatform) -> list[JobListExecutionProfilesResponseItem]:
    """Fetch execution profiles from the Jobs service, with caching."""
    global _cached_profiles, _cached_at
    now = time.monotonic()
    if _cached_profiles is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return _cached_profiles

    profiles = await sdk.jobs.list_execution_profiles()
    _cached_profiles = profiles
    _cached_at = now
    return profiles


async def resolve_profile_kind(
    sdk: AsyncNeMoPlatform,
    provider: str,
    profile: str,
) -> ExecutorKind:
    """Resolve the executor payload kind for a ``(provider, profile)`` pair.

    Queries the Jobs service's ``GET /v2/execution-profiles`` endpoint
    (cached for 5 minutes) and returns the profile's ``kind`` field
    (``"container"`` or ``"subprocess"``).

    Args:
        sdk: Async platform SDK client.
        provider: Compute provider (``"cpu"``, ``"gpu"``, ``"gpu_distributed"``).
        profile: Execution profile name (``"default"``, ``"subprocess"``, etc.).

    Returns:
        ``"container"`` or ``"subprocess"``.

    Raises:
        PlatformJobCompilationError: If no matching execution profile is found.
    """
    profiles = await _fetch_execution_profiles(sdk)
    for p in profiles:
        if p.provider == provider and p.profile == profile and p.kind is not None:
            return p.kind

    raise PlatformJobCompilationError(
        f"Execution profile '{provider}/{profile}' not found. "
        f"Check that the Jobs service has a profile registered for provider='{provider}', profile='{profile}'."
    )
