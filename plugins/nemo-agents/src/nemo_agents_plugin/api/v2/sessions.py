# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent session CRUD and lifecycle routes.

Sessions are addressed by name in the API, matching the existing Agent and
AgentDeployment resource conventions. Each session stores the immutable entity
ID of its deployment; creation validates that relationship within the route's
workspace before persisting the session.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable
from typing import cast
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_agents_plugin.api.v2._perms import SessionPerms
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.authz import scope
from nemo_agents_plugin.deployment_routing import get_deployment_endpoint
from nemo_agents_plugin.entities import AgentDeployment, AgentSession, SessionStatus
from nemo_agents_plugin.schema import CreateSessionRequest, SessionFilter, SessionPage
from nemo_platform_plugin.api.filters import make_filter_obj_dep
from nemo_platform_plugin.authz import CallerKind, path_rule
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityConflictError, NemoEntityNotFoundError
from nemo_platform_plugin.jobs.openapi_utils import generate_openapi_extra_params
from nemo_platform_plugin.schema import PaginationData
from pydantic import ValidationError
from starlette.requests import Request

logger = logging.getLogger(__name__)

router = APIRouter()

_FABRIC_CLEANUP_TIMEOUT_SECONDS = 5.0

_raw_session_filter_dep = make_filter_obj_dep(SessionFilter)


async def _session_filter_dep(request: Request) -> SessionFilter | dict[str, object]:
    """Parse session filters and expose schema errors as HTTP 422 responses."""
    try:
        return await cast(Awaitable[SessionFilter | dict[str, object]], _raw_session_filter_dep(request))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc


@router.post("/sessions", response_model=AgentSession, status_code=201, tags=["Agent Sessions"])
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[SessionPerms.CREATE],
)
async def create_session(
    workspace: str,
    body: CreateSessionRequest,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> AgentSession:
    """Create a logical conversation for an existing deployment."""
    deployment = await _get_deployment_for_session(
        entity_client,
        workspace=workspace,
        deployment_id=body.deployment_id,
    )
    session_name = body.name or f"{deployment.name}-{secrets.token_hex(4)}"
    session = AgentSession(
        name=session_name,
        workspace=workspace,
        deployment_id=body.deployment_id,
    )

    try:
        return await entity_client.create(session)
    except NemoEntityConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Session '{session_name}' already exists in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to create session for deployment '%s'", body.deployment_id)
        raise HTTPException(status_code=500, detail="Failed to create session.") from exc


@router.get(
    "/sessions",
    response_model=SessionPage,
    tags=["Agent Sessions"],
    openapi_extra=generate_openapi_extra_params(filter_schema=SessionFilter),
)
@scope.read
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[SessionPerms.LIST],
)
async def list_sessions(
    workspace: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-created_at"),
    filter: SessionFilter | dict[str, object] = Depends(_session_filter_dep),
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> SessionPage:
    """List sessions in a workspace, optionally filtered by deployment ID."""
    filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
    try:
        result = await entity_client.list(
            AgentSession,
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filter_obj=filter_dict or None,
        )
    except Exception as exc:
        logger.exception("Failed to list sessions in workspace '%s'", workspace)
        raise HTTPException(status_code=500, detail="Failed to list sessions.") from exc

    pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
    return SessionPage(
        data=result.data,
        pagination=pagination,
        sort=sort,
        filter=filter,
    )


@router.get("/sessions/{name}", response_model=AgentSession, tags=["Agent Sessions"])
@scope.read
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[SessionPerms.READ],
)
async def get_session(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> AgentSession:
    """Get a session by name."""
    try:
        return await entity_client.get(AgentSession, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{name}' not found in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to get session '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to get session.") from exc


@router.post("/sessions/{name}/close", response_model=AgentSession, tags=["Agent Sessions"])
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[SessionPerms.CLOSE],
)
async def close_session(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> AgentSession:
    """Close a session. Closing an already-closed session is idempotent."""
    try:
        session = await entity_client.get(AgentSession, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{name}' not found in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to get session '%s' before closing", name)
        raise HTTPException(status_code=500, detail="Failed to get session.") from exc

    if session.status is SessionStatus.CLOSED:
        await _cleanup_fabric_runtime(entity_client, session)
        return session

    session.status = SessionStatus.CLOSED
    try:
        updated_session = await entity_client.update(session)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{name}' not found in workspace '{workspace}'.",
        ) from exc
    except NemoEntityConflictError as exc:
        try:
            latest_session = await entity_client.get(AgentSession, name=name, workspace=workspace)
        except NemoEntityNotFoundError as get_exc:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{name}' not found in workspace '{workspace}'.",
            ) from get_exc
        except Exception as get_exc:
            logger.exception("Failed to get session '%s' after close conflict", name)
            raise HTTPException(status_code=500, detail="Failed to get session.") from get_exc

        if latest_session.status is SessionStatus.CLOSED:
            await _cleanup_fabric_runtime(entity_client, latest_session)
            return latest_session

        raise HTTPException(
            status_code=409,
            detail=f"Session '{name}' is being modified concurrently.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to close session '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to close session.") from exc

    await _cleanup_fabric_runtime(entity_client, updated_session)
    return updated_session


@router.delete("/sessions/{name}", status_code=204, tags=["Agent Sessions"])
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[SessionPerms.DELETE],
)
async def delete_session(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> None:
    """Permanently delete a session by name."""
    try:
        session = await entity_client.get(AgentSession, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{name}' not found in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to get session '%s' before deleting", name)
        raise HTTPException(status_code=500, detail="Failed to get session.") from exc

    try:
        await entity_client.delete(
            AgentSession,
            name=name,
            workspace=workspace,
            expected_db_version=session.db_version,
        )
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{name}' not found in workspace '{workspace}'.",
        ) from exc
    except NemoEntityConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Session '{name}' is being modified concurrently.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to delete session '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to delete session.") from exc

    await _cleanup_fabric_runtime(entity_client, session)


async def _get_deployment_for_session(
    entity_client: NemoEntitiesClient,
    *,
    workspace: str,
    deployment_id: str,
) -> AgentDeployment:
    """Resolve a deployment entity ID within the requested workspace."""
    try:
        deployment = await entity_client.find_one(
            AgentDeployment,
            workspace=workspace,
            filter_obj={"id": deployment_id},
        )
    except NemoEntityNotFoundError as exc:
        raise _deployment_not_found(workspace, deployment_id) from exc
    except Exception as exc:
        logger.exception("Failed to look up deployment ID '%s'", deployment_id)
        raise HTTPException(status_code=500, detail="Failed to look up deployment.") from exc

    if deployment.id != deployment_id or deployment.workspace != workspace:
        raise _deployment_not_found(workspace, deployment_id)
    return deployment


def _deployment_not_found(workspace: str, deployment_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"Deployment ID '{deployment_id}' not found in workspace '{workspace}'.",
    )


async def _cleanup_fabric_runtime(
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
