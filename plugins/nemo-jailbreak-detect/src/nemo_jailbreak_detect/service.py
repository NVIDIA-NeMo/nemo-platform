# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP service for the jailbreak-detection plugin.

Registered under ``nemo.services``; routes mount at ``/apis/jailbreak-detect``.

- Deployment CRUD writes the *desired* state; the controller does the work.
- ``POST .../classify`` proxies a prompt to a running deployment using the same
  NIM-compatible contract the model server exposes — handy for testing the
  deployment without going through guardrails.
"""

from __future__ import annotations

import logging
from typing import ClassVar

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from nemo_jailbreak_detect.config import JailbreakDetectConfig
from nemo_jailbreak_detect.entities import JailbreakDetectorDeployment
from nemo_jailbreak_detect.schema import (
    ClassifyRequest,
    ClassifyResponse,
    CreateDeploymentRequest,
    DeploymentFilter,
    DeploymentPage,
)
from nemo_platform_plugin.entity_client import (
    NemoEntitiesClient,
    NemoEntityConflictError,
    NemoEntityNotFoundError,
    get_entity_client,
)
from nemo_platform_plugin.schema import PaginationData
from nemo_platform_plugin.service import NemoService, RouterSpec
from nmp.common.entities.filters import make_filter_obj_dep

logger = logging.getLogger(__name__)

_PREFIX = "/v2/workspaces/{workspace}"


class JailbreakDetectService(NemoService):
    """Deployment CRUD + classify proxy for self-hosted jailbreak detection."""

    name: ClassVar[str] = "jailbreak-detect"
    dependencies: ClassVar[list[str]] = ["entities"]

    def get_routers(self) -> list[RouterSpec]:
        return [
            RouterSpec(
                _build_router(),
                tag="Jailbreak Detection",
                description="Manage self-hosted jailbreak-detection model deployments.",
                prefix=_PREFIX,
            ),
        ]


def _build_router() -> APIRouter:
    router = APIRouter()
    _filter_dep = make_filter_obj_dep(DeploymentFilter)

    @router.post("/deployments", response_model=JailbreakDetectorDeployment, status_code=201)
    async def create_deployment(
        workspace: str,
        body: CreateDeploymentRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> JailbreakDetectorDeployment:
        config = JailbreakDetectConfig.get()
        deployment = JailbreakDetectorDeployment(
            name=body.name,
            workspace=workspace,
            backend=body.backend or config.default_backend,
            image=body.image or config.server_image,
            device=body.device or config.default_device,
            port=body.port or config.default_port,
            status="pending",
        )
        try:
            return await entity_client.create(deployment)
        except NemoEntityConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Deployment '{body.name}' already exists in workspace '{workspace}'.",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to create deployment '%s'", body.name)
            raise HTTPException(status_code=500, detail="Failed to create deployment.") from exc

    @router.get("/deployments", response_model=DeploymentPage)
    async def list_deployments(
        workspace: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        sort: str = Query(default="-created_at"),
        filter: DeploymentFilter = Depends(_filter_dep),
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> DeploymentPage:
        filter_dict = filter if isinstance(filter, dict) else filter.model_dump(exclude_none=True)
        try:
            result = await entity_client.list(
                JailbreakDetectorDeployment,
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
        return DeploymentPage(data=result.data, pagination=pagination, sort=sort, filter=filter)

    @router.get("/deployments/{name}", response_model=JailbreakDetectorDeployment)
    async def get_deployment(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> JailbreakDetectorDeployment:
        try:
            return await entity_client.get(JailbreakDetectorDeployment, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Deployment '{name}' not found.") from exc

    @router.delete("/deployments/{name}", response_model=JailbreakDetectorDeployment)
    async def delete_deployment(
        workspace: str,
        name: str,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> JailbreakDetectorDeployment:
        """Mark a deployment for teardown. The controller stops the backend and
        removes the entity once stopped."""
        try:
            deployment = await entity_client.get(JailbreakDetectorDeployment, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Deployment '{name}' not found.") from exc

        deployment.status = "stopping"
        try:
            return await entity_client.update(deployment)
        except NemoEntityConflictError as exc:
            raise HTTPException(status_code=409, detail="Deployment changed concurrently; retry.") from exc

    @router.post("/deployments/{name}/classify", response_model=ClassifyResponse)
    async def classify(
        workspace: str,
        name: str,
        body: ClassifyRequest,
        entity_client: NemoEntitiesClient = Depends(get_entity_client),
    ) -> ClassifyResponse:
        """Proxy a classify call to a running deployment (NIM-compatible contract)."""
        try:
            deployment = await entity_client.get(JailbreakDetectorDeployment, name=name, workspace=workspace)
        except NemoEntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Deployment '{name}' not found.") from exc

        if deployment.status != "running" or not deployment.endpoint_url:
            raise HTTPException(
                status_code=409, detail=f"Deployment '{name}' is not running (status={deployment.status})."
            )

        config = JailbreakDetectConfig.get()
        url = deployment.endpoint_url.rstrip("/") + "/v1/classify"
        try:
            async with httpx.AsyncClient(timeout=config.request_timeout_seconds) as client:
                resp = await client.post(url, json={"input": body.input})
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("classify proxy to %s failed: %s", url, exc)
            raise HTTPException(status_code=502, detail="Upstream model server error.") from exc

        return ClassifyResponse(jailbreak=bool(data["jailbreak"]), score=float(data.get("score", 0.0)))

    return router
