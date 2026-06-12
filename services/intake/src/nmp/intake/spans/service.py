# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Application service for Intake trace spans."""

from __future__ import annotations

from nmp.common.api.common import PaginatedResult
from nmp.intake.spans.annotations_repository import AnnotationsRepository
from nmp.intake.spans.domain import (
    Annotation,
    AnnotationListFilter,
    EvaluatorResult,
    EvaluatorResultListFilter,
    IntakeSpan,
    IntakeTrace,
    SpanGroup,
    SpanListFilter,
    TraceBatch,
    TraceListFilter,
    TraceMode,
)
from nmp.intake.spans.evaluator_results_repository import EvaluatorResultsRepository
from nmp.intake.spans.span_repository import SpanRepository
from nmp.intake.spans.trace_repository import TraceRepository


class SpanNotFoundError(Exception):
    def __init__(self, workspace: str, span_id: str) -> None:
        super().__init__(f"Span {workspace}/{span_id} not found")
        self.workspace = workspace
        self.span_id = span_id


class EvaluatorResultNotFoundError(Exception):
    def __init__(self, workspace: str, evaluator_result_id: str) -> None:
        super().__init__(f"Evaluator result {workspace}/{evaluator_result_id} not found")
        self.workspace = workspace
        self.evaluator_result_id = evaluator_result_id


class TraceNotFoundError(Exception):
    def __init__(self, workspace: str, trace_id: str) -> None:
        super().__init__(f"Trace {workspace}/{trace_id} not found")
        self.workspace = workspace
        self.trace_id = trace_id


class AnnotationNotFoundError(Exception):
    def __init__(self, workspace: str, annotation_id: str) -> None:
        super().__init__(f"Annotation {workspace}/{annotation_id} not found")
        self.workspace = workspace
        self.annotation_id = annotation_id


class IntakeSpansService:
    def __init__(
        self,
        span_repository: SpanRepository,
        trace_repository: TraceRepository,
        evaluator_results_repository: EvaluatorResultsRepository,
        annotations_repository: AnnotationsRepository,
    ) -> None:
        self._spans = span_repository
        self._traces = trace_repository
        self._evaluator_results = evaluator_results_repository
        self._annotations = annotations_repository

    async def ingest_batch(self, batch: TraceBatch) -> None:
        await self._spans.save_spans(batch.spans)
        if batch.evaluator_results:
            await self._evaluator_results.save_evaluator_results(batch.evaluator_results)

    async def list_spans(
        self,
        *,
        filters: SpanListFilter,
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[IntakeSpan]:
        return await self._spans.list_spans(filters=filters, page=page, page_size=page_size, sort=sort)

    async def list_span_groups(
        self,
        *,
        filters: SpanListFilter,
        group_by: list[str],
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[SpanGroup]:
        return await self._spans.list_span_groups(
            filters=filters,
            group_by=group_by,
            page=page,
            page_size=page_size,
            sort=sort,
        )

    async def get_span(self, *, workspace: str, span_id: str) -> IntakeSpan:
        span = await self._spans.get_span(workspace=workspace, span_id=span_id)
        if span is None:
            raise SpanNotFoundError(workspace, span_id)
        return span

    async def list_traces(
        self,
        *,
        filters: TraceListFilter,
        page: int,
        page_size: int,
        sort: str,
        mode: TraceMode,
    ) -> PaginatedResult[IntakeTrace]:
        return await self._traces.list_traces(filters=filters, page=page, page_size=page_size, sort=sort, mode=mode)

    async def get_trace(self, *, workspace: str, trace_id: str, mode: TraceMode) -> IntakeTrace:
        trace = await self._traces.get_trace(workspace=workspace, trace_id=trace_id, mode=mode)
        if trace is None:
            raise TraceNotFoundError(workspace, trace_id)
        return trace

    async def create_evaluator_result(self, result: EvaluatorResult) -> EvaluatorResult:
        """Persist one evaluator_result. Loose target — no span existence check."""

        await self._evaluator_results.save_evaluator_results([result])
        return result

    async def list_evaluator_results(
        self,
        *,
        filters: EvaluatorResultListFilter,
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[EvaluatorResult]:
        return await self._evaluator_results.list_evaluator_results(
            filters=filters, page=page, page_size=page_size, sort=sort
        )

    async def get_evaluator_result(self, *, workspace: str, evaluator_result_id: str) -> EvaluatorResult:
        result = await self._evaluator_results.get_evaluator_result(
            workspace=workspace, evaluator_result_id=evaluator_result_id
        )
        if result is None:
            raise EvaluatorResultNotFoundError(workspace, evaluator_result_id)
        return result

    async def list_evaluator_results_for_span(self, *, workspace: str, span_id: str) -> list[EvaluatorResult]:
        return await self._evaluator_results.list_evaluator_results_for_span(workspace=workspace, span_id=span_id)

    async def create_annotation(self, annotation: Annotation) -> Annotation:
        """Persist one annotation. Target validation is permissive — no span/session existence check."""

        await self._annotations.save_annotations([annotation])
        return annotation

    async def get_annotation(self, *, workspace: str, annotation_id: str) -> Annotation:
        annotation = await self._annotations.get_annotation(workspace=workspace, annotation_id=annotation_id)
        if annotation is None:
            raise AnnotationNotFoundError(workspace, annotation_id)
        return annotation

    async def list_annotations(
        self,
        *,
        filters: AnnotationListFilter,
        page: int,
        page_size: int,
        sort: str,
    ) -> PaginatedResult[Annotation]:
        return await self._annotations.list_annotations(filters=filters, page=page, page_size=page_size, sort=sort)

    async def delete_annotation(self, *, workspace: str, annotation_id: str) -> None:
        existing = await self._annotations.get_annotation(workspace=workspace, annotation_id=annotation_id)
        if existing is None:
            raise AnnotationNotFoundError(workspace, annotation_id)
        await self._annotations.soft_delete_annotation(annotation=existing)
