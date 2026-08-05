# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistence and issuance services for Scoped Access Keys."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Depends
from nemo_platform_plugin.auth.access_keys.issuer import AccessKeyFeatureDisabledError
from nemo_platform_plugin.auth.access_keys.types import (
    AccessKeyCreateRequest,
    AccessKeyCreateResponse,
    AccessKeyListResponse,
    AccessKeyMetadataResponse,
    AccessKeyStatus,
)
from nmp.common.auth.access_keys import AccessKeyIssuerService
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig
from nmp.common.entities import EntityClient
from nmp.common.service.dependencies import get_entity_client
from nmp.core.auth.entities import AccessKeyEntity

ACCESS_KEY_WORKSPACE = "system"
logger = logging.getLogger(__name__)


class AccessKeyRegistry:
    """Durable access-key lifecycle records stored by the entities service."""

    def __init__(self, entity_client: EntityClient) -> None:
        self._entity_client = entity_client

    async def add(self, key: AccessKeyCreateResponse) -> None:
        await self._entity_client.create(
            AccessKeyEntity(
                name=key.jti,
                workspace=ACCESS_KEY_WORKSPACE,
                key_name=key.name,
                description=key.description,
                principal=key.principal,
                issuer=key.issuer,
                audiences=key.audiences,
                issued_at=key.created_at,
                expires_at=key.expires_at,
            )
        )

    async def list_for_principal(self, principal: str, *, page: int, page_size: int) -> AccessKeyListResponse:
        result = await self._entity_client.list(
            AccessKeyEntity,
            workspace=ACCESS_KEY_WORKSPACE,
            filter_obj={"principal": principal},
            sort="-issued_at",
            page=page,
            page_size=page_size,
        )
        return AccessKeyListResponse(
            data=[self._metadata(record) for record in result.data],
            has_more=page < result.pagination.total_pages,
        )

    @staticmethod
    def _metadata(record: AccessKeyEntity) -> AccessKeyMetadataResponse:
        return AccessKeyMetadataResponse(
            jti=record.name,
            name=record.key_name,
            description=record.description,
            principal=record.principal,
            status=AccessKeyRegistry._status(record),
            issuer=record.issuer,
            audiences=record.audiences,
            created_at=record.issued_at,
            expires_at=record.expires_at,
        )

    @staticmethod
    def _status(record: AccessKeyEntity) -> AccessKeyStatus:
        if record.revoked_at is not None:
            return "REVOKED"
        if record.expires_at is not None and record.expires_at <= datetime.now(tz=UTC):
            return "EXPIRED"
        return "ACTIVE"

def get_access_key_registry(entity_client: EntityClient = Depends(get_entity_client)) -> AccessKeyRegistry:
    return AccessKeyRegistry(entity_client.as_service("auth", internal=True))


class PersistentAccessKeyIssuer:
    """Signs access keys and records their lifecycle before returning them."""

    def __init__(self, config: AuthConfig, principal: Principal, registry: AccessKeyRegistry) -> None:
        self._issuer = AccessKeyIssuerService(config=config, principal=principal)
        self._config = config
        self._registry = registry
        self.principal = principal.id

    async def create_async(self, request: AccessKeyCreateRequest) -> AccessKeyCreateResponse:
        self._ensure_enabled()
        key = await self._issuer.create_async(request)
        await self._registry.add(key)
        logger.info(
            "Scoped Access Key created",
            extra={
                "audit_event": "access_key.created",
                "actor_principal": self.principal,
                "access_key_jti": key.jti,
            },
        )
        return key

    async def list_async(self, *, page: int = 1, page_size: int = 100) -> AccessKeyListResponse:
        self._ensure_enabled()
        return await self._registry.list_for_principal(self.principal, page=page, page_size=page_size)

    def revoke(self, jti: str) -> None:
        """Preserve the pre-lifecycle not-implemented response until revocation is added."""
        self._issuer.revoke(jti)

    def _ensure_enabled(self) -> None:
        if not self._config.access_keys.enabled:
            raise AccessKeyFeatureDisabledError("Scoped Access Keys are not enabled")
