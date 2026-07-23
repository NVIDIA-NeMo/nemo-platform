# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_insights_plugin.entities import (
    EvalAuthorCapture,
    EvalAuthorCaptureStatus,
    EvalAuthorConfigDetails,
    EvalAuthorInputs,
    EvalAuthorModels,
    EvalAuthorOutputs,
    EvalAuthorProvenance,
    EvalAuthorRun,
    EvalAuthorRunStage,
    EvalAuthorRunStatus,
    EvalAuthorValidation,
    Insight,
)
from nemo_insights_plugin.service import InsightsService
from nemo_platform_plugin.entity_client import NemoPaginationInfo, get_entity_client


def _insight(*, workspace: str = "workspace-a") -> Insight:
    insight = Insight(
        name="unsafe-transfer",
        workspace=workspace,
        title="Unsafe transfer",
        agent="airline-agent",
        description="The agent escalates an in-scope request.",
        trace_refs=["trace-1"],
    )
    insight._id = "insight-1"
    return insight


def _run(
    *,
    workspace: str = "workspace-a",
    status: EvalAuthorRunStatus = EvalAuthorRunStatus.RUNNING,
    stage: EvalAuthorRunStage = EvalAuthorRunStage.AUTHORING_VERIFIER,
) -> EvalAuthorRun:
    run = EvalAuthorRun(
        name="eval-author-run-123",
        workspace=workspace,
        insight_id="insight-1",
        status=status,
        stage=stage,
        evaluator_type="harbor",
        config=EvalAuthorConfigDetails(),
        inputs=EvalAuthorInputs(
            agent="airline-agent",
            task_template="fileset://workspace-a/template",
            train_dataset="fileset://workspace-a/train-source",
            validation_dataset="fileset://workspace-a/validation-source",
            trace_refs=["trace-1"],
        ),
        models=EvalAuthorModels(smart="gpt-smart", fast="gpt-fast"),
        provenance=EvalAuthorProvenance(
            optimizer_branch="codex/eval-author",
            optimizer_commit="abcdef",
            runner="run_eval_author",
        ),
        started_at=datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc),
    )
    run._id = "run-1"
    return run


def _payload() -> dict[str, object]:
    return {
        "insight_id": "insight-1",
        "config": {
            "max_traces": 1,
            "max_summary_tokens": 80_000,
            "max_validation_repair_attempts": 5,
        },
        "inputs": {
            "agent": "airline-agent",
            "task_template": "fileset://workspace-a/template",
            "train_dataset": "fileset://workspace-a/train-source",
            "validation_dataset": "fileset://workspace-a/validation-source",
            "trace_refs": ["trace-1"],
        },
        "models": {"smart": "gpt-smart", "fast": "gpt-fast"},
        "provenance": {
            "optimizer_branch": "codex/eval-author",
            "optimizer_commit": "abcdef",
            "runner": "run_eval_author",
        },
    }


def _app(entity_client: AsyncMock) -> TestClient:
    app = FastAPI()
    eval_author_router = next(
        spec for spec in InsightsService().get_routers() if spec.tag == "Insights Eval Author Runs"
    )
    app.include_router(eval_author_router.router, prefix=eval_author_router.prefix)
    app.dependency_overrides[get_entity_client] = lambda: entity_client
    return TestClient(app)


def test_create_run_validates_insight_and_sets_started_at() -> None:
    entity_client = AsyncMock()
    entity_client.get_by_id.return_value = _insight()

    async def create(entity: EvalAuthorRun) -> EvalAuthorRun:
        entity._id = "run-created"
        return entity

    entity_client.create.side_effect = create

    response = _app(entity_client).post(
        "/v2/workspaces/workspace-a/eval-author-runs",
        json={**_payload(), "status": "running", "stage": "analyzing_traces"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "run-created"
    assert body["name"].startswith("eval-author-run-")
    assert body["started_at"] is not None
    assert body["completed_at"] is None
    entity_client.get_by_id.assert_awaited_once_with(Insight, entity_id="insight-1")


def test_create_run_rejects_insight_from_another_workspace() -> None:
    entity_client = AsyncMock()
    entity_client.get_by_id.return_value = _insight(workspace="workspace-b")

    response = _app(entity_client).post(
        "/v2/workspaces/workspace-a/eval-author-runs",
        json=_payload(),
    )

    assert response.status_code == 422
    assert "does not exist in workspace 'workspace-a'" in response.json()["detail"]
    entity_client.create.assert_not_awaited()


def test_list_runs_forwards_filters_pagination_and_sort() -> None:
    entity_client = AsyncMock()
    run = _run()
    entity_client.list.return_value = SimpleNamespace(
        data=[run],
        pagination=NemoPaginationInfo(
            page=2,
            page_size=10,
            current_page_size=1,
            total_pages=2,
            total_results=11,
        ),
    )

    response = _app(entity_client).get(
        "/v2/workspaces/workspace-a/eval-author-runs",
        params={
            "page": 2,
            "page_size": 10,
            "sort": "-created_at",
            "insight_id": "insight-1",
            "status": "running",
            "created_at": "2026-07-01T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["pagination"]["total_results"] == 11
    entity_client.list.assert_awaited_once_with(
        EvalAuthorRun,
        workspace="workspace-a",
        page=2,
        page_size=10,
        sort="-created_at",
        filter_obj={
            "insight_id": "insight-1",
            "status": "running",
            "created_at": {"$gte": datetime(2026, 7, 1, tzinfo=timezone.utc)},
        },
    )


def test_get_run_hides_cross_workspace_entity() -> None:
    entity_client = AsyncMock()
    entity_client.get_by_id.return_value = _run(workspace="workspace-b")

    response = _app(entity_client).get("/v2/workspaces/workspace-a/eval-author-runs/run-1")

    assert response.status_code == 404


def test_update_run_rejects_stage_regression() -> None:
    entity_client = AsyncMock()
    entity_client.get_by_id.return_value = _run(stage=EvalAuthorRunStage.VALIDATING)

    response = _app(entity_client).patch(
        "/v2/workspaces/workspace-a/eval-author-runs/run-1",
        json={"stage": "analyzing_traces"},
    )

    assert response.status_code == 409
    assert "cannot regress" in response.json()["detail"]
    entity_client.update.assert_not_awaited()


def test_update_run_succeeds_and_sets_completion_timestamp() -> None:
    entity_client = AsyncMock()
    run = _run()
    entity_client.get_by_id.return_value = run
    entity_client.update.side_effect = lambda entity: entity
    outputs = EvalAuthorOutputs(
        artifact_fileset="fileset://workspace-a/opt-ea-123-artifacts",
        insight_suite="fileset://workspace-a/insight-suite",
        train_dataset="fileset://workspace-a/opt-ea-123-train",
        validation_dataset="fileset://workspace-a/opt-ea-123-validation",
        metric_names=["safe_transfer"],
        train_task_count=50,
        validation_task_count=30,
    )

    response = _app(entity_client).patch(
        "/v2/workspaces/workspace-a/eval-author-runs/run-1",
        json={
            "status": "succeeded",
            "stage": "completed",
            "outputs": outputs.model_dump(mode="json"),
            "capture": EvalAuthorCapture(
                prompt=EvalAuthorCaptureStatus.COMPLETE,
                trajectory=EvalAuthorCaptureStatus.COMPLETE,
                redactions=True,
                redacted_fields=["authorization"],
            ).model_dump(mode="json"),
            "validation": EvalAuthorValidation(status="passed", attempt_count=1).model_dump(
                mode="json"
            ),
            "summary": "Authored one verifier.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["completed_at"] is not None
    assert body["outputs"]["metric_names"] == ["safe_transfer"]
    assert body["capture"]["redacted_fields"] == ["authorization"]


def test_failed_run_retains_partial_artifacts_and_error() -> None:
    entity_client = AsyncMock()
    run = _run()
    entity_client.get_by_id.return_value = run
    entity_client.update.side_effect = lambda entity: entity

    response = _app(entity_client).patch(
        "/v2/workspaces/workspace-a/eval-author-runs/run-1",
        json={
            "status": "failed",
            "outputs": {
                "artifact_fileset": "fileset://workspace-a/opt-ea-123-artifacts",
                "metric_names": [],
                "train_task_count": 0,
                "validation_task_count": 0,
            },
            "capture": {
                "prompt": "partial",
                "trajectory": "partial",
                "redactions": True,
                "redacted_fields": ["api_key"],
            },
            "error": "Validation did not converge.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["stage"] == "authoring_verifier"
    assert body["outputs"]["artifact_fileset"].endswith("-artifacts")
    assert body["error"] == "Validation did not converge."
    assert body["completed_at"] is not None


def test_terminal_run_cannot_transition_or_change_stage() -> None:
    entity_client = AsyncMock()
    run = _run(
        status=EvalAuthorRunStatus.FAILED,
        stage=EvalAuthorRunStage.AUTHORING_VERIFIER,
    )
    entity_client.get_by_id.return_value = run

    status_response = _app(entity_client).patch(
        "/v2/workspaces/workspace-a/eval-author-runs/run-1",
        json={"status": "running"},
    )
    stage_response = _app(entity_client).patch(
        "/v2/workspaces/workspace-a/eval-author-runs/run-1",
        json={"stage": "validating"},
    )

    assert status_response.status_code == 409
    assert stage_response.status_code == 409
