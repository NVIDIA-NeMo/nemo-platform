# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared persisted-session lifecycle helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
from nemo_agents_plugin.deployment_routing import get_deployment_endpoint
from nemo_agents_plugin.entities import AgentDeployment, AgentSession
from nemo_platform_plugin.entity_client import NemoEntitiesClient

logger = logging.getLogger(__name__)

_FABRIC_CLEANUP_TIMEOUT_SECONDS = 5.0


def session_expiration_is_due(session: AgentSession, *, at: datetime) -> bool:
    """Return whether an active session has reached its persisted idle deadline."""
    expires_at = session.expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= at.astimezone(UTC)


async def cleanup_fabric_runtime(
    entity_client: NemoEntitiesClient,
    session: AgentSession,
) -> None:
    """Best-effort removal of a session's process-local Fabric runtime."""
    try:
        deployment = await entity_client.find_one(
            AgentDeployment,
            workspace=session.workspace,
            filter_obj={"id": session.deployment_id},
        )
    except Exception:
        logger.warning(
            "Could not resolve deployment ID '%s' while cleaning up session ID '%s'.",
            session.deployment_id,
            session.id,
            exc_info=True,
        )
        return

    if deployment.id != session.deployment_id or deployment.workspace != session.workspace:
        logger.warning(
            "Resolved deployment did not match session ID '%s'; skipping Fabric runtime cleanup.",
            session.id,
        )
        return

    endpoint = get_deployment_endpoint(deployment)
    if endpoint is None:
        logger.warning(
            "Deployment ID '%s' has no endpoint; skipping cleanup for session ID '%s'.",
            deployment.id,
            session.id,
        )
        return

    cleanup_url = f"{endpoint.rstrip('/')}/v1/sessions/{quote(session.id, safe='')}"
    try:
        async with httpx.AsyncClient(
            timeout=_FABRIC_CLEANUP_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.delete(cleanup_url)
    except Exception:
        logger.warning(
            "Fabric runtime cleanup request failed for session ID '%s'.",
            session.id,
            exc_info=True,
        )
        return

    # A missing runtime is already clean: the session may never have been invoked or may
    # have expired from the deployment's process-local registry.
    if response.status_code == 404 or 200 <= response.status_code < 300:
        return
    logger.warning(
        "Fabric runtime cleanup returned HTTP %s for session ID '%s'.",
        response.status_code,
        session.id,
    )
