# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ATIF trajectory ingest for ClickHouse-backed Intake spans."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from nmp.common.entities.client import EntityClient
from nmp.common.service.dependencies import get_entity_client
from nmp.intake.spans.api.dependencies import SpansServiceDep, require_workspace_access
from nmp.intake.spans.domain import TraceBatch
from nmp.intake.spans.ingest.atif_domain import (
    AtifAgent,
    AtifFinalMetrics,
    AtifSchemaVersion,
    AtifStep,
    AtifTrajectory,
    validate_atif_step_ids,
    validate_atif_tool_call_references,
)
from nmp.intake.spans.ingest.atif_mapping import trajectory_to_evaluator_results, trajectory_to_spans
from nmp.intake.spans.ingest.evaluation_context import ExperimentContextIngestModel
from nmp.intake.spans.ingest.experiment_context_validation import validate_experiment_context
from nmp.intake.spans.storage import utc_now
from pydantic import ConfigDict, Field, model_validator

router = APIRouter(dependencies=[Depends(require_workspace_access)])
API_TAG = "Ingest"
EntityClientDep = Annotated[EntityClient, Depends(get_entity_client)]


class AtifIngestRequest(ExperimentContextIngestModel):
    """Span-based ATIF ingest request.

    ATIF project scoping is intentionally not accepted here; use the workspace
    route and ``experiment_context`` for experiment identity.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: AtifSchemaVersion
    session_id: str | None = None
    agent: AtifAgent
    final_metrics: AtifFinalMetrics | None = None
    continued_trajectory_ref: str | None = None
    notes: str | None = None
    extra: dict[str, Any] | None = None
    steps: list[AtifStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_steps(self) -> AtifIngestRequest:
        validate_atif_step_ids(self.steps)
        validate_atif_tool_call_references(self.steps)
        return self

    def to_trajectory(self) -> AtifTrajectory:
        kwargs: dict[str, Any] = {} if self.session_id is None else {"session_id": self.session_id}
        return AtifTrajectory(
            schema_version=self.schema_version,
            agent=self.agent,
            steps=self.steps,
            final_metrics=self.final_metrics,
            continued_trajectory_ref=self.continued_trajectory_ref,
            notes=self.notes,
            extra=self.extra,
            evaluation_context=self.resolved_evaluation_context(),
            **kwargs,
        )


@router.post(
    "/v2/workspaces/{workspace}/ingest/atif",
    tags=[API_TAG],
    status_code=status.HTTP_201_CREATED,
    response_class=Response,
)
async def ingest_atif(
    workspace: str,
    body: AtifIngestRequest,
    service: SpansServiceDep,
    entity_client: EntityClientDep,
) -> Response:
    await validate_experiment_context(
        workspace=workspace,
        context=body.resolved_evaluation_context(),
        entity_client=entity_client,
    )
    ingested_at = utc_now()
    trajectory = body.to_trajectory()
    spans = trajectory_to_spans(
        workspace=workspace,
        trajectory=trajectory,
        ingested_at=ingested_at,
    )
    evaluator_results = trajectory_to_evaluator_results(
        workspace=workspace,
        trajectory=trajectory,
        spans=spans,
        ingested_at=ingested_at,
    )
    await service.ingest_batch(TraceBatch(spans=spans, evaluator_results=evaluator_results))
    return Response(status_code=status.HTTP_201_CREATED)
