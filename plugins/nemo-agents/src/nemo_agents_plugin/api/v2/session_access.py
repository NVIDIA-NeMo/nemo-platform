# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Ownership-aware access helpers for persisted agent sessions."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from nemo_agents_plugin.entities import AgentSession
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityNotFoundError

logger = logging.getLogger(__name__)


async def get_owned_session(
    entity_client: NemoEntitiesClient,
    *,
    workspace: str,
    name: str,
    effective_principal_id: str,
) -> AgentSession:
    """Resolve a session owned by the request's effective principal.

    Missing sessions and sessions owned by another principal intentionally have
    the same response so callers cannot use this endpoint to discover another
    principal's sessions.
    """
    try:
        session = await entity_client.get(AgentSession, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise session_not_found(workspace, name) from exc
    except Exception as exc:
        logger.exception("Failed to get session '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to get session.") from exc

    if session.workspace != workspace or session.created_by != effective_principal_id:
        raise session_not_found(workspace, name)

    return session


def session_not_found(workspace: str, name: str) -> HTTPException:
    """Return the non-disclosing response for unavailable sessions."""
    return HTTPException(
        status_code=404,
        detail=f"Session '{name}' not found in workspace '{workspace}'.",
    )
