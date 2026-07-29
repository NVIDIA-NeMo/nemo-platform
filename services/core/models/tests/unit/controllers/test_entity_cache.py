# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ModelEntityCache."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from nemo_platform import AsyncNeMoPlatform
from nemo_platform._exceptions import ConflictError, NotFoundError
from nmp.core.models.controllers.entity_cache import ModelEntityCache, UnflushedMutationsError

from .conftest import AsyncPaginator, make_entity, seed_entity_cache


def _entity(workspace="ws", name="model", model_providers=None, **attrs):
    return make_entity(workspace, name, model_providers=model_providers, **attrs)


@pytest.fixture
def mock_models_sdk():
    sdk = MagicMock(spec=AsyncNeMoPlatform)
    sdk.models.list = MagicMock(return_value=AsyncPaginator([]))
    sdk.models.create = AsyncMock(return_value=None)
    sdk.models.update = AsyncMock(return_value=None)
    sdk.models.retrieve = AsyncMock()
    return sdk


@pytest.fixture
def heartbeat_calls():
    """Collects heartbeat emissions so tests can assert progress was reported."""
    return []


@pytest.fixture
def cache(mock_models_sdk, heartbeat_calls):
    return ModelEntityCache(models_sdk=mock_models_sdk, emit_heartbeat=lambda: heartbeat_calls.append(1))


async def _load(mock_models_sdk, cache, entities=()):
    await seed_entity_cache(mock_models_sdk, cache, entities)


@pytest.mark.asyncio
async def test_refresh_loads_entities_keyed_by_workspace_and_name(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache, [_entity("ws-a", "m1"), _entity("ws-b", "m1")])

    assert cache.loaded
    assert cache.get("ws-a", "m1") is not None
    assert cache.get("ws-b", "m1") is not None
    assert cache.get("ws-c", "m1") is None


@pytest.mark.asyncio
async def test_refresh_rejects_unflushed_mutations(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache)
    cache.stage_provider_link("ws", "model", "ws/p1")

    with pytest.raises(UnflushedMutationsError):
        await cache.refresh()


@pytest.mark.asyncio
async def test_get_reflects_staged_provider_link_within_a_phase(mock_models_sdk, cache):
    """A read after a stage in the same phase must observe the staged change."""
    await _load(mock_models_sdk, cache, [_entity("ws", "model", ["ws/p1"])])

    cache.stage_provider_link("ws", "model", "ws/p2")

    assert cache.get("ws", "model").model_providers == ["ws/p1", "ws/p2"]


@pytest.mark.asyncio
async def test_get_reflects_staged_provider_unlink_within_a_phase(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache, [_entity("ws", "model", ["ws/p1", "ws/p2"])])

    cache.stage_provider_unlink("ws", "model", "ws/p1")

    assert cache.get("ws", "model").model_providers == ["ws/p2"]


@pytest.mark.asyncio
async def test_entity_staged_for_creation_still_reads_as_absent(mock_models_sdk, cache):
    """A staged creation is not fabricated, so callers keep treating it as new."""
    await _load(mock_models_sdk, cache)

    cache.stage_create("ws", "new-model", description="d", backend_format="OPENAI_CHAT")
    cache.stage_provider_link("ws", "new-model", "ws/p1")

    assert cache.get("ws", "new-model") is None


@pytest.mark.asyncio
async def test_multiple_providers_produce_a_single_update(mock_models_sdk, cache):
    """An entity linked by several providers is written once, not once per provider."""
    await _load(mock_models_sdk, cache, [_entity("ws", "model", [])])

    cache.stage_provider_link("ws", "model", "ws/p1")
    cache.stage_provider_link("ws", "model", "ws/p2")
    await cache.flush()

    mock_models_sdk.models.update.assert_awaited_once_with(
        workspace="ws", name="model", model_providers=["ws/p1", "ws/p2"]
    )


@pytest.mark.asyncio
async def test_no_write_when_already_converged(mock_models_sdk, cache):
    """Staging state that already matches the entity performs no write."""
    await _load(mock_models_sdk, cache, [_entity("ws", "model", ["ws/p1"])])

    cache.stage_provider_link("ws", "model", "ws/p1")
    await cache.flush()

    mock_models_sdk.models.update.assert_not_awaited()
    mock_models_sdk.models.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_providers_creating_the_same_entity_collapse_to_one_create(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache)

    cache.stage_create("ws", "model", description="from p1", backend_format="OPENAI_CHAT")
    cache.stage_provider_link("ws", "model", "ws/p1")
    cache.stage_create("ws", "model", description="from p2", backend_format="OPENAI_CHAT")
    cache.stage_provider_link("ws", "model", "ws/p2")
    await cache.flush()

    mock_models_sdk.models.create.assert_awaited_once_with(
        workspace="ws",
        name="model",
        description="from p1",
        backend_format="OPENAI_CHAT",
        model_providers=["ws/p1", "ws/p2"],
    )


@pytest.mark.asyncio
async def test_create_conflict_falls_back_to_updating_the_existing_entity(mock_models_sdk, cache):
    """An entity created concurrently is adopted rather than reported as an error."""
    await _load(mock_models_sdk, cache)
    mock_models_sdk.models.create = AsyncMock(side_effect=ConflictError("exists", response=MagicMock(), body=None))
    mock_models_sdk.models.retrieve = AsyncMock(return_value=_entity("ws", "model", ["ws/other"]))

    cache.stage_create("ws", "model", description="d", backend_format="OPENAI_CHAT")
    cache.stage_provider_link("ws", "model", "ws/p1")
    await cache.flush()

    mock_models_sdk.models.update.assert_awaited_once_with(
        workspace="ws", name="model", model_providers=["ws/other", "ws/p1"]
    )


@pytest.mark.asyncio
async def test_create_conflict_with_vanished_entity_is_ignored(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache)
    mock_models_sdk.models.create = AsyncMock(side_effect=ConflictError("exists", response=MagicMock(), body=None))
    mock_models_sdk.models.retrieve = AsyncMock(side_effect=NotFoundError("gone", response=MagicMock(), body=None))

    cache.stage_create("ws", "model", description="d")
    await cache.flush()

    mock_models_sdk.models.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_failing_entity_does_not_stop_the_others(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache, [_entity("ws", "m1", []), _entity("ws", "m2", [])])
    mock_models_sdk.models.update = AsyncMock(side_effect=[Exception("boom"), None])

    cache.stage_provider_link("ws", "m1", "ws/p1")
    cache.stage_provider_link("ws", "m2", "ws/p1")
    await cache.flush()

    assert mock_models_sdk.models.update.await_count == 2


@pytest.mark.asyncio
async def test_failed_write_is_kept_for_retry_and_succeeds_later(mock_models_sdk, cache):
    """A write that fails must not be lost.

    Some staged changes cannot be recomputed by a later pass -- unlinking a provider
    that is being deleted is derived from that provider -- so a dropped failure
    would leave the entity permanently inconsistent.
    """
    await _load(mock_models_sdk, cache, [_entity("ws", "m1", ["ws/p1"]), _entity("ws", "m2", ["ws/p1"])])
    mock_models_sdk.models.update = AsyncMock(side_effect=[Exception("boom"), None])

    cache.stage_provider_unlink("ws", "m1", "ws/p1")
    cache.stage_provider_unlink("ws", "m2", "ws/p1")
    await cache.flush()

    # The successful entity is done; the failed one is still staged.
    assert cache.get("ws", "m1").model_providers == []
    assert ("ws", "m1") in cache._pending
    assert ("ws", "m2") not in cache._pending

    # A later flush retries it, and this time it lands.
    mock_models_sdk.models.update = AsyncMock(return_value=None)
    await cache.flush()

    mock_models_sdk.models.update.assert_awaited_once_with(workspace="ws", name="m1", model_providers=[])
    assert cache._pending == {}


@pytest.mark.asyncio
async def test_refresh_allows_retained_failures_but_still_rejects_unflushed_work(mock_models_sdk, cache):
    """Refresh distinguishes "flushed and failed" from "staged and forgotten"."""
    await _load(mock_models_sdk, cache, [_entity("ws", "m1", ["ws/p1"])])
    mock_models_sdk.models.update = AsyncMock(side_effect=Exception("boom"))

    cache.stage_provider_unlink("ws", "m1", "ws/p1")
    await cache.flush()
    assert ("ws", "m1") in cache._pending

    # A retained failure does not block the next phase from re-reading.
    await _load(mock_models_sdk, cache, [_entity("ws", "m1", ["ws/p1"])])

    # Work that no flush has attempted still does.
    cache.stage_provider_link("ws", "m2", "ws/p2")
    with pytest.raises(UnflushedMutationsError):
        await cache.refresh()


@pytest.mark.asyncio
async def test_retained_failure_replays_against_a_newer_snapshot(mock_models_sdk, cache):
    """Staged changes are differences, so replaying them after a refresh stays correct."""
    await _load(mock_models_sdk, cache, [_entity("ws", "m1", ["ws/p1", "ws/p2"])])
    mock_models_sdk.models.update = AsyncMock(side_effect=Exception("boom"))

    cache.stage_provider_unlink("ws", "m1", "ws/p1")
    await cache.flush()

    # Snapshot moves on: another writer added a third provider meanwhile.
    await _load(mock_models_sdk, cache, [_entity("ws", "m1", ["ws/p1", "ws/p2", "ws/p3"])])
    mock_models_sdk.models.update = AsyncMock(return_value=None)
    await cache.flush()

    # The unlink applies to the newer state rather than reinstating the old list.
    mock_models_sdk.models.update.assert_awaited_once_with(
        workspace="ws", name="m1", model_providers=["ws/p2", "ws/p3"]
    )


@pytest.mark.asyncio
async def test_flush_clears_staged_changes(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache, [_entity("ws", "model", [])])

    cache.stage_provider_link("ws", "model", "ws/p1")
    await cache.flush()
    mock_models_sdk.models.update.reset_mock()

    # Nothing left staged, so a second flush writes nothing and a refresh is allowed.
    await cache.flush()
    mock_models_sdk.models.update.assert_not_awaited()
    await cache.refresh()


@pytest.mark.asyncio
async def test_link_then_unlink_for_the_same_provider_cancels_out(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache, [_entity("ws", "model", ["ws/p1"])])

    cache.stage_provider_unlink("ws", "model", "ws/p1")
    cache.stage_provider_link("ws", "model", "ws/p1")
    await cache.flush()

    mock_models_sdk.models.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_field_updates_are_written_as_staged(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache, [_entity("ws", "model", ["ws/p1"])])

    cache.stage_field_updates("ws", "model", fileset="hub/model", api_endpoint=None)
    await cache.flush()

    mock_models_sdk.models.update.assert_awaited_once_with(workspace="ws", name="model", fileset="hub/model")


@pytest.mark.asyncio
async def test_staged_change_for_missing_entity_without_create_is_skipped(mock_models_sdk, cache):
    await _load(mock_models_sdk, cache)

    cache.stage_provider_unlink("ws", "ghost", "ws/p1")
    await cache.flush()

    mock_models_sdk.models.create.assert_not_awaited()
    mock_models_sdk.models.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_after_flush_does_not_reapply_earlier_state(mock_models_sdk, cache):
    """A link removed in one phase is not reinstated by the next phase.

    The second phase must decide from a snapshot that already reflects the first
    phase's writes, otherwise it would re-add what was just removed.
    """
    store = {("ws", "model"): _entity("ws", "model", ["ws/p1"])}

    def _list(**_kwargs):
        return AsyncPaginator(list(store.values()))

    async def _update(*, workspace, name, **params):
        current = store[(workspace, name)]
        store[(workspace, name)] = _entity(workspace, name, params.get("model_providers", current.model_providers))
        return store[(workspace, name)]

    mock_models_sdk.models.list = MagicMock(side_effect=_list)
    mock_models_sdk.models.update = AsyncMock(side_effect=_update)

    # Phase one removes the provider link and applies it.
    await cache.refresh()
    cache.stage_provider_unlink("ws", "model", "ws/p1")
    await cache.flush()
    assert store[("ws", "model")].model_providers == []

    # Phase two re-reads, so it sees the removal instead of the stale link.
    await cache.refresh()
    assert cache.get("ws", "model").model_providers == []


@pytest.mark.asyncio
async def test_refresh_reports_progress_per_entity_read(mock_models_sdk, cache, heartbeat_calls):
    """Reading a large batch has to report progress as it goes."""
    await _load(mock_models_sdk, cache, [_entity("ws", f"m{i}") for i in range(25)])

    assert len(heartbeat_calls) == 25


@pytest.mark.asyncio
async def test_flush_reports_progress_per_entity_written(mock_models_sdk, cache, heartbeat_calls):
    """Writing a large batch has to report progress as it goes.

    Writes are the slowest part of a pass, so a flush that reported nothing would
    make a long but advancing pass indistinguishable from a stalled one.
    """
    await _load(mock_models_sdk, cache, [_entity("ws", f"m{i}", []) for i in range(25)])
    heartbeat_calls.clear()

    for i in range(25):
        cache.stage_provider_link("ws", f"m{i}", "ws/p1")
    await cache.flush()

    assert mock_models_sdk.models.update.await_count == 25
    assert len(heartbeat_calls) == 25


@pytest.mark.asyncio
async def test_flush_reports_progress_even_when_an_entity_write_fails(mock_models_sdk, cache, heartbeat_calls):
    """Moving past a failed entity is still progress."""
    await _load(mock_models_sdk, cache, [_entity("ws", "m1", []), _entity("ws", "m2", [])])
    mock_models_sdk.models.update = AsyncMock(side_effect=[Exception("boom"), None])
    heartbeat_calls.clear()

    cache.stage_provider_link("ws", "m1", "ws/p1")
    cache.stage_provider_link("ws", "m2", "ws/p1")
    await cache.flush()

    assert len(heartbeat_calls) == 2


@pytest.mark.asyncio
async def test_conflict_adoption_does_not_overwrite_the_existing_entity_attributes(mock_models_sdk, cache):
    """Adopting a concurrently-created entity leaves its own attributes alone.

    Attributes supplied for creation describe an entity we expected to create. When
    another writer got there first, theirs win; the owning reconciler re-evaluates
    what is still missing on a later pass.
    """
    await _load(mock_models_sdk, cache)
    mock_models_sdk.models.create = AsyncMock(side_effect=ConflictError("exists", response=MagicMock(), body=None))
    mock_models_sdk.models.retrieve = AsyncMock(
        return_value=_entity("ws", "model", ["ws/other"], backend_format="ANTHROPIC_MESSAGES")
    )

    cache.stage_create("ws", "model", description="ours", backend_format="OPENAI_CHAT")
    cache.stage_provider_link("ws", "model", "ws/p1")
    await cache.flush()

    # Only the provider link is written; description/backend_format are not forced.
    mock_models_sdk.models.update.assert_awaited_once_with(
        workspace="ws", name="model", model_providers=["ws/other", "ws/p1"]
    )
