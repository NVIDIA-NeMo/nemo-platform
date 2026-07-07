# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CRUD service for persisted agent-eval task entities.

A task is stored whole in the entity store (its metrics — inline bundles and/or stored-metric refs —
live in the entity record; there's no separate Files payload, unlike a metric bundle). Stored
``TaskEntity`` rows are mapped to the :class:`Task` API DTO — like ``MetricService`` maps
``MetricBundleEntity`` to ``Metric`` — so the wire contract round-trips cleanly (an ``EntityBase``'s
``id``/``created_at`` are computed and don't deserialize from the entity's own serialized form).
"""

from __future__ import annotations

import logging

from nemo_evaluator.api.schemas import MetricInline, MetricRef, Task, TaskInput
from nemo_evaluator.api.service.metric_service import MetricService
from nemo_evaluator.entities import TaskEntity
from nemo_platform_plugin.entities import EntityClient, EntityConflictError, EntityNotFoundError, PaginationInfo
from nemo_platform_plugin.filter_ops import FilterOperation
from nemo_platform_plugin.log_utils import sanitize_for_log
from nemo_platform_plugin.schema import Page, PaginationData

logger = logging.getLogger(__name__)


def _entity_to_task(entity: TaskEntity) -> Task:
    """Map a stored task entity to its API DTO, guarding the persistence timestamps."""
    created_at = entity.created_at
    updated_at = entity.updated_at
    if created_at is None or updated_at is None:
        raise ValueError(f"Stored task '{entity.workspace}/{entity.name}' is missing persistence timestamps")
    return Task(
        id=entity.id,
        name=entity.name,
        workspace=entity.workspace,
        project=entity.project,
        intent=entity.intent,
        inputs=entity.inputs,
        metrics=entity.metrics,
        views=entity.views,
        metadata=entity.metadata,
        created_at=created_at,
        updated_at=updated_at,
    )


def _pagination(src: PaginationInfo, current_page_size: int) -> PaginationData:
    """Carry the entity-store pagination counts into the API ``Page`` envelope."""
    return PaginationData(
        page=src.page,
        page_size=src.page_size,
        current_page_size=current_page_size,
        total_pages=src.total_pages,
        total_results=src.total_results,
    )


class TaskService:
    """Create/get/list/delete for persisted agent-eval task entities, exposed as the ``Task`` DTO."""

    def __init__(self, entity_client: EntityClient, metric_service: MetricService):
        self.entity_client = entity_client
        self.metric_service = metric_service

    async def _normalize_metrics(self, metrics: list[MetricRef | MetricInline], *, workspace: str) -> list[MetricRef]:
        """Resolve a task's submitted metrics to references — inline metrics are stored as derived
        metrics (content-addressed, hidden from the listing) so a persisted task only ever holds refs."""
        refs: list[MetricRef] = []
        for metric in metrics:
            if isinstance(metric, MetricRef):
                refs.append(metric)
            else:
                refs.append(await self.metric_service.store_derived_metric(metric, workspace=workspace))
        return refs

    async def create_task(
        self, name: str, task_input: TaskInput, *, workspace: str, project: str | None = None
    ) -> Task:
        """Store a new task (addressed by workspace/name). Raises ``ValueError`` if it already exists."""
        entity = TaskEntity(
            name=name,
            workspace=workspace,
            project=project,
            intent=task_input.intent,
            inputs=task_input.inputs,
            metrics=await self._normalize_metrics(task_input.metrics, workspace=workspace),
            views=task_input.views,
            metadata=task_input.metadata,
        )
        try:
            created = await self.entity_client.create(entity)
        except EntityConflictError as exc:
            raise ValueError(f"Task '{workspace}/{name}' already exists") from exc
        logger.info(
            "Task created", extra={"workspace": sanitize_for_log(workspace), "task_name": sanitize_for_log(name)}
        )
        return _entity_to_task(created)

    async def get_task(self, workspace: str, name: str) -> Task | None:
        try:
            entity = await self.entity_client.get(TaskEntity, workspace=workspace, name=name)
        except EntityNotFoundError:
            return None
        return _entity_to_task(entity)

    async def list_tasks(
        self,
        *,
        workspace: str,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        filter_operation: FilterOperation | None = None,
    ) -> Page[Task]:
        result = await self.entity_client.list(
            TaskEntity,
            workspace=workspace,
            filter_operation=filter_operation,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        data = [_entity_to_task(entity) for entity in result.data]
        return Page(data=data, pagination=_pagination(result.pagination, len(data)), sort=sort, filter=None)

    async def delete_task(self, workspace: str, name: str) -> bool:
        """Delete a stored task; ``False`` if absent."""
        try:
            await self.entity_client.delete(TaskEntity, name, workspace=workspace)
        except EntityNotFoundError:
            return False
        logger.info(
            "Task deleted", extra={"workspace": sanitize_for_log(workspace), "task_name": sanitize_for_log(name)}
        )
        return True
