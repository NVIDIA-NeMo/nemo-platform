# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import get_args, get_origin

from nemo_platform_plugin.client.types import BinaryContent, Paginated, PreparedRequest
from nemo_platform_plugin.evaluator import endpoints
from nemo_platform_plugin.evaluator.types import (
    AgentEvalJob,
    AgentEvalResult,
    CreateMetricRequest,
    CreateTaskRequest,
    CreateTasksetRequest,
    EvalResult,
    EvaluateJob,
    EvaluatorHealth,
    Metric,
    ReplaceTaskRequest,
    ReplaceTasksetRequest,
    Revision,
    SubmitAgentEvalJobRequest,
    SubmitEvaluateJobRequest,
    Task,
    Taskset,
)
from nemo_platform_plugin.jobs.schemas import PlatformJobStatusResponse


def _assert_paginated_model(response_type: object, model_type: type[object]) -> None:
    assert get_origin(response_type) is Paginated
    assert get_args(response_type)[0] is model_type


def test_submit_evaluate_job_endpoint_shape() -> None:
    body = SubmitEvaluateJobRequest(spec={"metrics": [], "dataset": []})
    prepared = endpoints.submit_evaluate_job(workspace="team-a", body=body)

    assert isinstance(prepared, PreparedRequest)
    assert prepared.method == "POST"
    assert prepared.path_template == "/apis/evaluator/v2/workspaces/{workspace}/evaluate/jobs"
    assert prepared.path_params == {"workspace": "team-a"}
    assert isinstance(prepared.content, bytes)
    assert json.loads(prepared.content) == {"spec": {"metrics": [], "dataset": []}}
    assert prepared.content_type == "application/json"
    assert prepared.response_type is EvaluateJob


def test_submit_agent_eval_job_endpoint_shape() -> None:
    prepared = endpoints.submit_agent_eval_job(
        workspace="team-a",
        body=SubmitAgentEvalJobRequest(spec={"tasks": "default/suite", "target": {"kind": "gym"}}),
    )

    assert prepared.method == "POST"
    assert prepared.path_template == "/apis/evaluator/v2/workspaces/{workspace}/agent-evaluate/jobs"
    assert prepared.path_params == {"workspace": "team-a"}
    assert prepared.response_type is AgentEvalJob


def test_health_endpoint_shape() -> None:
    prepared = endpoints.get_health()

    assert prepared.method == "GET"
    assert prepared.path_template == "/apis/evaluator/v1/healthz"
    assert prepared.path_params == {}
    assert prepared.response_type is EvaluatorHealth


def test_evaluate_job_and_download_endpoint_shapes() -> None:
    job = endpoints.get_evaluate_job(workspace="team-a", name="job-1")
    jobs = endpoints.list_evaluate_jobs(workspace="team-a")
    status = endpoints.get_evaluate_job_status(workspace="team-a", name="job-1")
    aggregate = endpoints.download_evaluate_job_aggregate_scores(workspace="team-a", name="job-1")
    row_scores = endpoints.download_evaluate_job_row_scores(workspace="team-a", name="job-1")
    artifacts = endpoints.download_evaluate_job_artifacts(workspace="team-a", name="job-1")

    assert job.method == "GET"
    assert job.path_template == "/apis/evaluator/v2/workspaces/{workspace}/evaluate/jobs/{name}"
    assert job.path_params == {"workspace": "team-a", "name": "job-1"}
    assert job.response_type is EvaluateJob
    _assert_paginated_model(jobs.response_type, EvaluateJob)
    assert status.path_template.endswith("/evaluate/jobs/{name}/status")
    assert status.response_type is PlatformJobStatusResponse
    assert aggregate.response_type is BinaryContent
    assert row_scores.response_type is BinaryContent
    assert artifacts.response_type is BinaryContent


def test_agent_eval_job_endpoint_shapes() -> None:
    job = endpoints.get_agent_eval_job(workspace="team-a", name="job-1")
    jobs = endpoints.list_agent_eval_jobs(workspace="team-a")
    status = endpoints.get_agent_eval_job_status(workspace="team-a", name="job-1")

    assert job.method == "GET"
    assert job.path_template == "/apis/evaluator/v2/workspaces/{workspace}/agent-evaluate/jobs/{name}"
    assert job.path_params == {"workspace": "team-a", "name": "job-1"}
    assert job.response_type is AgentEvalJob
    _assert_paginated_model(jobs.response_type, AgentEvalJob)
    assert status.path_template.endswith("/agent-evaluate/jobs/{name}/status")
    assert status.response_type is PlatformJobStatusResponse


def test_metric_endpoint_shapes() -> None:
    body = CreateMetricRequest(root={"type": "exact-match"})
    metric_create = endpoints.create_metric(
        workspace="team-a",
        name="accuracy",
        body=body,
        query_params={"project": "proj-a"},
    )

    assert metric_create.method == "POST"
    assert metric_create.path_template == "/apis/evaluator/v2/workspaces/{workspace}/metrics/{name}"
    assert metric_create.path_params == {"workspace": "team-a", "name": "accuracy"}
    assert metric_create.query_params == {"project": "proj-a"}
    assert isinstance(metric_create.content, bytes)
    assert json.loads(metric_create.content) == {"type": "exact-match"}
    assert metric_create.response_type is Metric
    assert metric_create.client_options is None
    assert metric_create.on_conflict_get is None
    _assert_paginated_model(endpoints.list_metrics(workspace="team-a").response_type, Metric)
    assert endpoints.get_metric(workspace="team-a", name="accuracy").response_type is Metric
    assert endpoints.delete_metric(workspace="team-a", name="accuracy").response_type is None


def test_task_endpoint_shapes() -> None:
    created = endpoints.create_task(
        workspace="team-a",
        name="task-1",
        body=CreateTaskRequest(root={"metrics": []}),
        query_params={"project": "proj-a"},
    )
    replaced = endpoints.replace_task(
        workspace="team-a",
        name="task-1",
        body=ReplaceTaskRequest(root={"metrics": []}),
    )
    revisions = endpoints.list_task_revisions(workspace="team-a", name="task-1", query_params={"page": 2})
    revision = endpoints.get_task_revision(workspace="team-a", name="task-1", revision="sha")
    tagged = endpoints.tag_task_revision(
        workspace="team-a",
        name="task-1",
        tag="prod",
        query_params={"revision": "sha"},
    )

    assert created.method == "POST"
    assert created.path_template == "/apis/evaluator/v2/workspaces/{workspace}/tasks/{name}"
    assert created.query_params == {"project": "proj-a"}
    assert created.response_type is Task
    assert replaced.method == "PUT"
    assert replaced.response_type is Task
    assert endpoints.get_task(workspace="team-a", name="task-1").response_type is Task
    _assert_paginated_model(endpoints.list_tasks(workspace="team-a").response_type, Task)
    _assert_paginated_model(revisions.response_type, Revision)
    assert revision.path_template.endswith("/tasks/{name}/revisions/{revision}")
    assert revision.response_type is Task
    assert tagged.path_template.endswith("/tasks/{name}/tags/{tag}")
    assert tagged.query_params == {"revision": "sha"}
    assert endpoints.delete_task(workspace="team-a", name="task-1").response_type is None


def test_taskset_endpoint_shapes() -> None:
    created = endpoints.create_taskset(
        workspace="team-a",
        name="suite",
        body=CreateTasksetRequest(root={"tasks": []}),
    )
    replaced = endpoints.replace_taskset(
        workspace="team-a",
        name="suite",
        body=ReplaceTasksetRequest(root={"tasks": []}),
        query_params={"project": "proj-a"},
    )
    revisions = endpoints.list_taskset_revisions(workspace="team-a", name="suite")
    revision = endpoints.get_taskset_revision(workspace="team-a", name="suite", revision="sha")
    tagged = endpoints.tag_taskset_revision(
        workspace="team-a",
        name="suite",
        tag="prod",
        query_params={"revision": "sha"},
    )

    assert created.method == "POST"
    assert created.path_template == "/apis/evaluator/v2/workspaces/{workspace}/tasksets/{name}"
    assert created.response_type is Taskset
    assert replaced.method == "PUT"
    assert replaced.query_params == {"project": "proj-a"}
    assert replaced.response_type is Taskset
    assert endpoints.get_taskset(workspace="team-a", name="suite").response_type is Taskset
    _assert_paginated_model(endpoints.list_tasksets(workspace="team-a").response_type, Taskset)
    _assert_paginated_model(revisions.response_type, Revision)
    assert revision.path_template.endswith("/tasksets/{name}/revisions/{revision}")
    assert revision.response_type is Taskset
    assert tagged.path_template.endswith("/tasksets/{name}/tags/{tag}")
    assert endpoints.delete_taskset(workspace="team-a", name="suite").response_type is None


def test_result_endpoint_shapes() -> None:
    eval_result = endpoints.get_eval_result(workspace="team-a", name="result-1")
    eval_results = endpoints.list_eval_results(workspace="team-a", query_params={"page": 2})
    agent_result = endpoints.get_agent_eval_result(workspace="team-a", name="result-1")
    agent_results = endpoints.list_agent_eval_results(workspace="team-a", query_params={"sort": "-created_at"})

    assert eval_result.response_type is EvalResult
    _assert_paginated_model(eval_results.response_type, EvalResult)
    assert endpoints.delete_eval_result(workspace="team-a", name="result-1").response_type is None
    assert agent_result.response_type is AgentEvalResult
    _assert_paginated_model(agent_results.response_type, AgentEvalResult)
    assert endpoints.delete_agent_eval_result(workspace="team-a", name="result-1").response_type is None
