# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the Evaluator service.

Wraps the endpoint functions from ``evaluator.endpoints`` as direct methods
using the ``method()`` descriptor, following the files/models pattern.

The evaluator's high-level ``submit()`` convenience method (overloaded for row
vs. taskset evaluation) stays in the SDK layer — it packages parameters into a
job spec and calls ``submit_evaluate_job`` / ``submit_agent_eval_job`` here.
"""

from dataclasses import replace

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.client.response import NemoResponse
from nemo_platform_plugin.client.types import PreparedRequest
from nemo_platform_plugin.evaluator import endpoints
from nemo_platform_plugin.evaluator.types import CreateMetricRequest, FlatQueryParams, Metric, ProjectQueryParams


def _create_metric_request(
    *,
    workspace: str | None,
    name: str,
    body: CreateMetricRequest,
    query_params: ProjectQueryParams | FlatQueryParams | None,
    exist_ok: bool,
) -> PreparedRequest[Metric]:
    request = endpoints.create_metric(workspace=workspace, name=name, body=body, query_params=query_params)
    if not exist_ok:
        return request
    return replace(
        request,
        client_options={"exist_ok": True},
        on_conflict_get=endpoints.get_metric(workspace=workspace, name=name),
    )


class _EvaluatorMethods:
    get_health = method(endpoints.get_health)

    list_evaluate_jobs = method(endpoints.list_evaluate_jobs)
    submit_evaluate_job = method(endpoints.submit_evaluate_job)
    get_evaluate_job = method(endpoints.get_evaluate_job)
    get_evaluate_job_status = method(endpoints.get_evaluate_job_status)
    download_evaluate_job_aggregate_scores = method(endpoints.download_evaluate_job_aggregate_scores)
    download_evaluate_job_row_scores = method(endpoints.download_evaluate_job_row_scores)
    download_evaluate_job_artifacts = method(endpoints.download_evaluate_job_artifacts)

    list_agent_eval_jobs = method(endpoints.list_agent_eval_jobs)
    submit_agent_eval_job = method(endpoints.submit_agent_eval_job)
    get_agent_eval_job = method(endpoints.get_agent_eval_job)
    get_agent_eval_job_status = method(endpoints.get_agent_eval_job_status)

    get_metric = method(endpoints.get_metric)
    list_metrics = method(endpoints.list_metrics)
    delete_metric = method(endpoints.delete_metric)

    get_task = method(endpoints.get_task)
    list_tasks = method(endpoints.list_tasks)
    create_task = method(endpoints.create_task)
    replace_task = method(endpoints.replace_task)
    list_task_revisions = method(endpoints.list_task_revisions)
    get_task_revision = method(endpoints.get_task_revision)
    tag_task_revision = method(endpoints.tag_task_revision)
    delete_task = method(endpoints.delete_task)

    get_taskset = method(endpoints.get_taskset)
    list_tasksets = method(endpoints.list_tasksets)
    create_taskset = method(endpoints.create_taskset)
    replace_taskset = method(endpoints.replace_taskset)
    list_taskset_revisions = method(endpoints.list_taskset_revisions)
    get_taskset_revision = method(endpoints.get_taskset_revision)
    tag_taskset_revision = method(endpoints.tag_taskset_revision)
    delete_taskset = method(endpoints.delete_taskset)

    get_eval_result = method(endpoints.get_eval_result)
    list_eval_results = method(endpoints.list_eval_results)
    delete_eval_result = method(endpoints.delete_eval_result)
    get_agent_eval_result = method(endpoints.get_agent_eval_result)
    list_agent_eval_results = method(endpoints.list_agent_eval_results)
    delete_agent_eval_result = method(endpoints.delete_agent_eval_result)


class EvaluatorClient(_EvaluatorMethods, NemoClient):
    """Sync client for the Evaluator service API."""

    def create_metric(
        self,
        *,
        workspace: str | None = None,
        name: str,
        body: CreateMetricRequest,
        query_params: ProjectQueryParams | FlatQueryParams | None = None,
        exist_ok: bool = False,
    ) -> NemoResponse[Metric]:
        return self.send(
            _create_metric_request(
                workspace=workspace,
                name=name,
                body=body,
                query_params=query_params,
                exist_ok=exist_ok,
            )
        )


class AsyncEvaluatorClient(_EvaluatorMethods, AsyncNemoClient):
    """Async client for the Evaluator service API."""

    async def create_metric(
        self,
        *,
        workspace: str | None = None,
        name: str,
        body: CreateMetricRequest,
        query_params: ProjectQueryParams | FlatQueryParams | None = None,
        exist_ok: bool = False,
    ) -> NemoResponse[Metric]:
        return await self.send(
            _create_metric_request(
                workspace=workspace,
                name=name,
                body=body,
                query_params=query_params,
                exist_ok=exist_ok,
            )
        )
