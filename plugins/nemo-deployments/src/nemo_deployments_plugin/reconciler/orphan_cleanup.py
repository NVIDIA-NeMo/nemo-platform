# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Delete backend deployments that have no corresponding entity."""

from __future__ import annotations

import logging

from nemo_deployments_plugin.backends.base import DeploymentBackend

logger = logging.getLogger(__name__)


async def reconcile_orphans(
    backends: list[DeploymentBackend],
    known_deployment_ids: set[str],
) -> None:
    """Delete backend deployments not present in the entity store."""
    for backend in backends:
        try:
            backend_names = await backend.list_managed_deployment_names()
        except Exception:
            logger.warning("Failed to list managed deployments for orphan cleanup", exc_info=True)
            continue

        orphans = set(backend_names) - known_deployment_ids
        for deployment_id in orphans:
            parts = deployment_id.split("/", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                logger.warning("Invalid deployment id from backend: %r, skipping", deployment_id)
                continue
            workspace, name = parts
            try:
                logger.info("Deleting orphan deployment %s", deployment_id)
                await backend.delete_deployment(workspace, name)
            except Exception:
                logger.warning("Failed to delete orphan %s", deployment_id, exc_info=True)
