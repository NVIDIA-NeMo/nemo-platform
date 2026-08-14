# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ClickHouse migration helper tests."""

import re
from pathlib import Path

import nmp.intake.spans.clickhouse_migrations as clickhouse_migrations
import pytest
from nmp.intake.spans.clickhouse_migrations import parse_clickhouse_url
from nmp.intake.spans.span_attribute_catalog import SpanAttributeField, spec_for_field


def test_parse_clickhouse_url_rejects_hostless_url():
    with pytest.raises(ValueError, match="include a host"):
        parse_clickhouse_url("http://:8123")


def test_parse_clickhouse_url_keeps_default_ports():
    assert parse_clickhouse_url("clickhouse.local").port == 8123
    assert parse_clickhouse_url("https://clickhouse.local").port == 8443


def test_spans_schema_keeps_cityhash_identity_expression():
    source = Path(clickhouse_migrations.__file__).read_text(encoding="utf-8")
    match = re.search(r"\bid\s+UInt64\s+MATERIALIZED\s+cityHash64\(([^)]*)\)", source)

    assert match is not None
    assert [part.strip() for part in match.group(1).split(",")] == [
        "workspace",
        "source_format",
        "trace_id",
        "external_span_id",
    ]


def test_trace_index_schema_is_root_span_projection():
    source = Path(clickhouse_migrations.__file__).read_text(encoding="utf-8")
    function_match = re.search(
        r"def _create_trace_index_schema\(.*?^_MIGRATIONS",
        source,
        re.DOTALL | re.MULTILINE,
    )
    assert function_match is not None
    source = function_match.group(0)

    table_match = re.search(
        r"CREATE TABLE \{table\}.*?ttl_only_drop_parts = 1",
        source,
        re.DOTALL,
    )

    assert table_match is not None
    ddl = source

    assert '"trace_index"' in source
    assert '"trace_index_mv"' in source
    assert "CREATE TABLE {table}" in ddl
    assert "CREATE MATERIALIZED VIEW {view}" in ddl
    assert "TO {table}" in ddl
    assert "INSERT INTO {table}" in source
    assert "WHERE external_parent_span_id = ''" in ddl
    # evaluation_id is resolved via a coalesce expression (canonical key + legacy aliases), not a single
    # bag-key lookup, so the backfill keeps spans stored under an older key associated.
    assert "{evaluation_id_expr} AS evaluation_id" in ddl
    assert "coalesce(" in ddl
    assert "attributes_string['{test_case_key}'] AS test_case_id" in ddl
    assert "root_status LowCardinality(String)" in ddl
    assert "root_input String" in ddl
    assert "PRIMARY KEY (workspace, root_started_at)" in ddl
    assert "ORDER BY (workspace, root_started_at, trace_id, root_span_id)" in ddl
    assert "INDEX idx_evaluation_id evaluation_id" in ddl
    assert "index_granularity = 256" in ddl


def test_trace_index_mv_keys_match_attribute_catalog():
    evaluation_spec = spec_for_field(SpanAttributeField.EVALUATION_NAME)
    assert evaluation_spec.bag_key == "nemo.evaluation.name"
    # The legacy key is still accepted on ingest so pre-rename producers keep associating.
    assert "nemo.experiment.id" in evaluation_spec.source_keys
    assert spec_for_field(SpanAttributeField.TEST_CASE_ID).bag_key == "nemo.test_case.id"
