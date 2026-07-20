# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluation session ClickHouse query tests."""

from nmp.intake.spans.evaluation_session_repository import (
    _SORT_EXPR_FINAL,
    _SORT_EXPR_PAGE,
    _build_order_by,
    _count_sql,
    _list_sql,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_list_sql(**kwargs) -> str:
    """Call _list_sql with fixed table names; only pass what the test cares about."""
    return _list_sql(
        trace_index_table="trace_index",
        spans_table="spans",
        evaluator_results_table="evaluator_results",
        scoped_filter_sql="",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Existing payload-mode tests — updated to pass the now-required sort_keys arg
# ---------------------------------------------------------------------------


def test_session_count_query_does_not_read_root_payloads() -> None:
    query = _count_sql(trace_index_table="trace_index", scoped_filter_sql="")

    assert "root_input" not in query
    assert "root_output" not in query


def test_session_preview_query_truncates_input_and_output_in_clickhouse() -> None:
    query = _make_list_sql(mode="preview", sort_keys=[])

    assert "substringUTF8(root_input, 1, %(payload_char_limit)s) AS input" in query
    assert "substringUTF8(root_output, 1, %(payload_char_limit)s) AS output" in query
    assert "root_input AS input" not in query
    assert "root_output AS output" not in query


def test_session_summary_query_omits_input_and_output_columns() -> None:
    query = _make_list_sql(mode="summary", sort_keys=[])

    assert "root_input" not in query
    assert "root_output" not in query
    assert "'' AS input" in query
    assert "'' AS output" in query


def test_session_detailed_query_reads_full_input_and_output() -> None:
    query = _make_list_sql(mode="detailed", sort_keys=[])

    assert "root_input AS input" in query
    assert "root_output AS output" in query
    assert "substringUTF8(root_input" not in query


# ---------------------------------------------------------------------------
# Sort: default (no sort_keys)
# The original ORDER BY must be preserved so existing behaviour is unchanged.
# ---------------------------------------------------------------------------


def test_default_sort_preserves_original_order() -> None:
    # sort_keys=[] means no sort param was sent — fall back to start_time ASC.
    query = _make_list_sql(mode="summary", sort_keys=[])

    # Both page_sessions and the final SELECT must use the default order.
    assert "ORDER BY start_time ASC, root_span_id ASC" in query
    assert "ORDER BY sessions.start_time ASC, sessions.root_span_id ASC" in query
    # No pre_page_metrics CTE should be injected.
    assert "pre_page_metrics" not in query


# ---------------------------------------------------------------------------
# Sort: single field (trace_index column — no pre-metrics join needed)
# ---------------------------------------------------------------------------


def test_single_field_sort_latency_desc() -> None:
    query = _make_list_sql(mode="summary", sort_keys=[("latency_ms", True)])

    # page_sessions ORDER BY should use the scoped_sessions alias (no prefix).
    assert "ORDER BY latency_ms DESC NULLS LAST, root_span_id ASC" in query
    # Final SELECT ORDER BY uses the sessions. prefix.
    assert "ORDER BY sessions.latency_ms DESC NULLS LAST, sessions.root_span_id ASC" in query
    # No pre_page_metrics needed for a trace_index column.
    assert "pre_page_metrics" not in query


def test_single_field_sort_status_asc() -> None:
    query = _make_list_sql(mode="summary", sort_keys=[("status", False)])

    assert "ORDER BY root_span_status ASC NULLS LAST, root_span_id ASC" in query
    assert "ORDER BY sessions.root_span_status ASC NULLS LAST, sessions.root_span_id ASC" in query
    assert "pre_page_metrics" not in query


# ---------------------------------------------------------------------------
# Sort: multi-field
# ---------------------------------------------------------------------------


def test_multi_field_sort_applies_keys_in_order() -> None:
    # Primary: cost DESC, tie-break: latency ASC (plus stable root_span_id).
    query = _make_list_sql(mode="summary", sort_keys=[("cost_total_usd", True), ("latency_ms", False)])

    # pre_page_metrics must be present because cost_total_usd requires it.
    assert "pre_page_metrics AS (" in query
    # page_sessions ORDER BY references pm. for cost, plain column for latency.
    assert "pm.cost_total_usd DESC NULLS LAST, latency_ms ASC NULLS LAST, s.root_span_id ASC" in query
    # Final SELECT ORDER BY uses metrics. for cost.
    assert (
        "metrics.cost_total_usd DESC NULLS LAST, sessions.latency_ms ASC NULLS LAST, sessions.root_span_id ASC" in query
    )


# ---------------------------------------------------------------------------
# Sort: cost_total_usd and tokens trigger pre_page_metrics CTE
# ---------------------------------------------------------------------------


def test_cost_sort_injects_pre_page_metrics_cte() -> None:
    query = _make_list_sql(mode="summary", sort_keys=[("cost_total_usd", True)])

    # The CTE must appear before page_sessions so page_sessions can JOIN against it.
    pre_pos = query.index("pre_page_metrics AS (")
    page_pos = query.index("page_sessions AS (")
    assert pre_pos < page_pos

    # page_sessions must join scoped_sessions with pre_page_metrics.
    assert "LEFT JOIN pre_page_metrics AS pm" in query


def test_tokens_sort_injects_pre_page_metrics_cte() -> None:
    query = _make_list_sql(mode="summary", sort_keys=[("tokens", False)])

    assert "pre_page_metrics AS (" in query
    assert "pm.total_tokens ASC NULLS LAST" in query
    # Final SELECT uses the NULL-safe coalesce form so sessions with only input or only
    # output tokens still sort by their partial usage instead of NULL-ing to the bottom.
    assert "coalesce(metrics.input_tokens, 0) + coalesce(metrics.output_tokens, 0)" in query


# ---------------------------------------------------------------------------
# Sort: stable tiebreaker is always appended
# ---------------------------------------------------------------------------


def test_tiebreaker_always_appended() -> None:
    # Even a single-field sort should end with root_span_id for determinism.
    query = _make_list_sql(mode="summary", sort_keys=[("started_at", False)])

    assert "root_span_id ASC" in query


# ---------------------------------------------------------------------------
# _build_order_by unit tests
# ---------------------------------------------------------------------------


def test_build_order_by_single_asc() -> None:
    result = _build_order_by([("latency_ms", False)], _SORT_EXPR_PAGE, "root_span_id ASC")
    assert result == "latency_ms ASC NULLS LAST, root_span_id ASC"


def test_build_order_by_single_desc() -> None:
    result = _build_order_by([("cost_total_usd", True)], _SORT_EXPR_PAGE, "s.root_span_id ASC")
    assert result == "pm.cost_total_usd DESC NULLS LAST, s.root_span_id ASC"


def test_build_order_by_multi() -> None:
    result = _build_order_by(
        [("cost_total_usd", True), ("latency_ms", False)],
        _SORT_EXPR_FINAL,
        "sessions.root_span_id ASC",
    )
    assert result == (
        "metrics.cost_total_usd DESC NULLS LAST, sessions.latency_ms ASC NULLS LAST, sessions.root_span_id ASC"
    )
