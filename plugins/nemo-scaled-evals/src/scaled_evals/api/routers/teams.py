# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, Query

from scaled_evals.api.schemas.common import ListEnvelope, StubRecord, TeamSummaryResponse
from scaled_evals.api.utils import list_envelope

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/{team_id}/summary", response_model=TeamSummaryResponse)
def team_summary(team_id: str) -> TeamSummaryResponse:
    return TeamSummaryResponse(team_id=team_id, evaluations={"active": 0}, stub=True)


@router.get("/{team_id}/evaluations", response_model=ListEnvelope[StubRecord])
def team_evaluations(
    team_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> ListEnvelope[StubRecord]:
    _ = team_id
    return list_envelope(cursor=cursor, limit=limit)
