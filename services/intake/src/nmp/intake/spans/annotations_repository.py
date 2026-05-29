# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake annotation storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from nmp.common.api.common import PaginatedResult
from nmp.intake.spans.clickhouse.dao import ClickHouseDao
from nmp.intake.spans.clickhouse.filters import annotation_list_where, annotation_lookup_where
from nmp.intake.spans.clickhouse.query import SortSpec, order_by_clause
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import Annotation, AnnotationKind, AnnotationListFilter
from nmp.intake.spans.storage import dict_to_row, make_pagination

ANNOTATION_COLUMNS = [
    "annotation_id",
    "workspace",
    "span_id",
    "session_id",
    "kind",
    "name",
    "value_text",
    "value_numeric",
    "text",
    "metadata",
    "created_by",
    "created_at",
    "ingested_at",
    "is_deleted",
]

ANNOTATION_SORT = SortSpec(columns={"created_at": "created_at"}, tiebreaker="annotation_id", label="annotation")


class AnnotationsRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._dao = ClickHouseDao(client)

    async def save_annotations(self, annotations: list[Annotation]) -> None:
        if not annotations:
            return
        rows = [dict_to_row(_annotation_to_row(item), ANNOTATION_COLUMNS) for item in annotations]
        await self._dao.insert_rows("annotations", rows, column_names=ANNOTATION_COLUMNS)

    async def get_annotation(self, *, workspace: str, annotation_id: str) -> Annotation | None:
        row = await self._dao.fetch_one(
            self._dao.table("annotations"),
            annotation_lookup_where(workspace=workspace, annotation_id=annotation_id),
            final=True,
        )
        if row is None:
            return None
        return _row_to_annotation(row)

    async def list_annotations(
        self,
        *,
        filters: AnnotationListFilter,
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[Annotation]:
        rows, total_results = await self._dao.paginate(
            table=self._dao.table("annotations"),
            where=annotation_list_where(filters),
            sort=sort,
            sort_spec=ANNOTATION_SORT,
            page=page,
            page_size=page_size,
            final=True,
        )
        annotations = [_row_to_annotation(row) for row in rows]
        return PaginatedResult(
            data=annotations,
            pagination=make_pagination(
                page=page,
                page_size=page_size,
                current_page_size=len(annotations),
                total_results=total_results,
            ),
        )

    async def soft_delete_annotation(self, *, annotation: Annotation) -> None:
        """Tombstone the annotation_id by writing a new row with is_deleted=1.

        The tombstone uses a fresh `ingested_at` so the ReplacingMergeTree
        version column strictly exceeds the live row and the deletion wins
        on next merge. `FINAL` reads filter out tombstoned rows.
        """

        row = _annotation_to_row(annotation, is_deleted=True)
        row["ingested_at"] = datetime.now(timezone.utc)
        rows = [dict_to_row(row, ANNOTATION_COLUMNS)]
        await self._dao.insert_rows("annotations", rows, column_names=ANNOTATION_COLUMNS)


def _annotation_order_by(sort: str) -> str:
    return order_by_clause(sort, ANNOTATION_SORT)


def _annotation_to_row(annotation: Annotation, *, is_deleted: bool = False) -> dict[str, Any]:
    return {
        "annotation_id": annotation.annotation_id,
        "workspace": annotation.workspace,
        # span_id stored as empty string when absent (matches `external_parent_span_id` convention).
        "span_id": annotation.span_id or "",
        "session_id": annotation.session_id,
        "kind": annotation.kind.value,
        "name": annotation.name,
        "value_text": annotation.value_text,
        "value_numeric": annotation.value_numeric,
        "text": annotation.text,
        "metadata": json.dumps(annotation.metadata) if annotation.metadata is not None else None,
        "created_by": annotation.created_by,
        "created_at": annotation.created_at,
        "ingested_at": annotation.ingested_at,
        "is_deleted": 1 if is_deleted else 0,
    }


def _row_to_annotation(row: dict[str, Any]) -> Annotation:
    metadata_raw = row.get("metadata")
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) and metadata_raw else None
    span_id_raw = row.get("span_id")
    span_id = span_id_raw if isinstance(span_id_raw, str) and span_id_raw else None
    return Annotation(
        annotation_id=row["annotation_id"],
        workspace=row["workspace"],
        span_id=span_id,
        session_id=row["session_id"],
        kind=AnnotationKind(row["kind"]),
        name=row.get("name"),
        value_text=row.get("value_text"),
        value_numeric=row.get("value_numeric"),
        text=row.get("text"),
        metadata=metadata,
        created_by=row.get("created_by"),
        created_at=row["created_at"],
        ingested_at=row["ingested_at"],
    )
