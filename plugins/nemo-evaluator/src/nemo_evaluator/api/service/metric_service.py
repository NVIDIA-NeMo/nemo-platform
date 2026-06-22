# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Service layer for stored metric operations.

Combines the Entity Store (the queryable index) with the Files service (the
canonical serialized bundle). The service owns the bundle's storage lifecycle.

Stored metrics are immutable: they can be created, read, listed, and deleted,
but not updated in place. Each bundle upload lands in its own uniquely-named
fileset, which makes every write/rollback target exactly one metric's bytes. As
a result no failure mode leaves a metric pointing at the wrong or missing data —
the worst case is an orphaned fileset (a storage leak), never a corrupted metric:

- create: upload first, then create the entity. On a name conflict (or any
  index failure) we delete the fileset we just created — never another
  metric's. The entity is only created once its bundle exists.
- delete: delete the entity first, then its fileset.
"""

from __future__ import annotations

import logging

from nemo_evaluator.api.schemas import (
    Metric,
    MetricInline,
)
from nemo_evaluator.entities import MetricBundleEntity
from nemo_evaluator.metric_storage import delete_bundle_by_ref, store_bundle
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundle as RuntimeMetricBundle
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.entities import (
    EntityClient,
    EntityConflictError,
    EntityNotFoundError,
)
from nemo_platform_plugin.filter_ops import FilterOperation
from nemo_platform_plugin.schema import Page, PaginationData

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: object) -> str:
    """Strip line-break/control characters to prevent log injection."""
    return str(value).replace("\r", "").replace("\n", "")


def _entity_to_schema(entity: MetricBundleEntity) -> Metric:
    """Convert a stored metric entity to its API representation."""
    created_at = entity.created_at
    updated_at = entity.updated_at
    if created_at is None or updated_at is None:
        raise ValueError(f"Stored metric '{entity.workspace}/{entity.name}' is missing persistence timestamps")
    return Metric(
        id=entity.id,
        name=entity.name,
        workspace=entity.workspace,
        project=entity.project,
        metric_type=entity.metric_type,
        description=entity.description,
        labels=entity.labels,
        outputs=entity.outputs,
        secrets=entity.secrets,
        payload_kind=entity.payload_kind,
        payload_digest=entity.payload_digest,
        bundle_ref=entity.bundle_ref,
        created_at=created_at,
        updated_at=updated_at,
    )


def _entity_from_bundle(
    *,
    name: str,
    workspace: str,
    bundle: RuntimeMetricBundle,
    bundle_ref: str,
    project: str | None,
) -> MetricBundleEntity:
    """Build a stored-metric entity from a bundle and its Files reference."""
    return MetricBundleEntity(
        name=name,
        workspace=workspace,
        project=project,
        metric_type=bundle.metric_type,
        description=bundle.metadata.description,
        labels=bundle.metadata.labels,
        outputs=bundle.outputs,
        secrets=bundle.secrets,
        payload_kind=bundle.payload.kind,
        payload_digest=bundle.payload.digest,
        bundle_ref=bundle_ref,
    )


class MetricService:
    """Service layer for stored metric CRUD."""

    def __init__(self, entity_client: EntityClient, sdk: AsyncNeMoPlatform):
        self.entity_client = entity_client
        self.sdk = sdk

    async def create_metric(
        self,
        name: str,
        metric: MetricInline,
        *,
        workspace: str,
        project: str | None = None,
    ) -> Metric:
        """Store a new metric (addressed by workspace/name): upload its bundle, then index it."""
        logger.debug(
            "Creating metric", extra={"workspace": _sanitize_for_log(workspace), "metric_name": _sanitize_for_log(name)}
        )

        # Cheap pre-check to avoid uploading a (potentially large) bundle we would
        # only discard. The entity create below remains the authoritative,
        # race-safe uniqueness guard.
        try:
            await self.entity_client.get(MetricBundleEntity, name=name, workspace=workspace)
            raise ValueError(f"Metric with name '{name}' already exists in workspace '{workspace}'")
        except EntityNotFoundError:
            pass

        # Convert the wire DTO into the runtime bundle (JSON round-trip keeps the
        # base64 payload handling consistent), then store/index it.
        runtime_bundle = RuntimeMetricBundle.model_validate_json(metric.model_dump_json())
        bundle_ref = await store_bundle(self.sdk, workspace, name, runtime_bundle)
        entity = _entity_from_bundle(
            name=name,
            workspace=workspace,
            bundle=runtime_bundle,
            bundle_ref=bundle_ref,
            project=project,
        )

        try:
            created = await self.entity_client.create(entity)
        except EntityConflictError as e:
            # We own this uniquely-named fileset and the entity was not created;
            # deleting it cannot affect the existing metric's data.
            await self._discard_bundle(bundle_ref)
            raise ValueError(f"Metric with name '{name}' already exists in workspace '{workspace}'") from e
        except Exception:
            await self._discard_bundle(bundle_ref)
            raise

        logger.info(
            "Metric created",
            extra={"workspace": _sanitize_for_log(created.workspace), "metric_name": _sanitize_for_log(created.name)},
        )
        return _entity_to_schema(created)

    async def get_metric(self, workspace: str, name: str) -> Metric | None:
        """Get a stored metric by workspace and name."""
        try:
            entity = await self.entity_client.get(MetricBundleEntity, workspace=workspace, name=name)
            return _entity_to_schema(entity)
        except EntityNotFoundError:
            return None

    async def list_metrics(
        self,
        workspace: str,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        filter_operation: FilterOperation | None = None,
    ) -> Page[Metric]:
        """List stored metrics with filtering and pagination."""
        result = await self.entity_client.list(
            MetricBundleEntity,
            workspace=workspace,
            filter_operation=filter_operation,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        metrics = [_entity_to_schema(entity) for entity in result.data]
        return Page(
            data=metrics,
            pagination=PaginationData(
                page=result.pagination.page,
                page_size=result.pagination.page_size,
                current_page_size=len(metrics),
                total_pages=result.pagination.total_pages,
                total_results=result.pagination.total_results,
            ),
            sort=sort,
            filter=None,
        )

    async def delete_metric(self, workspace: str, name: str) -> bool:
        """Delete a stored metric and its backing bundle. Returns False if not found."""
        try:
            entity = await self.entity_client.get(MetricBundleEntity, workspace=workspace, name=name)
        except EntityNotFoundError:
            return False

        try:
            await self.entity_client.delete(MetricBundleEntity, name, workspace=workspace)
        except EntityNotFoundError:
            # Lost a delete race: another request already removed it.
            return False
        await self._discard_bundle(entity.bundle_ref)
        logger.info(
            "Metric deleted", extra={"workspace": _sanitize_for_log(workspace), "metric_name": _sanitize_for_log(name)}
        )
        return True

    async def _discard_bundle(self, bundle_ref: str) -> None:
        """Delete an unreferenced bundle fileset.

        Safe by construction: every reference names a fileset created for a
        single metric version, so deleting it can only remove bytes nothing
        else points at. A failure here leaks that one fileset (logged) but never
        affects a live metric.
        """
        try:
            await delete_bundle_by_ref(self.sdk, bundle_ref)
        except Exception:
            logger.warning(
                "Failed to delete unreferenced metric bundle fileset; storage may be leaked",
                extra={"bundle_ref": _sanitize_for_log(bundle_ref)},
                exc_info=True,
            )
