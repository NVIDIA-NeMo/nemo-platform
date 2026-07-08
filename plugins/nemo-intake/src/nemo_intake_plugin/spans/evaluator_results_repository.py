# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse implementation of Intake evaluator_results storage."""

from typing import Any

from nemo_intake_plugin.spans.clickhouse_client import ClickHouseSpanClient
from nemo_intake_plugin.spans.domain import (
    EvaluatorResult,
    EvaluatorResultDataType,
    EvaluatorResultListFilter,
)
from nemo_intake_plugin.spans.storage import dict_to_row, make_pagination, result_rows
from nmp.common.api.common import PaginatedResult

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
        self._client = client

    async def save_evaluator_results(self, results: list[EvaluatorResult]) -> None:
        if not results:
            return
        rows = [dict_to_row(_evaluator_result_to_row(result), EVALUATOR_RESULT_COLUMNS) for result in results]
        await self._client.insert("evaluator_results", rows, column_names=EVALUATOR_RESULT_COLUMNS)

    async def get_evaluator_result(self, *, workspace: str, evaluator_result_id: str) -> EvaluatorResult | None:
        result = await self._client.query(
            f"""
            SELECT *
            FROM {self._client.table("evaluator_results")} FINAL
            WHERE workspace = %(workspace)s AND evaluator_result_id = %(evaluator_result_id)s
            LIMIT 1
            """,
            parameters={"workspace": workspace, "evaluator_result_id": evaluator_result_id},
        )
        rows = result_rows(result)
        if not rows:
            return None
        return _row_to_evaluator_result(rows[0])

    async def list_evaluator_results(
        self,
        *,
        filters: EvaluatorResultListFilter,
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[EvaluatorResult]:
        where_sql, parameters = _evaluator_result_where(filters)
        table = self._client.table("evaluator_results")
        total_result = await self._client.query(
            f"SELECT count() FROM {table} FINAL WHERE {where_sql}", parameters=parameters
        )
        total_results = int(total_result.result_rows[0][0])
        offset = (page - 1) * page_size
        rows_result = await self._client.query(
            f"""
            SELECT *
            FROM {table} FINAL
            WHERE {where_sql}
            ORDER BY {_evaluator_result_order_by(sort)}
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            parameters={**parameters, "limit": page_size, "offset": offset},
        )
        results = [_row_to_evaluator_result(row) for row in result_rows(rows_result)]
        return PaginatedResult(
            data=results,
            pagination=make_pagination(
                page=page, page_size=page_size, current_page_size=len(results), total_results=total_results
            ),
        )

    async def list_evaluator_results_for_span(self, *, workspace: str, span_id: str) -> list[EvaluatorResult]:
        result = await self._client.query(
            f"""
            SELECT *
            FROM {self._client.table("evaluator_results")} FINAL
            WHERE workspace = %(workspace)s AND span_id = %(span_id)s
            ORDER BY created_at ASC, evaluator_result_id ASC
            """,
            parameters={"workspace": workspace, "span_id": span_id},
        )
        return [_row_to_evaluator_result(row) for row in result_rows(result)]


def _evaluator_result_where(filters: EvaluatorResultListFilter) -> tuple[str, dict[str, Any]]:
    clauses = ["workspace = %(workspace)s"]
    parameters: dict[str, Any] = {"workspace": filters.workspace}
    if filters.span_id is not None:
        clauses.append("span_id = %(span_id)s")
        parameters["span_id"] = filters.span_id
    if filters.session_id is not None:
        clauses.append("session_id = %(session_id)s")
        parameters["session_id"] = filters.session_id
    if filters.name is not None:
        clauses.append("name = %(name)s")
        parameters["name"] = filters.name
    if filters.data_type is not None:
        clauses.append("data_type = %(data_type)s")
        parameters["data_type"] = filters.data_type.value
    if filters.created_by is not None:
        clauses.append("created_by = %(created_by)s")
        parameters["created_by"] = filters.created_by
    if filters.value_gte is not None:
        clauses.append("value >= %(value_gte)s")
        parameters["value_gte"] = filters.value_gte
    if filters.value_lte is not None:
        clauses.append("value <= %(value_lte)s")
        parameters["value_lte"] = filters.value_lte
    if filters.created_at_gte is not None:
        clauses.append("created_at >= %(created_at_gte)s")
        parameters["created_at_gte"] = filters.created_at_gte
    if filters.created_at_lte is not None:
        clauses.append("created_at <= %(created_at_lte)s")
        parameters["created_at_lte"] = filters.created_at_lte
    return " AND ".join(clauses), parameters


def _evaluator_result_order_by(sort: str) -> str:
    direction = "DESC" if sort.startswith("-") else "ASC"
    field = sort.removeprefix("-")
    column = EVALUATOR_RESULT_SORT_COLUMNS.get(field)
    if column is None:
        raise ValueError(f"Unsupported evaluator_result sort field: {field}")
    return f"{column} {direction}, evaluator_result_id ASC"


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
