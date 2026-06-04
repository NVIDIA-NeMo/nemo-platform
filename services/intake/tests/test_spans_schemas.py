# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Span domain and API schema tests."""

import json
from datetime import datetime, timezone

import pytest
from nmp.intake.spans.api.spans_schemas import Span
from nmp.intake.spans.api.traces_schemas import Trace
from nmp.intake.spans.domain import IntakeSpan, IntakeTrace, SpanKind, SpanStatus, TraceEvaluationContext
from nmp.intake.spans.storage import json_dumps_preserve
from pydantic import ValidationError


def test_intake_span_rejects_empty_external_span_id():
    with pytest.raises(ValidationError, match="external_span_id must not be empty"):
        IntakeSpan(
            workspace="workspace-a",
            session_id="session-a",
            trace_id="trace-a",
            source_format="test",
            external_span_id="",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_span_response_raw_attributes_merges_atif_raw_with_unknown_attributes():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    span = IntakeSpan(
        workspace="workspace-a",
        session_id="session-a",
        trace_id="trace-a",
        source_format="atif",
        external_span_id="span-a",
        kind=SpanKind.LLM,
        status=SpanStatus.SUCCESS,
        start_time=now,
        event_ts=now,
        attributes_string={
            "atif.raw": json_dumps_preserve(
                {"source_session_id": "session-a", "experiment.metadata": {"source": "atif.raw"}}
            ),
            "custom.string": "value-a",
            "experiment.metadata": json.dumps({"source": "attribute.bag"}),
            "gen_ai.request.model": "model-a",
        },
        attributes_number={"custom.number": 1.25, "llm.token_count.prompt": 42},
        attributes_bool={"custom.bool": True},
    )

    response = Span.from_domain(span)

    assert response.raw_attributes is not None
    assert json.loads(response.raw_attributes) == {
        "source_session_id": "session-a",
        "custom.string": "value-a",
        "custom.number": 1.25,
        "custom.bool": True,
    }


def test_trace_response_maps_core_trace_fields():
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended_at = datetime(2026, 1, 1, 0, 0, 2, 500000, tzinfo=timezone.utc)
    trace = IntakeTrace(
        id="trace-a",
        workspace="workspace-a",
        session_id="session-a",
        source_format="otel",
        root_span_id="span-root",
        name="root",
        input="root input",
        output="root output",
        project="project-a",
        evaluation_context=TraceEvaluationContext(
            evaluation_id="eval-a",
            evaluation_run_id="run-a",
            dataset_name="dataset-a",
            metadata={"split": "dev"},
        ),
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=2500,
        ingested_at=ended_at,
        status=SpanStatus.ERROR,
        input_tokens=420,
        output_tokens=310,
        cached_tokens=128,
        total_tokens=858,
        cost_usd=0.0061,
        cost_input_usd=0.0024,
        cost_output_usd=0.0037,
        models=["model-a"],
        providers=["openai"],
        span_count=2,
        error_count=1,
    )

    response = Trace.from_domain(trace)

    assert response.id == "trace-a"
    assert response.root_span_id == "span-root"
    assert response.session_id == "session-a"
    assert response.workspace == "workspace-a"
    assert response.name == "root"
    assert response.started_at == started_at
    assert response.ended_at == ended_at
    assert response.status == SpanStatus.ERROR
    assert response.duration_ms == 2500
    assert response.input_tokens == 420
    assert response.output_tokens == 310
    assert response.cached_tokens == 128
    assert response.total_tokens == 858
    assert response.cost_usd == 0.0061
    assert response.cost_input_usd == 0.0024
    assert response.cost_output_usd == 0.0037
    assert response.span_count == 2
    assert response.error_count == 1
    assert response.evaluation_context is not None
    assert response.evaluation_context.evaluation_id == "eval-a"
    assert response.evaluation_context.evaluation_run_id == "run-a"
    assert response.evaluation_context.dataset_name == "dataset-a"
    assert response.evaluation_context.metadata == {"split": "dev"}
