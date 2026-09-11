# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read the revision an agent's spec fileset is pinned to."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from nemo_agents_plugin.entities import ethos_fileset_name
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import NotFoundError as PluginClientNotFoundError
from nemo_platform_plugin.files.client import AsyncFilesClient
from nemo_platform_plugin.log_utils import sanitize_for_log

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class SpecRevision:
    """The revision an agent's spec fileset resolved to, and the ref it tracks."""

    revision: str = ""
    tracked_revision: str = ""


async def read_spec_revision(files_client: AsyncFilesClient | None, *, workspace: str, agent_name: str) -> SpecRevision:
    """Return what the agent's spec fileset is pinned to right now.

    Both fields are empty when the fileset is absent or its backend pins nothing —
    an agent that deploys from its inline config alone is the normal case, not an
    error. Nothing here may fail a deployment: this is a record of what was staged,
    and the runner reports a fileset it cannot read.
    """
    if files_client is None:
        return SpecRevision()

    fileset_name = ethos_fileset_name(agent_name)
    try:
        response = await files_client.get_fileset(workspace=workspace, name=fileset_name)
        storage = response.data().storage
    except PluginClientNotFoundError:
        return SpecRevision()
    except Exception:
        logger.warning(
            "Could not read fileset %s/%s for deployment provenance",
            sanitize_for_log(workspace),
            sanitize_for_log(fileset_name),
            exc_info=True,
        )
        return SpecRevision()

    return SpecRevision(revision=storage.pinned_revision, tracked_revision=storage.tracked_revision or "")


def files_client_for(sdk: AsyncNeMoPlatform) -> AsyncFilesClient | None:
    """Adapt the platform SDK, or report that provenance cannot be read through it.

    Failing to build the client is the same kind of event as an unreadable
    fileset: it costs the deployment its recorded revision, not its deployment.
    """
    try:
        return client_from_platform(sdk, AsyncFilesClient)
    except Exception:
        logger.warning("Could not build a files client for deployment provenance", exc_info=True)
        return None


async def stage_with_spec_revision(
    sdk: AsyncNeMoPlatform,
    *,
    workspace: str,
    agent_name: str,
    stage: Callable[[], Awaitable[T]],
) -> tuple[T, SpecRevision]:
    """Run *stage*, and report the revision the content it staged came from.

    The files API resolves a fileset's revision per request, so reading the
    revision after the download would record whatever a refresh landing in between
    left behind rather than what was staged. Restage once when the revision moves,
    which is the closest thing to an atomic read the download path allows.
    """
    files_client = files_client_for(sdk)
    if files_client is None:
        return await stage(), SpecRevision()

    before = await read_spec_revision(files_client, workspace=workspace, agent_name=agent_name)
    staged = await stage()
    after = await read_spec_revision(files_client, workspace=workspace, agent_name=agent_name)
    if after == before:
        return staged, after

    logger.info(
        "Spec fileset %s/%s moved from %r to %r while staging; staging it again",
        sanitize_for_log(workspace),
        sanitize_for_log(ethos_fileset_name(agent_name)),
        before.revision,
        after.revision,
    )
    staged = await stage()
    settled = await read_spec_revision(files_client, workspace=workspace, agent_name=agent_name)
    if settled != after:
        # `settled` is a third revision that no staging pass produced. Recording it
        # would be the failure this function exists to prevent, and a wrong revision
        # is worse than none for a client asking whether a deployment is stale.
        logger.warning(
            "Spec fileset %s/%s moved again while staging; recording no revision for it",
            sanitize_for_log(workspace),
            sanitize_for_log(ethos_fileset_name(agent_name)),
        )
        return staged, SpecRevision()
    return staged, settled
