# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validation helpers for experiment-scoped ingest."""

from fastapi import HTTPException, status
from nmp.common.entities.client import EntityClient, EntityNotFoundError
from nmp.intake.entities.experiments import Experiment
from nmp.intake.spans.ingest.evaluation_context import ExperimentContext


async def validate_experiment_context(
    *,
    workspace: str,
    context: ExperimentContext | None,
    entity_client: EntityClient,
) -> None:
    if context is None:
        return
    try:
        await entity_client.get(Experiment, name=context.experiment_id, workspace=workspace)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment '{context.experiment_id}' must be created before it can be logged.",
        ) from exc
