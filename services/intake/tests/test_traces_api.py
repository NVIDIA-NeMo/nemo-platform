# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trace API filter tests."""

import json
from datetime import datetime, timezone

from nmp.common.api.filter import parse_json_filter
from nmp.common.api.parsed_filter import ParsedFilter
from nmp.intake.spans.api.traces import _trace_filter
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
                "evaluation_run_id": "run-a",
            }
        ),
    )

    assert filters.workspace == "workspace-a"
    assert filters.trace_id == "trace-a"
    assert filters.session_id == "session-a"
    assert filters.status == SpanStatus.ERROR
    assert filters.started_at_gte == started_at
    assert len(filters.root_attribute_filters) == 1
    assert filters.root_attribute_filters[0].field == "evaluation_run_id"
    assert filters.root_attribute_filters[0].value == "run-a"
    assert not filters.span_attribute_filters


def _parsed_filter(value: dict[str, object]) -> ParsedFilter:
    return ParsedFilter(operation=parse_json_filter(json.dumps(value)))
