# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluation session ClickHouse query tests."""

from nmp.intake.spans.evaluation_session_repository import _count_sql, _list_sql


def test_session_count_query_does_not_read_root_payloads() -> None:
    query = _count_sql(trace_index_table="trace_index", scoped_filter_sql="")

    assert "root_input" not in query
    assert "root_output" not in query


def test_session_preview_query_truncates_input_and_output_in_clickhouse() -> None:
    query = _list_sql(
        trace_index_table="trace_index",
        spans_table="spans",
        evaluator_results_table="evaluator_results",
        scoped_filter_sql="",
        mode="preview",
    )

    assert "substringUTF8(root_input, 1, %(payload_char_limit)s) AS input" in query
    assert "substringUTF8(root_output, 1, %(payload_char_limit)s) AS output" in query
    assert "root_input AS input" not in query
    assert "root_output AS output" not in query


def test_session_summary_query_omits_input_and_output_columns() -> None:
    query = _list_sql(
        trace_index_table="trace_index",
        spans_table="spans",
        evaluator_results_table="evaluator_results",
        scoped_filter_sql="",
        mode="summary",
    )

    assert "root_input" not in query
    assert "root_output" not in query
    assert "'' AS input" in query
    assert "'' AS output" in query


def test_session_detailed_query_reads_full_input_and_output() -> None:
    query = _list_sql(
        trace_index_table="trace_index",
        spans_table="spans",
        evaluator_results_table="evaluator_results",
        scoped_filter_sql="",
        mode="detailed",
    )

    assert "root_input AS input" in query
    assert "root_output AS output" in query
    assert "substringUTF8(root_input" not in query
