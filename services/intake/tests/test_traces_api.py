# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace API filter tests."""

import json
from datetime import datetime, timezone

from nmp.common.api.filter import parse_json_filter
from nmp.common.api.parsed_filter import ParsedFilter
from nmp.intake.spans.api.traces import _trace_filter
from nmp.intake.spans.api.traces_schemas import TraceFilter
from nmp.intake.spans.domain import SpanStatus


def test_trace_filter_maps_public_fields_to_repository_filter():
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    filters = _trace_filter(
        "workspace-a",
        _parsed_filter(
            {
                "id": "trace-a",
                "session_id": "session-a",
                "status": "error",
                "started_at": {"$gte": started_at.isoformat()},
                "evaluation_id": "experiment-a",
                "test_case_id": "case-a",
            }
        ),
    )

    assert filters.workspace == "workspace-a"
    assert filters.trace_id == "trace-a"
    assert filters.session_id == "session-a"
    assert filters.status == SpanStatus.ERROR
    assert filters.started_at_gte == started_at
    assert filters.evaluation_id == "experiment-a"
    assert filters.test_case_id == "case-a"


def test_trace_filter_accepts_evaluation_id():
    filters = _trace_filter(
        "workspace-a",
        _parsed_filter({"evaluation_id": "experiment-a"}),
    )

    assert filters.evaluation_id == "experiment-a"


def test_trace_filter_accepts_deprecated_experiment_id_alias():
    filters = _trace_filter(
        "workspace-a",
        _parsed_filter({"experiment_id": "experiment-a"}),
    )

    assert filters.evaluation_id == "experiment-a"


def test_trace_filter_schema_exposes_evaluation_id_with_deprecated_experiment_id_alias():
    properties = TraceFilter.model_json_schema()["properties"]

    assert properties["evaluation_id"]["description"] == "Filter by root-span evaluation id."
    assert "deprecated" not in properties["evaluation_id"]
    assert properties["experiment_id"]["deprecated"] is True
    assert properties["test_case_id"]["description"] == "Filter by root-span evaluation test case id."
    assert "deprecated" not in properties["test_case_id"]


def test_trace_filter_applies_no_implicit_time_bound():
    filters = _trace_filter("workspace-a", _parsed_filter({"id": "trace-a"}))

    assert filters.started_at_gte is None
    assert filters.started_at_lte is None


def _parsed_filter(value: dict[str, object]) -> ParsedFilter:
    return ParsedFilter(operation=parse_json_filter(json.dumps(value)))
