# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed endpoint definitions for the Evaluator service.

Single source of truth for the HTTP contract. Replaces the hand-written
``nemo_evaluator.sdk`` resource layer's direct ``NeMoPlatform._client`` usage.

The evaluator's high-level ``submit()`` convenience method (with its overloaded
signatures for row vs. taskset evaluation) stays in the SDK layer — it packages
parameters into a job spec and calls ``submit_evaluate_job`` or
``submit_agent_eval_job`` here for the actual HTTP POST.
"""

from __future__ import annotations

from abc import abstractmethod

from nemo_platform_plugin.client.endpoint import delete, get, post
from nemo_platform_plugin.client.types import Paginated, PreparedRequest
from nemo_platform_plugin.evaluator.types import (
    AgentEvalResult,
    CreateMetricRequest,
    EvalResult,
    EvaluatorJobResponse,
    ListAgentEvalResultsQueryParams,
    ListEvalResultsQueryParams,
    ListMetricsQueryParams,
    MetricBundle,
    SubmitAgentEvalJobRequest,
    SubmitEvaluateJobRequest,
)

_EVAL_JOBS = "/apis/evaluator/v2/workspaces/{workspace}/evaluate/jobs"
_AGENT_EVAL_JOBS = "/apis/evaluator/v2/workspaces/{workspace}/agent-evaluate/jobs"
_EVAL_RESULTS = "/apis/evaluator/v2/workspaces/{workspace}/eval-results"
_AGENT_EVAL_RESULTS = "/apis/evaluator/v2/workspaces/{workspace}/agent-eval-results"
_METRICS = "/apis/evaluator/v2/workspaces/{workspace}/metrics"


# ---------------------------------------------------------------------------
# Job submission
# ---------------------------------------------------------------------------


@post(_EVAL_JOBS)
@abstractmethod
def submit_evaluate_job(*, workspace: str | None = None, body: SubmitEvaluateJobRequest) -> EvaluatorJobResponse: ...


@post(_AGENT_EVAL_JOBS)
@abstractmethod
def submit_agent_eval_job(*, workspace: str | None = None, body: SubmitAgentEvalJobRequest) -> EvaluatorJobResponse: ...


# ---------------------------------------------------------------------------
# Eval results
# ---------------------------------------------------------------------------


@get(f"{_EVAL_RESULTS}/{{name}}")
@abstractmethod
def get_eval_result(*, workspace: str | None = None, name: str) -> EvalResult: ...


@get(_EVAL_RESULTS)
@abstractmethod
def list_eval_results(
    *, workspace: str | None = None, query_params: ListEvalResultsQueryParams | None = None
) -> Paginated[EvalResult]: ...


# ---------------------------------------------------------------------------
# Agent eval results
# ---------------------------------------------------------------------------


@get(f"{_AGENT_EVAL_RESULTS}/{{name}}")
@abstractmethod
def get_agent_eval_result(*, workspace: str | None = None, name: str) -> AgentEvalResult: ...


@get(_AGENT_EVAL_RESULTS)
@abstractmethod
def list_agent_eval_results(
    *, workspace: str | None = None, query_params: ListAgentEvalResultsQueryParams | None = None
) -> Paginated[AgentEvalResult]: ...


@delete(f"{_AGENT_EVAL_RESULTS}/{{name}}")
@abstractmethod
def delete_agent_eval_result(*, workspace: str | None = None, name: str) -> None: ...


# ---------------------------------------------------------------------------
# Metrics CRUD
# ---------------------------------------------------------------------------


@get(f"{_METRICS}/{{name}}")
@abstractmethod
def get_metric(*, workspace: str | None = None, name: str) -> MetricBundle: ...


@get(_METRICS)
@abstractmethod
def list_metrics(
    *, workspace: str | None = None, query_params: ListMetricsQueryParams | None = None
) -> Paginated[MetricBundle]: ...


def _get_metric_on_conflict(body: CreateMetricRequest, workspace: str | None) -> PreparedRequest[MetricBundle]:
    return get_metric(name=body.name, workspace=workspace)


@post(_METRICS, get_on_conflict=_get_metric_on_conflict)
@abstractmethod
def create_metric(
    *, workspace: str | None = None, body: CreateMetricRequest, exist_ok: bool = False
) -> MetricBundle: ...


@delete(f"{_METRICS}/{{name}}")
@abstractmethod
def delete_metric(*, workspace: str | None = None, name: str) -> None: ...
