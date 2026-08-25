# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persistence and issuance services for Scoped Access Keys."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Depends, HTTPException
from nemo_platform_plugin.auth.access_keys.issuer import AccessKeyFeatureDisabledError
from nemo_platform_plugin.auth.access_keys.types import (
    AccessKeyCreateRequest,
    AccessKeyCreateResponse,
    AccessKeyListResponse,
    AccessKeyMetadataResponse,
    AccessKeyReversibleStatus,
    AccessKeyStatus,
)
from nmp.common.api.filter import ComparisonOperation, FilterOperator, LogicalOperation
from nmp.common.auth.access_keys import (
    LEGACY_ACCESS_KEY_METADATA_VERSION,
    AccessKeyIssuerService,
    AccessKeyValidationError,
)
from nmp.common.auth.jwt import TokenClaims
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig
from nmp.common.entities import EntityClient, EntityConflictError, EntityNotFoundError
from nmp.common.service.dependencies import get_entity_client
from nmp.core.auth.entities import AccessKeyEntity

ACCESS_KEY_WORKSPACE = "system"
logger = logging.getLogger(__name__)

# Service-bound keys are machine-to-machine credentials owned by the platform, not
# by the creating individual (AIRCORE-986). Every lifecycle operation therefore
# uses this callback to require a current PlatformAdmin, including when the caller
# originally created the key.
AdminOverride = Callable[[], Awaitable[bool]]


def _memoize_admin_override(admin_override: AdminOverride | None) -> AdminOverride | None:
    """Cache a single admin_override result for the lifetime of one lifecycle call.

    _get_owned() may be invoked twice within one revoke()/suspend()/unsuspend() call
    (initial read, then a re-read after a losing optimistic-lock race). Without this,
    each read would trigger its own PDP has_role round trip for service-bound keys.
    """
    if admin_override is None:
        return None
    result: bool | None = None

    async def cached() -> bool:
        nonlocal result
        if result is None:
            result = await admin_override()
        return result

    return cached


class AccessKeyNotFoundError(Exception):
    """Raised when a key does not exist or is not owned by the caller."""


class AccessKeyStateConflictError(Exception):
    """Raised when an irreversible lifecycle state prevents a transition."""


class AccessKeyRegistry:
    """Durable access-key lifecycle records stored by the entities service."""

    def __init__(self, entity_client: EntityClient) -> None:
        self._entity_client = entity_client

    async def add(self, key: AccessKeyCreateResponse, *, owner_principal: str | None = None) -> None:
        owner = owner_principal or key.principal
        await self._entity_client.create(
            AccessKeyEntity(
                name=key.jti,
                workspace=ACCESS_KEY_WORKSPACE,
                key_name=key.name,
                description=key.description,
                principal=owner,
                subject_principal=key.principal if key.principal != owner else None,
                entity_type=key.entity_type,
                issuer=key.issuer,
                audiences=key.audiences,
                issued_at=key.created_at,
                expires_at=key.expires_at,
            )
        )

    async def list_for_principal(
        self, principal: str, *, page: int, page_size: int, include_service_accounts: bool = False
    ) -> AccessKeyListResponse:
        # Service-bound keys are platform-owned, not creator-owned (AIRCORE-986): a
        # PlatformAdmin other than the creator can already revoke/suspend one via
        # _get_owned's admin_override, so listing must surface every service-bound key
        # to any current admin rather than only the one who happened to create it.
        # EntityBase fields (all fields on AccessKeyEntity besides the base name/workspace/etc.)
        # live in the data JSON column, so filter_operation needs the same `data.` prefix
        # that _convert_filter_obj_to_filter_str applies for the filter_obj shorthand.
        own_principal = ComparisonOperation(operator=FilterOperator.EQ, field="data.principal", value=principal)
        filter_operation = (
            LogicalOperation(
                operator=FilterOperator.OR,
                operations=[
                    own_principal,
                    ComparisonOperation(operator=FilterOperator.EQ, field="data.entity_type", value="SERVICE_ACCOUNT"),
                ],
            )
            if include_service_accounts
            else own_principal
        )
        result = await self._entity_client.list(
            AccessKeyEntity,
            workspace=ACCESS_KEY_WORKSPACE,
            filter_operation=filter_operation,
            sort="-issued_at",
            page=page,
            page_size=page_size,
        )
        records = result.data
        if not include_service_accounts:
            records = [record for record in records if record.entity_type != "SERVICE_ACCOUNT"]
        # Short non-admin pages after Python filtering are intentional: favor never hiding valid keys over exact pagination; no fix needed.
        return AccessKeyListResponse(
            data=[self._metadata(record) for record in records],
            has_more=page < result.pagination.total_pages,
        )

    async def revoke(self, jti: str, principal: str, *, admin_override: AdminOverride | None = None) -> bool:
        # Note: unlike is_active, revoke has no backfill path for legacy v1 keys that have
        # never authenticated after migration. Without the original JWT claims we cannot
        # construct a valid entity, so callers receive 404 until the key authenticates once.
        admin_override = _memoize_admin_override(admin_override)
        record = await self._get_owned(jti, principal, admin_override=admin_override)
        if record.status == "REVOKED":
            return False
        updated = record.model_copy(update={"status": "REVOKED"})
        try:
            await self._entity_client.update(updated)
        except EntityConflictError:
            # EntityClient.update uses db_version optimistic locking. Re-read to
            # determine whether a concurrent revoke won the race.
            try:
                current = await self._get_owned(jti, principal, admin_override=admin_override)
            except AccessKeyNotFoundError:
                # The key was concurrently hard-deleted between our update and this
                # read. Treat as already-revoked (idempotent outcome).
                return False
            if current.status == "REVOKED":
                return False
            raise
        return True

    async def suspend(
        self, jti: str, principal: str, *, admin_override: AdminOverride | None = None
    ) -> tuple[bool, AccessKeyReversibleStatus]:
        return await self._set_suspension(jti, principal, suspended=True, admin_override=admin_override)

    async def unsuspend(
        self, jti: str, principal: str, *, admin_override: AdminOverride | None = None
    ) -> tuple[bool, AccessKeyReversibleStatus]:
        return await self._set_suspension(jti, principal, suspended=False, admin_override=admin_override)

    async def _set_suspension(
        self,
        jti: str,
        principal: str,
        *,
        suspended: bool,
        admin_override: AdminOverride | None = None,
    ) -> tuple[bool, AccessKeyReversibleStatus]:
        target_status: Literal["ACTIVE", "SUSPENDED"] = "SUSPENDED" if suspended else "ACTIVE"
        completed_action = "suspended" if suspended else "unsuspended"
        admin_override = _memoize_admin_override(admin_override)
        record = await self._get_owned(jti, principal, admin_override=admin_override)
        if record.status == "REVOKED":
            raise AccessKeyStateConflictError(f"Revoked Scoped Access Key {jti} cannot be {completed_action}")
        effective_status = self._reversible_status(record)
        if effective_status == "EXPIRED":
            return False, effective_status
        if record.status == target_status:
            return False, effective_status
        updated = record.model_copy(update={"status": target_status})
        try:
            await self._entity_client.update(updated)
        except EntityConflictError:
            # EntityClient.update uses db_version optimistic locking. Re-read to
            # determine whether a concurrent update won the race.
            current = await self._get_owned(jti, principal, admin_override=admin_override)
            if current.status == "REVOKED":
                raise AccessKeyStateConflictError(f"Revoked Scoped Access Key {jti} cannot be {completed_action}")
            current_status = self._reversible_status(current)
            if current_status == "EXPIRED" or current.status == target_status:
                return False, current_status
            raise
        return True, self._reversible_status(updated)

    async def is_active(self, jti: str, principal: str, *, claims: TokenClaims | None = None) -> bool:
        try:
            record = await self._get_for_subject(jti, principal)
        except AccessKeyNotFoundError:
            if claims is None:
                return False
            record = await self._backfill_legacy_record(jti, principal, claims)
            if record is None:
                return False
        return self._status(record, leeway_seconds=30) == "ACTIVE"

    async def _get_for_subject(self, jti: str, principal: str) -> AccessKeyEntity:
        record = await self._get(jti)
        if (record.subject_principal or record.principal) != principal:
            raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found")
        return record

    async def _get_owned(
        self, jti: str, principal: str, *, admin_override: AdminOverride | None = None
    ) -> AccessKeyEntity:
        record = await self._get(jti)
        if record.is_service_account:
            # Service-bound keys belong to the platform, not to the administrator who
            # created them. Require the caller to be a *current* PlatformAdmin for every
            # lifecycle operation, including when that caller is the recorded creator.
            if admin_override is not None and await admin_override():
                return record
        elif record.principal == principal:
            return record
        raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found")

    async def _get(self, jti: str) -> AccessKeyEntity:
        try:
            return await self._entity_client.get(
                AccessKeyEntity,
                name=jti,
                workspace=ACCESS_KEY_WORKSPACE,
            )
        except EntityNotFoundError as exc:
            raise AccessKeyNotFoundError(f"Scoped Access Key {jti} was not found") from exc

    @staticmethod
    def _metadata(record: AccessKeyEntity) -> AccessKeyMetadataResponse:
        return AccessKeyMetadataResponse(
            jti=record.name,
            name=record.key_name,
            description=record.description,
            principal=record.subject_principal or record.principal,
            entity_type=record.entity_type,
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
        if record.expires_at is not None and datetime.now(tz=UTC) >= record.expires_at + timedelta(
            seconds=leeway_seconds
        ):
            return "EXPIRED"
        if record.status == "SUSPENDED":
            return "SUSPENDED"
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
                return await self._get_for_subject(jti, principal)
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

    def __init__(
        self,
        config: AuthConfig,
        principal: Principal,
        registry: AccessKeyRegistry,
        *,
        admin_override: AdminOverride | None = None,
    ) -> None:
        self._issuer = AccessKeyIssuerService(config=config, principal=principal)
        self._config = config
        self._registry = registry
        self.principal = principal.id
        # Lets any current PlatformAdmin revoke or suspend a service-bound key;
        # see AdminOverride and AIRCORE-986. Memoized for the lifetime of this issuer
        # instance (one per request, see get_access_key_issuer) so that an endpoint-level
        # pre-check (is_platform_admin) and create_async's own defense-in-depth re-check
        # share a single PDP has_role round trip instead of each paying for one.
        self._admin_override = _memoize_admin_override(admin_override)

    async def is_platform_admin(self) -> bool:
        """Whether the caller is a current PlatformAdmin.

        Backed by the same memoized admin_override create_async consults, so callers that
        need to gate on PlatformAdmin status before invoking create_async (to return 403
        instead of create_async's 400) do not trigger a second PDP round trip.
        """
        return self._admin_override is not None and await self._admin_override()

    async def create_async(
        self, request: AccessKeyCreateRequest, *, allow_service_account: bool = False
    ) -> AccessKeyCreateResponse:
        self._ensure_enabled()
        if allow_service_account:
            # Defense-in-depth, mirroring the admin_override re-check that revoke/suspend/
            # unsuspend apply for service-bound keys: don't rely solely on the caller having
            # verified PlatformAdmin status before setting this flag (see AdminOverride).
            if not await self.is_platform_admin():
                raise AccessKeyValidationError("Service-bound Scoped Access Keys require PlatformAdmin")
        key = await self._issuer.create_async(request, allow_service_account=allow_service_account)
        try:
            await self._registry.add(key, owner_principal=self.principal)
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
        # A current PlatformAdmin sees every service-bound key, not just the ones they
        # personally created, mirroring the admin_override check lifecycle operations
        # already apply (see AccessKeyRegistry.list_for_principal). If the PDP role check
        # itself fails (e.g. unreachable), degrade to the caller's own keys rather than
        # failing listing outright for every user.
        try:
            include_service_accounts = await self.is_platform_admin()
        except HTTPException:
            logger.warning(
                "PlatformAdmin check failed while listing Scoped Access Keys; "
                "falling back to listing only the caller's own keys",
                extra={"actor_principal": self.principal},
                exc_info=True,
            )
            include_service_accounts = False
        return await self._registry.list_for_principal(
            self.principal, page=page, page_size=page_size, include_service_accounts=include_service_accounts
        )

    async def revoke_async(self, jti: str) -> bool:
        self._ensure_enabled()
        revoked = await self._registry.revoke(jti, self.principal, admin_override=self._admin_override)
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
        suspended, effective_status = await self._registry.suspend(
            jti, self.principal, admin_override=self._admin_override
        )
        self._log_suspension(jti, changed=suspended, action="suspend")
        return suspended, effective_status

    async def unsuspend_async(self, jti: str) -> tuple[bool, AccessKeyReversibleStatus]:
        self._ensure_enabled()
        unsuspended, effective_status = await self._registry.unsuspend(
            jti, self.principal, admin_override=self._admin_override
        )
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
