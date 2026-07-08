# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP contract used by Intake's Python client."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, NotRequired, TypedDict

from nemo_intake_plugin.api.v2.experiments.schemas import (
    ExperimentGroupRequest,
    ExperimentGroupResponse,
    ExperimentRequest,
    ExperimentResponse,
)
from nemo_intake_plugin.spans.api.evaluator_results_schemas import EvaluatorResult, EvaluatorResultInput
from nemo_intake_plugin.spans.api.traces_schemas import Trace
from nemo_intake_plugin.spans.ingest.atif import AtifIngestRequest
from nemo_platform_plugin.client.endpoint import get, post
from nemo_platform_plugin.client.types import Paginated, PreparedRequest
from pydantic import RootModel


class TraceListQueryParams(TypedDict, total=False):
    filter: NotRequired[dict[str, Any]]
    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    mode: NotRequired[str]


class EvaluatorResultList(RootModel[list[EvaluatorResult]]):
    """Non-paginated evaluator results attached to one span."""


@post("/apis/intake/v2/workspaces/{workspace}/ingest/atif")
@abstractmethod
def create_atif(*, workspace: str | None = None, body: AtifIngestRequest) -> None: ...


@post("/apis/intake/v2/workspaces/{workspace}/evaluator-results")
@abstractmethod
def create_evaluator_result(*, workspace: str | None = None, body: EvaluatorResultInput) -> EvaluatorResult: ...


@get("/apis/intake/v2/workspaces/{workspace}/traces")
@abstractmethod
def list_traces(
    *, workspace: str | None = None, query_params: TraceListQueryParams | None = None
) -> Paginated[Trace]: ...


@get("/apis/intake/v2/workspaces/{workspace}/spans/{span_id}/evaluator-results")
@abstractmethod
def list_span_evaluator_results(*, workspace: str | None = None, span_id: str) -> EvaluatorResultList: ...


@get("/apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}")
@abstractmethod
def get_experiment_group(*, workspace: str | None = None, name: str) -> ExperimentGroupResponse: ...


def _get_experiment_group_on_conflict(
    body: ExperimentGroupRequest, workspace: str | None
) -> PreparedRequest[ExperimentGroupResponse]:
    return get_experiment_group(workspace=workspace, name=body.name)


@post(
    "/apis/intake/v2/workspaces/{workspace}/experiment-groups",
    get_on_conflict=_get_experiment_group_on_conflict,
)
@abstractmethod
def create_experiment_group(
    *, workspace: str | None = None, body: ExperimentGroupRequest, exist_ok: bool = False
) -> ExperimentGroupResponse: ...


@get("/apis/intake/v2/workspaces/{workspace}/experiments/{name}")
@abstractmethod
def get_experiment(*, workspace: str | None = None, name: str) -> ExperimentResponse: ...


def _get_experiment_on_conflict(body: ExperimentRequest, workspace: str | None) -> PreparedRequest[ExperimentResponse]:
    return get_experiment(workspace=workspace, name=body.name)


@post(
    "/apis/intake/v2/workspaces/{workspace}/experiments",
    get_on_conflict=_get_experiment_on_conflict,
)
@abstractmethod
def create_experiment(
    *, workspace: str | None = None, body: ExperimentRequest, exist_ok: bool = False
) -> ExperimentResponse: ...
