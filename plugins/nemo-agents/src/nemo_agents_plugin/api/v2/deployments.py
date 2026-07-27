# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deployment lifecycle routes — create/list/get/delete AgentDeployment entities.

Creating a deployment:
1. Validates the referenced Agent exists.
2. Deep-copies the agent config and injects the inference-gateway URL.
3. Creates an ``AgentDeployment`` entity with ``status: "pending"``.
4. Returns immediately — the :class:`~nemo_agents_plugin.runner.controller.AgentDeploymentController`
   picks up the pending deployment on the next reconcile cycle.

Deleting a deployment marks it ``deleting``; the controller terminates the
process and removes the entity.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.api.v2._perms import DeploymentPerms
from nemo_agents_plugin.api.v2.dependencies import get_entity_client
from nemo_agents_plugin.authz import scope
from nemo_agents_plugin.entities import (
    NAT_WORKFLOW_CONFIG_FORMAT,
    NEMO_AGENTS_SPEC_CONFIG_FORMAT,
    Agent,
    AgentDeployment,
    is_container_deployment_mode,
)
from nemo_agents_plugin.schema import (
    CreateDeploymentRequest,
    DeploymentFilter,
    DeploymentPage,
)
from nemo_agents_plugin.utils import inject_default_model, inject_gateway_url, inject_nemo_trace_fields
from nemo_platform_plugin.api.filters import make_filter_obj_dep
from nemo_platform_plugin.authz import CallerKind, path_rule
from nemo_platform_plugin.entity_client import NemoEntitiesClient, NemoEntityConflictError, NemoEntityNotFoundError
from nemo_platform_plugin.schema import PaginationData
from pydantic import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter()

_deployment_filter_dep = make_filter_obj_dep(DeploymentFilter)
_DELETE_MARK_ATTEMPTS = 3


@router.post("/deployments", response_model=AgentDeployment, status_code=201, tags=["Agent Deployments"])
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[DeploymentPerms.CREATE],
)
async def create_deployment(
    workspace: str,
    body: CreateDeploymentRequest,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> AgentDeployment:
    """Create a new deployment for an existing agent.

    The deployment starts in ``pending`` state and is picked up by the
    deployment controller on its next reconcile cycle.
    """
    # 1. Validate the referenced agent exists
    try:
        agent = await entity_client.get(Agent, name=body.agent, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{body.agent}' not found in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to look up agent '%s'", body.agent)
        raise HTTPException(status_code=500, detail="Failed to look up agent.") from exc

    # 2. Build deployment name (auto-generate if not provided)
    deployment_name = body.name or f"{body.agent}-{secrets.token_hex(4)}"

    # 3. Resolve deployment-time config. NAT workflows need legacy injection;
    # Platform-owned agent specs stay strict and are translated by the runner.
    resolved_config = _resolve_deployment_config(agent, workspace=workspace)

    # 4. Create the entity with status "pending"
    deployment = AgentDeployment(
        name=deployment_name,
        workspace=workspace,
        agent=body.agent,
        config=resolved_config,
        status="pending",
        deployment_mode=body.deployment_mode,
        image=body.image,
        plugin_deployment=deployment_name if is_container_deployment_mode(body.deployment_mode) else "",
    )
    try:
        saved = await entity_client.create(deployment)
    except NemoEntityConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Deployment '{deployment_name}' already exists in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to create deployment for agent '%s'", body.agent)
        raise HTTPException(status_code=500, detail="Failed to create deployment.") from exc

    return saved


def _resolve_deployment_config(agent: Agent, *, workspace: str) -> dict[str, Any]:
    if agent.config_format == NAT_WORKFLOW_CONFIG_FORMAT:
        resolved_config = inject_gateway_url(agent.config, workspace)
        resolved_config = inject_default_model(resolved_config)
        inject_nemo_trace_fields(resolved_config, workspace=workspace, agent_name=agent.name)
        return resolved_config

    if agent.config_format == NEMO_AGENTS_SPEC_CONFIG_FORMAT:
        try:
            return AgentConfig.model_validate(agent.config).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid agent config: {exc}") from exc

    raise HTTPException(status_code=400, detail=f"Unsupported config_format {agent.config_format!r}.")


@router.get("/deployments", response_model=DeploymentPage, tags=["Agent Deployments"])
@scope.read
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[DeploymentPerms.LIST],
)
async def list_deployments(
    workspace: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-created_at"),
    filter: DeploymentFilter = Depends(_deployment_filter_dep),
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> DeploymentPage:
    """List all deployments in the workspace with pagination and filter support."""
    filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
    try:
        result = await entity_client.list(
            AgentDeployment,
            workspace=workspace,
            page=page,
            page_size=page_size,
            sort=sort,
            filter_obj=filter_dict or None,
        )
    except Exception as exc:
        logger.exception("Failed to list deployments in workspace '%s'", workspace)
        raise HTTPException(status_code=500, detail="Failed to list deployments.") from exc

    pagination = PaginationData.model_validate(result.pagination.model_dump()) if result.pagination else None
    return DeploymentPage(
        data=result.data,
        pagination=pagination,
        sort=sort,
        filter=filter,
    )


@router.get("/deployments/{name}", response_model=AgentDeployment, tags=["Agent Deployments"])
@scope.read
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[DeploymentPerms.READ],
)
async def get_deployment(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> AgentDeployment:
    """Get a deployment by name."""
    try:
        dep = await entity_client.get(AgentDeployment, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment '{name}' not found in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to get deployment '%s'", name)
        raise HTTPException(status_code=500, detail="Failed to get deployment.") from exc
    return dep


@router.delete("/deployments/{name}", status_code=204, tags=["Agent Deployments"])
@scope.write
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions=[DeploymentPerms.DELETE],
)
async def delete_deployment(
    workspace: str,
    name: str,
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> None:
    """Stop and remove a deployment.

    Marks the deployment as ``deleting``.  The controller terminates the
    subprocess and removes the entity on the next reconcile cycle.
    """
    for attempt in range(_DELETE_MARK_ATTEMPTS):
        try:
            await _mark_deployment_deleting_once(
                entity_client,
                workspace=workspace,
                name=name,
                retrying=attempt > 0,
            )
            return
        except HTTPException:
            raise
        except NemoEntityConflictError as exc:
            if attempt + 1 >= _DELETE_MARK_ATTEMPTS:
                raise HTTPException(
                    status_code=409,
                    detail=f"Deployment '{name}' is being modified concurrently.",
                ) from exc
            logger.info("Retrying delete for deployment '%s' after concurrent update", name)
        except Exception as exc:
            logger.exception("Failed to mark deployment '%s' as deleting", name)
            raise HTTPException(status_code=500, detail="Failed to update deployment.") from exc


async def _mark_deployment_deleting_once(
    entity_client: NemoEntitiesClient,
    *,
    workspace: str,
    name: str,
    retrying: bool,
) -> None:
    try:
        dep = await entity_client.get(AgentDeployment, name=name, workspace=workspace)
    except NemoEntityNotFoundError as exc:
        if retrying:
            logger.info("Deployment '%s' already deleted during delete retry", name)
            return
        raise HTTPException(
            status_code=404,
            detail=f"Deployment '{name}' not found in workspace '{workspace}'.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to look up deployment '%s' before delete", name)
        raise HTTPException(status_code=500, detail="Failed to look up deployment.") from exc

    if dep.status == "deleting":
        return

    dep.status = "deleting"
    try:
        await entity_client.update(dep)
    except NemoEntityNotFoundError:
        logger.info("Deployment '%s' already deleted before status update", name)
        return
