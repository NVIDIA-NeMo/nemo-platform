# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake evaluator_results storage."""

from typing import Any

from nmp.common.api.common import PaginatedResult
from nmp.intake.spans.clickhouse.dao import ClickHouseDao
from nmp.intake.spans.clickhouse.query import WhereBuilder, column, order_by_clause
from nmp.intake.spans.clickhouse_client import ClickHouseSpanClient
from nmp.intake.spans.domain import (
    EvaluatorResult,
    EvaluatorResultDataType,
    EvaluatorResultListFilter,
)
from nmp.intake.spans.storage import dict_to_row, make_pagination

EVALUATOR_RESULT_COLUMNS = [
    "evaluator_result_id",
    "span_id",
    "session_id",
    "workspace",
    "name",
    "value",
    "string_value",
    "data_type",
    "comment",
    "created_by",
    "created_at",
    "ingested_at",
]

EVALUATOR_RESULT_SORT_COLUMNS = {
    "created_at": "created_at",
    "value": "value",
}


class EvaluatorResultsRepository:
    def __init__(self, client: ClickHouseSpanClient) -> None:
        self._dao = ClickHouseDao(client)

    async def save_evaluator_results(self, results: list[EvaluatorResult]) -> None:
        if not results:
            return
        rows = [dict_to_row(_evaluator_result_to_row(result), EVALUATOR_RESULT_COLUMNS) for result in results]
        await self._dao.insert_rows("evaluator_results", rows, column_names=EVALUATOR_RESULT_COLUMNS)

    async def get_evaluator_result(self, *, workspace: str, evaluator_result_id: str) -> EvaluatorResult | None:
        where = (
            WhereBuilder()
            .eq(column("workspace"), "workspace", workspace)
            .eq(column("evaluator_result_id"), "evaluator_result_id", evaluator_result_id)
        )
        row = await self._dao.fetch_one(self._dao.table("evaluator_results"), where, final=True)
        if row is None:
            return None
        return _row_to_evaluator_result(row)

    async def list_evaluator_results(
        self,
        *,
        filters: EvaluatorResultListFilter,
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[EvaluatorResult]:
        rows, total_results = await self._dao.paginate(
            table=self._dao.table("evaluator_results"),
            where=_evaluator_result_where(filters),
            sort=sort,
            sort_columns=EVALUATOR_RESULT_SORT_COLUMNS,
            tiebreaker="evaluator_result_id",
            sort_label="evaluator_result",
            page=page,
            page_size=page_size,
            final=True,
        )
        results = [_row_to_evaluator_result(row) for row in rows]
        return PaginatedResult(
            data=results,
            pagination=make_pagination(
                page=page, page_size=page_size, current_page_size=len(results), total_results=total_results
            ),
        )

    async def list_evaluator_results_for_span(self, *, workspace: str, span_id: str) -> list[EvaluatorResult]:
        where = WhereBuilder().eq(column("workspace"), "workspace", workspace).eq(column("span_id"), "span_id", span_id)
        rows = await self._dao.fetch_all(
            self._dao.table("evaluator_results"),
            where,
            order_by="created_at ASC, evaluator_result_id ASC",
            final=True,
        )
        return [_row_to_evaluator_result(row) for row in rows]


def _evaluator_result_where(filters: EvaluatorResultListFilter) -> WhereBuilder:
    where = WhereBuilder().eq(column("workspace"), "workspace", filters.workspace)
    if filters.span_id is not None:
        where.eq(column("span_id"), "span_id", filters.span_id)
    if filters.session_id is not None:
        where.eq(column("session_id"), "session_id", filters.session_id)
    if filters.name is not None:
        where.eq(column("name"), "name", filters.name)
    if filters.data_type is not None:
        where.eq(column("data_type"), "data_type", filters.data_type.value)
    if filters.created_by is not None:
        where.eq(column("created_by"), "created_by", filters.created_by)
    if filters.value_gte is not None:
        where.gte(column("value"), "value_gte", filters.value_gte)
    if filters.value_lte is not None:
        where.lte(column("value"), "value_lte", filters.value_lte)
    if filters.created_at_gte is not None:
        where.gte(column("created_at"), "created_at_gte", filters.created_at_gte)
    if filters.created_at_lte is not None:
        where.lte(column("created_at"), "created_at_lte", filters.created_at_lte)
    return where


def _evaluator_result_order_by(sort: str) -> str:
    return order_by_clause(
        sort,
        sort_columns=EVALUATOR_RESULT_SORT_COLUMNS,
        tiebreaker="evaluator_result_id",
        label="evaluator_result",
    )


def _evaluator_result_to_row(result: EvaluatorResult) -> dict[str, Any]:
    return {
        "evaluator_result_id": result.evaluator_result_id,
        "span_id": result.span_id,
        "session_id": result.session_id,
        "workspace": result.workspace,
        "name": result.name,
        "value": result.value,
        "string_value": result.string_value,
        "data_type": result.data_type.value,
        "comment": result.comment,
        "created_by": result.created_by,
        "created_at": result.created_at,
        "ingested_at": result.ingested_at,
    }


def _row_to_evaluator_result(row: dict[str, Any]) -> EvaluatorResult:
    return EvaluatorResult(
        evaluator_result_id=row["evaluator_result_id"],
        span_id=row["span_id"],
        session_id=row["session_id"],
        workspace=row["workspace"],
        name=row["name"],
        value=row.get("value"),
        string_value=row.get("string_value"),
        data_type=EvaluatorResultDataType(row["data_type"]),
        comment=row.get("comment"),
        created_by=row.get("created_by"),
        created_at=row["created_at"],
        ingested_at=row["ingested_at"],
    )
