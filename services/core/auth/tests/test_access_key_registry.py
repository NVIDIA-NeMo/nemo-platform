# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_platform_plugin.auth.access_keys.types import AccessKeyCreateResponse
from nmp.common.auth.jwt import TokenClaims
from nmp.common.entities import EntityNotFoundError
from nmp.core.auth.app.access_keys import AccessKeyNotFoundError, AccessKeyRegistry
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
        revoked_at=NOW if revoked else None,
        issuer="https://platform.example.com/apis/auth",
        audiences=["nemo-platform-access-key"],
    )


def _expired_record() -> AccessKeyEntity:
    return _record(jti="ak_expired").model_copy(update={"expires_at": datetime(2026, 8, 3, 18, 0, tzinfo=UTC)})


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
    entity_client.list.return_value = SimpleNamespace(
        data=[_record(), _record(jti="ak_revoked", revoked=True)], pagination=SimpleNamespace(total_pages=2)
    )
    registry = AccessKeyRegistry(entity_client)

    result = await registry.list_for_principal("alice@example.com", page=1, page_size=2)

    assert [key.jti for key in result.data] == ["ak_example", "ak_revoked"]
    assert [key.status for key in result.data] == ["ACTIVE", "REVOKED"]
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
async def test_registry_revokes_owned_key_without_deleting_audit_record() -> None:
    entity_client = AsyncMock()
    original = _record()
    entity_client.get.return_value = original
    registry = AccessKeyRegistry(entity_client)

    assert await registry.revoke("ak_example", "alice@example.com")

    updated = entity_client.update.await_args.args[0]
    assert updated is not original
    assert original.revoked_at is None
    assert updated.revoked_at is not None
    entity_client.delete.assert_not_awaited()


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
            "aud": ["nemo-platform-access-key"],
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
