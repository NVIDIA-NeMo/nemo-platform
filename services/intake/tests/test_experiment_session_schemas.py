# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone

from nmp.intake.api.v2.experiments.schemas import EvaluationSessionResponse
from nmp.intake.spans.domain import SpanStatus
from nmp.intake.spans.evaluation_session_repository import EvaluationSessionRow


def test_evaluation_session_from_row_preserves_input() -> None:
    input_text = "x" * 1050
    row = _session_row(input_text=input_text)

    response = EvaluationSessionResponse.from_row(row)

    assert response.input == input_text


def _session_row(input_text: str) -> EvaluationSessionRow:
    now = datetime.now(timezone.utc)
    return EvaluationSessionRow(
        workspace="default",
        evaluation_name="evaluation",
        session_id="session",
        test_case_id="case",
        trace_id="trace",
        root_span_id="root",
        started_at=now,
        ended_at=now,
        latency_ms=10,
        status=SpanStatus.SUCCESS,
        input=input_text,
        input_tokens=1,
        output_tokens=2,
        cached_tokens=3,
        cost_total_usd=0.01,
        evaluator_scores={"score": 1.0},
    )
