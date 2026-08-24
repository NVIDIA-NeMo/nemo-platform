# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read, write, and delete a fileset's stored profile.

The profile lives in its own ``fileset_profile`` entity parented to the fileset (see
:class:`~nmp.core.files.entities.FilesetProfile`). These helpers are the only places that know
that, so the endpoints stay about HTTP and the storage shape can move without touching them.
"""

import logging

from nemo_platform_plugin.files.dataset_profile import AnyFilesetProfile
from nmp.common.entities.client import EntityClient, EntityNotFoundError
from nmp.core.files.entities import FILESET_PROFILE_ENTITY_NAME, Fileset, FilesetProfile

logger = logging.getLogger(__name__)


async def _get_entity(entity_store: EntityClient, fileset: Fileset) -> FilesetProfile | None:
    try:
        return await entity_store.get(
            FilesetProfile,
            FILESET_PROFILE_ENTITY_NAME,
            workspace=fileset.workspace,
            parent=fileset.id,
        )
    except EntityNotFoundError:
        return None


async def get_profile(entity_store: EntityClient, fileset: Fileset) -> AnyFilesetProfile | None:
    """The stored profile for ``fileset``, or None if it has never been profiled."""
    stored = await _get_entity(entity_store, fileset)
    return stored.profile if stored is not None else None


async def put_profile(entity_store: EntityClient, fileset: Fileset, profile: AnyFilesetProfile) -> None:
    """Store ``profile`` for ``fileset``, replacing any previous one.

    Create-or-replace rather than create-only: profiling is re-runnable by design, so the second
    run of a changed dataset must land rather than conflict.
    """
    existing = await _get_entity(entity_store, fileset)
    if existing is None:
        await entity_store.create(
            FilesetProfile(
                name=FILESET_PROFILE_ENTITY_NAME,
                workspace=fileset.workspace,
                fileset=fileset.id,
                profile=profile,
            )
        )
    else:
        await entity_store.update(existing.model_copy(update={"profile": profile}))
    logger.info("Stored %s profile for fileset %s/%s", profile.kind, fileset.workspace, fileset.name)


async def delete_profile(entity_store: EntityClient, fileset: Fileset) -> None:
    """Drop the stored profile for ``fileset``, if any.

    Called when the fileset is deleted: the entity store does not cascade, so a child left behind
    would be unreachable rows that never get cleaned up.
    """
    stored = await _get_entity(entity_store, fileset)
    if stored is None:
        return
    await entity_store.delete_by_id(FilesetProfile, stored.id)
    logger.info("Deleted profile for fileset %s/%s", fileset.workspace, fileset.name)
