# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_platform_plugin.auth.access_keys.types import AccessKeyCreateResponse
from nmp.common.auth.jwt import TokenClaims
from nmp.common.entities import EntityConflictError, EntityNotFoundError
from nmp.core.auth.app.access_keys import AccessKeyNotFoundError, AccessKeyRegistry, AccessKeyStateConflictError
from nmp.core.auth.entities import AccessKeyEntity

NOW = datetime(2026, 8, 4, 18, 0, tzinfo=UTC)


def _record(*, jti: str = "ak_example", principal: str = "alice@example.com", revoked: bool = False):
    return AccessKeyEntity(
        name=jti,
        workspace="system",
        key_name="ci-build",
        description="CI build automation",
        principal=principal,
        issued_at=NOW,
        expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        status="REVOKED" if revoked else "ACTIVE",
        issuer="https://platform.example.com/apis/auth",
        audiences=["nemo-platform-access-key"],
    )


def _suspended_record() -> AccessKeyEntity:
    return _record(jti="ak_suspended").model_copy(update={"status": "SUSPENDED"})


def _expired_record() -> AccessKeyEntity:
    return _record(jti="ak_expired").model_copy(update={"expires_at": datetime(2000, 1, 1, tzinfo=UTC)})


def test_access_key_entity_migrates_legacy_revoked_at_to_status() -> None:
    record = AccessKeyEntity.model_validate(
        {
            "name": "ak_legacy_revoked",
            "workspace": "system",
            "principal": "alice@example.com",
            "issued_at": NOW,
            "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
            "issuer": "https://platform.example.com/apis/auth",
            "audiences": ["nemo-platform-access-key"],
            "revoked_at": NOW,
        }
    )

    assert record.status == "REVOKED"


def test_access_key_entity_defaults_unrevoked_legacy_record_to_active() -> None:
    record = AccessKeyEntity.model_validate(
        {
            "name": "ak_legacy_active",
            "workspace": "system",
            "principal": "alice@example.com",
            "issued_at": NOW,
            "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
            "issuer": "https://platform.example.com/apis/auth",
            "audiences": ["nemo-platform-access-key"],
            "revoked_at": None,
        }
    )

    assert record.status == "ACTIVE"


@pytest.mark.asyncio
async def test_registry_persists_created_key_metadata() -> None:
    entity_client = AsyncMock()
    registry = AccessKeyRegistry(entity_client)
    key = AccessKeyCreateResponse(
        jti="ak_example",
        name="ci-build",
        principal="alice@example.com",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        description="CI build automation",
        status="ACTIVE",
        issuer="https://platform.example.com/apis/auth",
        audiences=["nemo-platform-access-key"],
        token="secret-token",
        token_type="Bearer",
    )

    await registry.add(key)

    saved = entity_client.create.await_args.args[0]
    assert isinstance(saved, AccessKeyEntity)
    assert saved.name == "ak_example"
    assert saved.key_name == "ci-build"
    assert saved.description == "CI build automation"
    assert "secret-token" not in saved.model_dump_json()


@pytest.mark.asyncio
async def test_registry_lists_principals_keys_with_status_across_pages() -> None:
    entity_client = AsyncMock()
    active_record = _record().model_copy(update={"audiences": ["nemo-platform-access-key", "nemo-platform-access-key"]})
    entity_client.list.return_value = SimpleNamespace(
        data=[active_record, _record(jti="ak_revoked", revoked=True)], pagination=SimpleNamespace(total_pages=2)
    )
    registry = AccessKeyRegistry(entity_client)

    result = await registry.list_for_principal("alice@example.com", page=1, page_size=2)

    assert [key.jti for key in result.data] == ["ak_example", "ak_revoked"]
    assert [key.status for key in result.data] == ["ACTIVE", "REVOKED"]
    assert result.data[0].audiences == ["nemo-platform-access-key"]
    assert result.has_more
    entity_client.list.assert_awaited_once()
    assert entity_client.list.await_args.kwargs["page"] == 1
    assert entity_client.list.await_args.kwargs["page_size"] == 2
    assert entity_client.list.await_args.kwargs["filter_obj"] == {"principal": "alice@example.com"}


@pytest.mark.asyncio
async def test_registry_can_retrieve_later_list_page() -> None:
    entity_client = AsyncMock()
    entity_client.list.return_value = SimpleNamespace(
        data=[_record(jti="ak_later")], pagination=SimpleNamespace(total_pages=12)
    )
    registry = AccessKeyRegistry(entity_client)

    result = await registry.list_for_principal("alice@example.com", page=11, page_size=25)

    assert [key.jti for key in result.data] == ["ak_later"]
    assert result.has_more
    assert entity_client.list.await_args.kwargs["page"] == 11
    assert entity_client.list.await_args.kwargs["page_size"] == 25


@pytest.mark.asyncio
async def test_registry_reports_expired_status() -> None:
    entity_client = AsyncMock()
    entity_client.list.return_value = SimpleNamespace(
        data=[_expired_record()], pagination=SimpleNamespace(total_pages=1)
    )
    registry = AccessKeyRegistry(entity_client)

    result = await registry.list_for_principal("alice@example.com", page=1, page_size=100)

    assert result.data[0].status == "EXPIRED"


@pytest.mark.asyncio
async def test_registry_reports_expired_at_timestamp_while_authentication_allows_clock_skew() -> None:
    record = _record().model_copy(update={"expires_at": datetime.now(tz=UTC) - timedelta(seconds=1)})
    entity_client = AsyncMock()
    entity_client.list.return_value = SimpleNamespace(data=[record], pagination=SimpleNamespace(total_pages=1))
    entity_client.get.return_value = record
    registry = AccessKeyRegistry(entity_client)

    result = await registry.list_for_principal("alice@example.com", page=1, page_size=100)

    assert result.data[0].status == "EXPIRED"
    assert await registry.is_active(record.name, record.principal)


@pytest.mark.asyncio
async def test_registry_revokes_owned_key_without_deleting_audit_record() -> None:
    entity_client = AsyncMock()
    original = _record()
    entity_client.get.return_value = original
    registry = AccessKeyRegistry(entity_client)

    assert await registry.revoke("ak_example", "alice@example.com")

    updated = entity_client.update.await_args.args[0]
    assert updated is not original
    assert original.status == "ACTIVE"
    assert updated.status == "REVOKED"
    entity_client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_registry_concurrent_revoke_reports_existing_revocation() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = [_record(), _record(revoked=True)]
    entity_client.update.side_effect = EntityConflictError("entity version changed")
    registry = AccessKeyRegistry(entity_client)

    assert not await registry.revoke("ak_example", "alice@example.com")

    assert entity_client.get.await_count == 2
    entity_client.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_registry_concurrent_revoke_with_hard_delete_treats_as_already_revoked() -> None:
    entity_client = AsyncMock()
    # First get succeeds; update conflicts; second get raises not-found (key deleted).
    entity_client.get.side_effect = [_record(), EntityNotFoundError("gone")]
    entity_client.update.side_effect = EntityConflictError("entity version changed")
    registry = AccessKeyRegistry(entity_client)

    assert not await registry.revoke("ak_example", "alice@example.com")

    assert entity_client.get.await_count == 2


@pytest.mark.asyncio
async def test_registry_concurrent_suspend_with_hard_delete_reports_not_found() -> None:
    entity_client = AsyncMock()
    # First get succeeds; update conflicts; second get raises not-found (key deleted).
    entity_client.get.side_effect = [_record(), EntityNotFoundError("gone")]
    entity_client.update.side_effect = EntityConflictError("entity version changed")
    registry = AccessKeyRegistry(entity_client)

    with pytest.raises(AccessKeyNotFoundError, match="Scoped Access Key ak_example was not found"):
        await registry.suspend("ak_example", "alice@example.com")

    assert entity_client.get.await_count == 2


@pytest.mark.asyncio
async def test_registry_can_newly_revoke_expired_key() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _expired_record()
    registry = AccessKeyRegistry(entity_client)

    assert await registry.revoke("ak_expired", "alice@example.com")

    updated = entity_client.update.await_args.args[0]
    assert updated.status == "REVOKED"


@pytest.mark.asyncio
async def test_registry_reports_revoked_key_as_inactive() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _record(revoked=True)
    registry = AccessKeyRegistry(entity_client)

    assert not await registry.is_active("ak_example", "alice@example.com")


@pytest.mark.asyncio
async def test_registry_hides_missing_and_other_principals_keys() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _record(principal="bob@example.com")
    registry = AccessKeyRegistry(entity_client)

    with pytest.raises(AccessKeyNotFoundError):
        await registry.revoke("ak_example", "alice@example.com")

    entity_client.get.side_effect = EntityNotFoundError("missing")
    assert not await registry.is_active("ak_missing", "alice@example.com")


@pytest.mark.asyncio
async def test_registry_backfills_missing_legacy_access_key_from_validated_claims() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = EntityNotFoundError("missing")
    registry = AccessKeyRegistry(entity_client)
    claims = TokenClaims(
        subject="alice@example.com",
        email=None,
        groups=[],
        scopes=[],
        raw_claims={
            "iss": "https://platform.example.com/apis/auth",
            "aud": ["nemo-platform-access-key", "nemo-platform-access-key"],
            "sub": "alice@example.com",
            "iat": 1_785_280_000,
            "nbf": 1_785_280_000,
            "exp": 1_893_456_000,
            "jti": "ak_legacy",
            "nmp_token_type": "access_key",
            "nmp_access_key": {"version": 1, "name": "legacy-key"},
        },
    )

    assert await registry.is_active("ak_legacy", "alice@example.com", claims=claims)

    saved = entity_client.create.await_args.args[0]
    assert saved.name == "ak_legacy"
    assert saved.key_name == "legacy-key"
    assert saved.description is None
    assert saved.principal == "alice@example.com"
    assert saved.issuer == "https://platform.example.com/apis/auth"
    assert saved.audiences == ["nemo-platform-access-key"]
    assert saved.issued_at == datetime.fromtimestamp(1_785_280_000, tz=UTC)
    assert saved.expires_at == datetime.fromtimestamp(1_893_456_000, tz=UTC)


@pytest.mark.asyncio
async def test_registry_reports_suspended_key_in_list() -> None:
    entity_client = AsyncMock()
    entity_client.list.return_value = SimpleNamespace(
        data=[_suspended_record()], pagination=SimpleNamespace(total_pages=1)
    )
    registry = AccessKeyRegistry(entity_client)

    result = await registry.list_for_principal("alice@example.com", page=1, page_size=100)

    assert result.data[0].status == "SUSPENDED"


@pytest.mark.asyncio
async def test_registry_suspension_precedes_expiration_until_key_is_unsuspended() -> None:
    suspended_expired = _expired_record().model_copy(update={"status": "SUSPENDED"})
    entity_client = AsyncMock()
    entity_client.list.return_value = SimpleNamespace(
        data=[suspended_expired], pagination=SimpleNamespace(total_pages=1)
    )
    entity_client.get.return_value = suspended_expired
    registry = AccessKeyRegistry(entity_client)

    listed = await registry.list_for_principal("alice@example.com", page=1, page_size=100)
    assert listed.data[0].status == "SUSPENDED"

    changed, effective_status = await registry.unsuspend("ak_expired", "alice@example.com")
    assert changed
    assert effective_status == "EXPIRED"
    restored = entity_client.update.await_args.args[0]
    assert AccessKeyRegistry._status(restored) == "EXPIRED"


@pytest.mark.asyncio
async def test_registry_revoke_transitions_suspended_key_to_revoked() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _suspended_record()
    registry = AccessKeyRegistry(entity_client)

    assert await registry.revoke("ak_suspended", "alice@example.com")

    updated = entity_client.update.await_args.args[0]
    assert updated.status == "REVOKED"


@pytest.mark.asyncio
async def test_registry_concurrent_revoke_retries_when_key_is_only_suspended() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = [_record(), _suspended_record()]
    entity_client.update.side_effect = EntityConflictError("entity version changed")
    registry = AccessKeyRegistry(entity_client)

    with pytest.raises(EntityConflictError, match="entity version changed"):
        await registry.revoke("ak_suspended", "alice@example.com")

    assert entity_client.get.await_count == 2
    entity_client.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_registry_reports_suspended_key_as_inactive() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _suspended_record()
    registry = AccessKeyRegistry(entity_client)

    assert not await registry.is_active("ak_suspended", "alice@example.com")


@pytest.mark.asyncio
async def test_registry_suspends_and_unsuspends_key() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = [_record(), _suspended_record()]
    registry = AccessKeyRegistry(entity_client)

    suspend_changed, suspend_status = await registry.suspend("ak_example", "alice@example.com")
    assert suspend_changed
    assert suspend_status == "SUSPENDED"
    assert entity_client.update.await_args_list[0].args[0].status == "SUSPENDED"
    unsuspend_changed, unsuspend_status = await registry.unsuspend("ak_suspended", "alice@example.com")
    assert unsuspend_changed
    assert unsuspend_status == "ACTIVE"
    assert entity_client.update.await_args_list[1].args[0].status == "ACTIVE"


@pytest.mark.asyncio
async def test_registry_suspension_operations_are_idempotent() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = [_suspended_record(), _record()]
    registry = AccessKeyRegistry(entity_client)

    suspend_changed, suspend_status = await registry.suspend("ak_suspended", "alice@example.com")
    assert not suspend_changed
    assert suspend_status == "SUSPENDED"
    unsuspend_changed, unsuspend_status = await registry.unsuspend("ak_example", "alice@example.com")
    assert not unsuspend_changed
    assert unsuspend_status == "ACTIVE"
    entity_client.update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["suspend", "unsuspend"])
async def test_registry_rejects_suspension_transition_for_revoked_key(operation: str) -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _record(revoked=True)
    registry = AccessKeyRegistry(entity_client)

    with pytest.raises(AccessKeyStateConflictError, match=f"cannot be {operation}ed"):
        await getattr(registry, operation)("ak_example", "alice@example.com")

    entity_client.update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "current"),
    [("suspend", _suspended_record()), ("unsuspend", _record())],
)
async def test_registry_concurrent_suspension_transition_reports_target_state(
    operation: str, current: AccessKeyEntity
) -> None:
    initial = _record() if operation == "suspend" else _suspended_record()
    entity_client = AsyncMock()
    entity_client.get.side_effect = [initial, current]
    entity_client.update.side_effect = EntityConflictError("entity version changed")
    registry = AccessKeyRegistry(entity_client)

    changed, effective_status = await getattr(registry, operation)(initial.name, initial.principal)
    assert not changed
    assert effective_status == current.status
    assert entity_client.get.await_count == 2
    entity_client.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_registry_concurrent_suspension_transition_rejects_revocation() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = [_record(), _record(revoked=True)]
    entity_client.update.side_effect = EntityConflictError("entity version changed")
    registry = AccessKeyRegistry(entity_client)

    with pytest.raises(AccessKeyStateConflictError, match="cannot be suspended"):
        await registry.suspend("ak_example", "alice@example.com")


@pytest.mark.asyncio
async def test_registry_rejects_missing_current_access_key_record() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = EntityNotFoundError("missing")
    registry = AccessKeyRegistry(entity_client)
    claims = TokenClaims(
        subject="alice@example.com",
        email=None,
        groups=[],
        scopes=[],
        raw_claims={
            "iss": "https://platform.example.com/apis/auth",
            "aud": ["nemo-platform-access-key"],
            "sub": "alice@example.com",
            "iat": 1_785_280_000,
            "nbf": 1_785_280_000,
            "exp": 1_893_456_000,
            "jti": "ak_current",
            "nmp_token_type": "access_key",
            "nmp_access_key": {"version": 2, "name": "current-key"},
        },
    )

    assert not await registry.is_active("ak_current", "alice@example.com", claims=claims)
    entity_client.create.assert_not_awaited()
