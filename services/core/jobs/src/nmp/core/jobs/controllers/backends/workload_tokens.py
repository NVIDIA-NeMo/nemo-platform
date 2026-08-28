# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for controller-managed workload identity subject tokens."""

from __future__ import annotations

import datetime
import io
import tarfile

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.entities.client import EntitiesClient
from nmp.common.auth import SyncWorkloadDelegationStore
from nmp.common.entities import SyncEntityClient

WORKLOAD_DELEGATION_TTL_BUFFER_SECONDS = 300


def create_authenticated_workload_delegation_store(nmp_sdk: NeMoPlatform) -> SyncWorkloadDelegationStore:
    """Create a jobs service-scoped workload delegation store from a platform SDK."""
    entity_client = SyncEntityClient(client_from_platform(nmp_sdk, EntitiesClient)).as_service("jobs", internal=True)
    return SyncWorkloadDelegationStore(entity_client)


def workload_delegation_expires_at(
    *,
    ttl_seconds_active: int,
    now: datetime.datetime | None = None,
) -> datetime.datetime:
    effective_now = now or datetime.datetime.now(datetime.timezone.utc)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=datetime.timezone.utc)
    return effective_now + datetime.timedelta(seconds=ttl_seconds_active + WORKLOAD_DELEGATION_TTL_BUFFER_SECONDS)


def build_token_archive(token: str, *, name: str = "token.tmp") -> io.BytesIO:
    """Build a tar archive containing one token file."""
    data = token.encode("utf-8")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo(name=name)
        info.size = len(data)
        info.mode = 0o400
        tar.addfile(info, io.BytesIO(data))
    archive.seek(0)
    return archive
