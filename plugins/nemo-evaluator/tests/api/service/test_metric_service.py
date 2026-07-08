# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.api.service.metric_service import MetricService
from nemo_evaluator.entities import MetricBundleEntity
from nemo_evaluator.metric_storage import parse_bundle_ref
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_platform_plugin.entities import (
    EntityConflictError,
    EntityNotFoundError,
    ListResponse,
    PaginationInfo,
)

# ---- in-memory fakes -------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeAsyncFilesClient:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, bytes]] = {}

    async def create_fileset(self, *, body, workspace=None, exist_ok=False):
        self._store.setdefault((workspace, body.name), {})
        return AsyncMock(data=lambda: object())

    async def delete_fileset(self, *, name, workspace=None):
        self._store.pop((workspace, name), None)
        return AsyncMock(data=lambda: object())

    async def upload_file(self, *, path, content, workspace, name):
        self._store.setdefault((workspace, name), {})[path] = bytes(content)
        return AsyncMock(data=lambda: object())

    async def download_file(self, *, path, workspace, name):
        return _FakeResponse(self._store[(workspace, name)][path])


class _FakeEntityClient:
    def __init__(self) -> None:
        self.entities: dict[tuple[str, str], MetricBundleEntity] = {}

    async def get(self, entity_cls, *, workspace, name):
        key = (workspace, name)
        if key not in self.entities:
            raise EntityNotFoundError(f"{workspace}/{name} not found")
        return self.entities[key]

    async def create(self, entity):
        key = (entity.workspace, entity.name)
        if key in self.entities:
            raise EntityConflictError(f"{key} exists")
        now = datetime.now(timezone.utc)
        entity._id = f"metric_bundle-{entity.name}"
        entity._created_at = now
        entity._updated_at = now
        self.entities[key] = entity
        return entity

    async def delete(self, entity_cls, name, *, workspace):
        self.entities.pop((workspace, name), None)

    async def list(self, entity_cls, *, workspace, filter_operation=None, sort=None, page=1, page_size=100):
        items = [e for (ws, _), e in self.entities.items() if ws == workspace]
        return ListResponse(
            data=items,
            pagination=PaginationInfo(
                page=page,
                page_size=page_size,
                current_page_size=len(items),
                total_pages=1,
                total_results=len(items),
            ),
        )


@pytest.fixture
def fake_files():
    return _FakeAsyncFilesClient()


@pytest.fixture
def service(fake_files):
    svc = MetricService(_FakeEntityClient(), object())
    svc._fake_files = fake_files
    with patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_files):
        yield svc


def _bundle(metric=None) -> MetricInline:
    """Build a runtime bundle and return it as the API wire DTO (what requests carry)."""
    metric = metric or ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    runtime_bundle = bundle_metric(metric, CloudpickleMetricBundlePackager())
    return MetricInline.model_validate_json(runtime_bundle.model_dump_json())


def _fileset_of(service: MetricService, bundle_ref: str) -> tuple[str, str]:
    workspace, fileset, _ = parse_bundle_ref(bundle_ref)
    return (workspace, fileset)


# ---- tests -----------------------------------------------------------------


async def test_create_stores_bundle_and_indexes_entity(service: MetricService, fake_files) -> None:
    bundle = _bundle()
    created = await service.create_metric("exact", bundle, workspace="default")

    assert created.name == "exact"
    assert created.metric_type == bundle.metric_type
    assert created.payload_kind == "cloudpickle"
    assert created.payload_digest == bundle.payload.digest
    assert created.bundle_ref.startswith("default/metric-bundle.")
    assert created.description == bundle.metadata.description
    assert created.labels == bundle.metadata.labels
    assert _fileset_of(service, created.bundle_ref) in fake_files._store


async def test_create_rejects_duplicate_without_clobbering_existing(service: MetricService, fake_files) -> None:
    first = await service.create_metric("exact", _bundle(), workspace="default")

    with pytest.raises(ValueError, match="already exists"):
        await service.create_metric("exact", _bundle(), workspace="default")

    assert _fileset_of(service, first.bundle_ref) in fake_files._store


async def test_get_returns_none_when_missing(service: MetricService) -> None:
    assert await service.get_metric("default", "nope") is None


async def test_delete_removes_entity_and_bundle(service: MetricService, fake_files) -> None:
    created = await service.create_metric("m", _bundle(), workspace="default")

    assert await service.delete_metric("default", "m") is True
    assert await service.get_metric("default", "m") is None
    assert _fileset_of(service, created.bundle_ref) not in fake_files._store


async def test_delete_returns_false_when_missing(service: MetricService) -> None:
    assert await service.delete_metric("default", "nope") is False


async def test_delete_handles_concurrent_delete_race(service: MetricService) -> None:
    await service.create_metric("m", _bundle(), workspace="default")

    async def _already_deleted(*_args, **_kwargs):
        raise EntityNotFoundError("deleted concurrently")

    service.entity_client.delete = _already_deleted
    assert await service.delete_metric("default", "m") is False


async def test_list_returns_workspace_metrics(service: MetricService) -> None:
    await service.create_metric("a", _bundle(), workspace="default")
    await service.create_metric("b", _bundle(), workspace="default")

    page = await service.list_metrics("default")

    assert {m.name for m in page.data} == {"a", "b"}
    assert page.pagination is not None
    assert page.pagination.total_results == 2


# ---- derived metrics -------------------------------------------------------


async def test_store_derived_metric_names_by_digest_and_marks_derived(service: MetricService, fake_files) -> None:
    from nemo_evaluator.api.service.metric_service import _MAX_ENTITY_NAME_LENGTH

    ref = await service.store_derived_metric(_bundle(), workspace="default")

    workspace, _, name = ref.root.partition("/")
    assert workspace == "default"
    assert name.startswith("derived.")
    assert len(name) <= _MAX_ENTITY_NAME_LENGTH
    entity = service.entity_client.entities[("default", name)]
    assert entity.derived is True
    assert _fileset_of(service, entity.bundle_ref) in fake_files._store


async def test_store_derived_metric_distinguishes_full_contract(service: MetricService) -> None:
    bundle = _bundle()
    variant = bundle.model_copy(update={"metadata": bundle.metadata.model_copy(update={"description": "different"})})
    assert bundle.payload.digest == variant.payload.digest

    first = await service.store_derived_metric(bundle, workspace="default")
    second = await service.store_derived_metric(variant, workspace="default")

    assert first.root != second.root
    assert len(service.entity_client.entities) == 2


async def test_store_derived_metric_is_content_addressed_dedup(service: MetricService, fake_files) -> None:
    bundle = _bundle()

    first = await service.store_derived_metric(bundle, workspace="default")
    second = await service.store_derived_metric(bundle, workspace="default")

    assert first.root == second.root
    assert len(service.entity_client.entities) == 1
    assert len(fake_files._store) == 1


async def test_list_excludes_derived_by_default(service: MetricService) -> None:
    captured: list[object] = []
    original_list = service.entity_client.list

    async def _spy(entity_cls, *, filter_operation=None, **kwargs):
        captured.append(filter_operation)
        return await original_list(entity_cls, filter_operation=filter_operation, **kwargs)

    service.entity_client.list = _spy

    await service.list_metrics("default")
    await service.list_metrics("default", include_derived=True)

    assert captured[0] is not None
    assert captured[1] is None
