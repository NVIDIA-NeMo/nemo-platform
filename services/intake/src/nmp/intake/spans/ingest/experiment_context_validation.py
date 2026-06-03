# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validation helpers for experiment-scoped ingest."""

from fastapi import HTTPException, status
from nmp.common.entities.client import EntityClient, EntityNotFoundError
from nmp.intake.entities.experiments import Experiment
from nmp.intake.spans.ingest.evaluation_context import EvaluationContext, ExperimentContext


async def validate_experiment_context(
    *,
    workspace: str,
    context: EvaluationContext | ExperimentContext | None,
    entity_client: EntityClient,
) -> None:
    if context is None:
        return
    experiment_id = _experiment_id(context)
    if not experiment_id:
        return
    try:
        await entity_client.get(Experiment, name=experiment_id, workspace=workspace)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment '{experiment_id}' must be created before it can be logged.",
        ) from exc


def _experiment_id(context: EvaluationContext | ExperimentContext) -> str | None:
    if isinstance(context, ExperimentContext):
        return context.experiment_id
    return context.evaluation_id
