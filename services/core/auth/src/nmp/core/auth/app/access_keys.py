# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistence and issuance services for Scoped Access Keys."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Depends
from nemo_platform_plugin.auth.access_keys.issuer import AccessKeyFeatureDisabledError
from nemo_platform_plugin.auth.access_keys.types import (
    AccessKeyCreateRequest,
    AccessKeyCreateResponse,
    AccessKeyListResponse,
    AccessKeyMetadataResponse,
    AccessKeyReversibleStatus,
    AccessKeyStatus,
)
from nmp.common.auth.access_keys import LEGACY_ACCESS_KEY_METADATA_VERSION, AccessKeyIssuerService
from nmp.common.auth.jwt import TokenClaims
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig
from nmp.common.entities import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.common.service.dependencies import get_entity_client
from nmp.core.auth.entities import AccessKeyEntity

ACCESS_KEY_WORKSPACE = "system"
logger = logging.getLogger(__name__)


class AccessKeyNotFoundError(Exception):
    """Raised when a key does not exist or is not owned by the caller."""


class AccessKeyStateConflictError(Exception):
    """Raised when an irreversible lifecycle state prevents a transition."""


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

    async def revoke(self, jti: str, principal: str) -> bool:
        # Note: unlike is_active, revoke has no backfill path for legacy v1 keys that have
        # never authenticated after migration. Without the original JWT claims we cannot
        # construct a valid entity, so callers receive 404 until the key authenticates once.
        record = await self._get_owned(jti, principal)
        if record.status == "REVOKED":
            return False
        updated = record.model_copy(update={"status": "REVOKED"})
        try:
            await self._entity_client.update(updated)
        except EntityConflictError:
            # EntityClient.update uses db_version optimistic locking. Re-read to
            # determine whether a concurrent revoke won the race.
            try:
                current = await self._get_owned(jti, principal)
            except AccessKeyNotFoundError:
                # The key was concurrently hard-deleted between our update and this
                # read. Treat as already-revoked (idempotent outcome).
                return False
            if current.status == "REVOKED":
                return False
            raise
        return True

    async def suspend(self, jti: str, principal: str) -> tuple[bool, AccessKeyReversibleStatus]:
        return await self._set_suspension(jti, principal, suspended=True)

    async def unsuspend(self, jti: str, principal: str) -> tuple[bool, AccessKeyReversibleStatus]:
        return await self._set_suspension(jti, principal, suspended=False)

    async def _set_suspension(
        self, jti: str, principal: str, *, suspended: bool
    ) -> tuple[bool, AccessKeyReversibleStatus]:
        target_status: Literal["ACTIVE", "SUSPENDED"] = "SUSPENDED" if suspended else "ACTIVE"
        completed_action = "suspended" if suspended else "unsuspended"
        record = await self._get_owned(jti, principal)
        if record.status == "REVOKED":
            raise AccessKeyStateConflictError(f"Revoked Scoped Access Key {jti} cannot be {completed_action}")
        if record.status == target_status:
            return False, self._reversible_status(record)
        updated = record.model_copy(update={"status": target_status})
        try:
            await self._entity_client.update(updated)
        except EntityConflictError:
            # EntityClient.update uses db_version optimistic locking. Re-read to
            # determine whether a concurrent update won the race.
            current = await self._get_owned(jti, principal)
            if current.status == "REVOKED":
                raise AccessKeyStateConflictError(f"Revoked Scoped Access Key {jti} cannot be {completed_action}")
            if current.status == target_status:
                return False, self._reversible_status(current)
            raise
        return True, self._reversible_status(updated)

    async def is_active(self, jti: str, principal: str, *, claims: TokenClaims | None = None) -> bool:
        try:
            record = await self._get_owned(jti, principal)
        except AccessKeyNotFoundError:
            if claims is None:
                return False
            record = await self._backfill_legacy_record(jti, principal, claims)
            if record is None:
                return False
        return self._status(record, leeway_seconds=30) == "ACTIVE"

    async def _get_owned(self, jti: str, principal: str) -> AccessKeyEntity:
        try:
            record = await self._entity_client.get(
                AccessKeyEntity,
                name=jti,
                workspace=ACCESS_KEY_WORKSPACE,
            )
        except EntityNotFoundError as exc:
            raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found") from exc
        if record.principal != principal:
            raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found")
        return record

    @staticmethod
    def _metadata(record: AccessKeyEntity) -> AccessKeyMetadataResponse:
        return AccessKeyMetadataResponse(
            jti=record.name,
            name=record.key_name,
            description=record.description,
            principal=record.principal,
            # Report lifecycle status against the published expiration instant.
            # Clock-skew leeway applies only while authenticating the JWT.
            status=AccessKeyRegistry._status(record),
            issuer=record.issuer,
            audiences=list(dict.fromkeys(record.audiences)),
            created_at=record.issued_at,
            expires_at=record.expires_at,
        )

    @staticmethod
    def _status(record: AccessKeyEntity, *, leeway_seconds: int = 0) -> AccessKeyStatus:
        if record.status == "REVOKED":
            return "REVOKED"
        if record.status == "SUSPENDED":
            return "SUSPENDED"
        if record.expires_at is not None and datetime.now(tz=UTC) >= record.expires_at + timedelta(
            seconds=leeway_seconds
        ):
            return "EXPIRED"
        return "ACTIVE"

    @staticmethod
    def _reversible_status(record: AccessKeyEntity) -> AccessKeyReversibleStatus:
        effective_status = AccessKeyRegistry._status(record)
        if effective_status == "REVOKED":
            raise AssertionError("A reversible access-key transition cannot produce REVOKED status")
        return effective_status

    async def _backfill_legacy_record(
        self,
        jti: str,
        principal: str,
        claims: TokenClaims,
    ) -> AccessKeyEntity | None:
        record = self._record_from_validated_claims(jti, principal, claims)
        if record is None:
            return None
        try:
            await self._entity_client.create(record)
        except EntityConflictError:
            try:
                return await self._get_owned(jti, principal)
            except AccessKeyNotFoundError:
                return None
        logger.info(
            "Backfilled legacy Scoped Access Key lifecycle record",
            extra={
                "audit_event": "access_key.backfilled",
                "actor_principal": principal,
                "access_key_jti": jti,
            },
        )
        # Return the locally-constructed record rather than re-fetching. The
        # immediate caller (is_active) only reads status and expires_at,
        # both of which are set locally. If this method is extended to use
        # server-assigned fields (e.g. db_version), re-fetch here instead.
        return record

    @classmethod
    def _record_from_validated_claims(
        cls,
        jti: str,
        principal: str,
        claims: TokenClaims,
    ) -> AccessKeyEntity | None:
        raw_claims = claims.raw_claims
        # Keep the registry boundary defensive even though the authenticate
        # endpoint currently derives ``jti`` and ``principal`` from these claims.
        if raw_claims.get("jti") != jti or claims.subject != principal:
            return None
        issuer = raw_claims.get("iss")
        issued_at = cls._datetime_from_claim(raw_claims.get("iat"))
        if not isinstance(issuer, str) or issued_at is None:
            return None
        audiences = cls._audiences_from_claim(raw_claims.get("aud"))
        if not audiences:
            return None

        metadata = raw_claims.get("nmp_access_key")
        if not isinstance(metadata, dict):
            return None
        if metadata.get("version") != LEGACY_ACCESS_KEY_METADATA_VERSION:
            logger.warning(
                "Access key %s (version=%s) has no registry record and cannot be backfilled; "
                "this key will be rejected until its record is restored",
                jti,
                metadata.get("version"),
            )
            return None
        key_name = metadata.get("name")
        return AccessKeyEntity(
            name=jti,
            workspace=ACCESS_KEY_WORKSPACE,
            key_name=key_name if isinstance(key_name, str) else None,
            # description is not embedded in JWT claims for any version; always None on backfill
            description=None,
            principal=principal,
            issuer=issuer,
            audiences=audiences,
            issued_at=issued_at,
            expires_at=cls._datetime_from_claim(raw_claims.get("exp")),
        )

    @staticmethod
    def _audiences_from_claim(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return list(dict.fromkeys(audience for audience in value if isinstance(audience, str)))
        return []

    @staticmethod
    def _datetime_from_claim(value: object) -> datetime | None:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        return None


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
        try:
            await self._registry.add(key)
        except Exception:
            logger.warning(
                "Failed to persist Scoped Access Key lifecycle record; the signed JWT will not be returned to the caller",
                extra={"access_key_jti": key.jti, "actor_principal": self.principal},
                exc_info=True,
            )
            raise
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

    async def revoke_async(self, jti: str) -> bool:
        self._ensure_enabled()
        revoked = await self._registry.revoke(jti, self.principal)
        audit_event = "access_key.revoked" if revoked else "access_key.revoke_noop"
        logger.info(
            "Scoped Access Key revoked" if revoked else "Scoped Access Key revoke requested for already-revoked key",
            extra={
                "audit_event": audit_event,
                "actor_principal": self.principal,
                "access_key_jti": jti,
                "access_key_already_revoked": not revoked,
            },
        )
        return revoked

    async def suspend_async(self, jti: str) -> tuple[bool, AccessKeyReversibleStatus]:
        self._ensure_enabled()
        suspended, effective_status = await self._registry.suspend(jti, self.principal)
        self._log_suspension(jti, changed=suspended, action="suspend")
        return suspended, effective_status

    async def unsuspend_async(self, jti: str) -> tuple[bool, AccessKeyReversibleStatus]:
        self._ensure_enabled()
        unsuspended, effective_status = await self._registry.unsuspend(jti, self.principal)
        self._log_suspension(jti, changed=unsuspended, action="unsuspend")
        return unsuspended, effective_status

    def _log_suspension(
        self,
        jti: str,
        *,
        changed: bool,
        action: Literal["suspend", "unsuspend"],
    ) -> None:
        completed_action = "suspended" if action == "suspend" else "unsuspended"
        logger.info(
            f"Scoped Access Key {completed_action}"
            if changed
            else f"Scoped Access Key {action} requested with no change",
            extra={
                "audit_event": f"access_key.{action}ed" if changed else f"access_key.{action}_noop",
                "actor_principal": self.principal,
                "access_key_jti": jti,
                "access_key_state_changed": changed,
            },
        )

    def _ensure_enabled(self) -> None:
        if not self._config.access_keys.enabled:
            raise AccessKeyFeatureDisabledError("Scoped Access Keys are not enabled")
