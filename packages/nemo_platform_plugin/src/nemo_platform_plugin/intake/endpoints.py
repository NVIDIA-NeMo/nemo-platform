# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the Intake APIs used by evaluator."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterable, Iterable

from nemo_platform_plugin.client.endpoint import get, patch, post
from nemo_platform_plugin.client.types import Paginated, PreparedRequest
from nemo_platform_plugin.intake.types import (
    AtifCreateRequest,
    EvaluationPatchRequest,
    EvaluationResponse,
    EvaluatorResult,
    EvaluatorResultCreateRequest,
    IngestResponse,
    ListEvaluatorResultsQueryParams,
    ListTracesQueryParams,
    Trace,
)

_INTAKE_BASE = "/apis/intake/v2/workspaces/{workspace}"


@post(f"{_INTAKE_BASE}/ingest/atif")
@abstractmethod
def create_atif(*, workspace: str | None = None, body: AtifCreateRequest) -> None: ...


def create_otlp_traces(
    *,
    workspace: str | None = None,
    content: bytes | Iterable[bytes] | AsyncIterable[bytes],
) -> PreparedRequest[IngestResponse]:
    return PreparedRequest(
        path_template=f"{_INTAKE_BASE}/ingest/otlp/v1/traces",
        path_params={} if workspace is None else {"workspace": workspace},
        method="POST",
        content=content,
        content_type="application/x-protobuf",
        response_type=IngestResponse,
    )


@get(f"{_INTAKE_BASE}/traces")
@abstractmethod
def list_traces(
    *,
    workspace: str | None = None,
    query_params: ListTracesQueryParams | None = None,
) -> Paginated[Trace]: ...


@post(f"{_INTAKE_BASE}/evaluator-results")
@abstractmethod
def create_evaluator_result(
    *,
    workspace: str | None = None,
    body: EvaluatorResultCreateRequest,
) -> EvaluatorResult: ...


@get(f"{_INTAKE_BASE}/evaluations/{{name}}")
@abstractmethod
def get_evaluation(*, workspace: str | None = None, name: str) -> EvaluationResponse: ...


@patch(f"{_INTAKE_BASE}/evaluations/{{name}}")
@abstractmethod
def patch_evaluation(
    *,
    workspace: str | None = None,
    name: str,
    body: EvaluationPatchRequest,
) -> EvaluationResponse: ...


@get(f"{_INTAKE_BASE}/evaluator-results")
@abstractmethod
def list_evaluator_results(
    *,
    workspace: str | None = None,
    query_params: ListEvaluatorResultsQueryParams | None = None,
) -> Paginated[EvaluatorResult]: ...


@get(f"{_INTAKE_BASE}/spans/{{span_id}}/evaluator-results")
@abstractmethod
def list_evaluator_results_for_span(*, workspace: str | None = None, span_id: str) -> list[EvaluatorResult]: ...
