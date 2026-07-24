# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Behavioral tests for the OTLP JSONL <-> protobuf helpers.

Everything is asserted through observable output — the trace id string or a
parsed ``ExportTraceServiceRequest`` — never through private helpers, so these
pin the module's contract rather than its implementation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator import ResourceRef
from nemo_experimentalist_plugin.experimentalist.otlp import (
    jsonl_to_protobuf,
    read_trace_id,
    spans_to_protobuf,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

TRACE_HEX = "769b36252e9284e8a0329643dafcbe68"  # 32 hex chars = 16 bytes
SPAN_HEX = "97f23312b666e0bc"  # 16 hex chars = 8 bytes
PARENT_HEX = "aaaaaaaaaaaaaaaa"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ref(path: Path) -> ResourceRef:
    return ResourceRef(uri=f"file://{path}", description="", metadata={})


def _write(path: Path, *lines: dict) -> Path:
    path.write_text("\n".join(json.dumps(line) for line in lines))
    return path


def _merge(payloads: list[bytes]) -> ExportTraceServiceRequest:
    """Concatenate chunked payloads back into one request (proto repeated-field merge)."""
    req = ExportTraceServiceRequest()
    req.ParseFromString(b"".join(payloads))
    return req


def _all_spans(req: ExportTraceServiceRequest) -> list:
    return [sp for rs in req.resource_spans for ss in rs.scope_spans for sp in ss.spans]


def _resource_attrs(rs) -> dict:
    return {a.key: a.value for a in rs.resource.attributes}


def _span_row(**overrides) -> dict:
    row = {"trace_id": TRACE_HEX, "span_id": SPAN_HEX}
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# read_trace_id
# ---------------------------------------------------------------------------


def test_read_trace_id_returns_first_span_hex(tmp_path):
    p = _write(tmp_path / "t.jsonl", {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": TRACE_HEX}]}]}]})
    assert read_trace_id(_ref(p)) == TRACE_HEX


def test_read_trace_id_skips_blank_lines_and_takes_first(tmp_path):
    first_hex = "a" * 32
    second_hex = "b" * 32
    first = {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": first_hex}]}]}]}
    second = {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": second_hex}]}]}]}
    p = tmp_path / "t.jsonl"
    p.write_text(f"\n\n{json.dumps(first)}\n\n{json.dumps(second)}\n")
    assert read_trace_id(_ref(p)) == first_hex


def test_read_trace_id_scans_across_nested_lists(tmp_path):
    line = {
        "resourceSpans": [
            {"scopeSpans": [{"spans": [{"spanId": "no-trace-here"}]}]},
            {"scopeSpans": [{"spans": [{}, {"traceId": TRACE_HEX}]}]},
        ]
    }
    p = _write(tmp_path / "t.jsonl", line)
    assert read_trace_id(_ref(p)) == TRACE_HEX


@pytest.mark.parametrize(
    "line",
    [
        {"resourceSpans": [{"scopeSpans": [{"spans": [{"spanId": "1234567890"}]}]}]},  # no traceId
        {"resourceSpans": []},  # no spans at all
    ],
)
def test_read_trace_id_raises_when_absent(tmp_path, line):
    p = _write(tmp_path / "t.jsonl", line)
    with pytest.raises(ValueError, match="No traceId"):
        read_trace_id(_ref(p))


def test_read_trace_id_raises_on_empty_file(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    with pytest.raises(ValueError, match="No traceId"):
        read_trace_id(_ref(p))


# ---------------------------------------------------------------------------
# jsonl_to_protobuf
# ---------------------------------------------------------------------------


def test_jsonl_hex_ids_become_bytes(tmp_path):
    p = _write(
        tmp_path / "t.jsonl",
        {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": TRACE_HEX, "spanId": SPAN_HEX}]}]}]},
    )
    (sp,) = _all_spans(_merge(jsonl_to_protobuf(p, {})))
    assert sp.trace_id.hex() == TRACE_HEX
    assert sp.span_id.hex() == SPAN_HEX


def test_jsonl_parent_span_hex_becomes_bytes(tmp_path):
    p = _write(
        tmp_path / "t.jsonl",
        {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": TRACE_HEX, "parentSpanId": PARENT_HEX}]}]}]},
    )
    (sp,) = _all_spans(_merge(jsonl_to_protobuf(p, {})))
    assert sp.parent_span_id.hex() == PARENT_HEX


def test_jsonl_injects_extra_resource_attrs(tmp_path):
    p = _write(tmp_path / "t.jsonl", {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": TRACE_HEX}]}]}]})
    req = _merge(jsonl_to_protobuf(p, {"nemo.experiment.id": "exp-1", "nemo.trial.id": "t1"}))
    attrs = _resource_attrs(req.resource_spans[0])
    assert attrs["nemo.experiment.id"].string_value == "exp-1"
    assert attrs["nemo.trial.id"].string_value == "t1"


def test_jsonl_preserves_existing_resource_attrs(tmp_path):
    line = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "hostname", "value": {"stringValue": "h1"}}]},
                "scopeSpans": [{"spans": [{"traceId": TRACE_HEX}]}],
            }
        ]
    }
    p = _write(tmp_path / "t.jsonl", line)
    attrs = _resource_attrs(_merge(jsonl_to_protobuf(p, {"nemo.experiment.id": "exp-1"})).resource_spans[0])
    assert attrs["hostname"].string_value == "h1"  # original kept
    assert attrs["nemo.experiment.id"].string_value == "exp-1"  # new added


def test_jsonl_extra_attr_overrides_duplicate_key(tmp_path):
    line = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "nemo.experiment.id", "value": {"stringValue": "old"}}]},
                "scopeSpans": [{"spans": [{"traceId": TRACE_HEX}]}],
            }
        ]
    }
    p = _write(tmp_path / "t.jsonl", line)
    rs = _merge(jsonl_to_protobuf(p, {"nemo.experiment.id": "new"})).resource_spans[0]
    keys = [a.key for a in rs.resource.attributes]
    assert keys.count("nemo.experiment.id") == 1  # not duplicated
    assert _resource_attrs(rs)["nemo.experiment.id"].string_value == "new"  # overridden


def test_jsonl_chunks_split_and_merge_back(tmp_path):
    lines = [
        {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": TRACE_HEX, "spanId": format(i, "016x")}]}]}]}
        for i in range(5)
    ]
    p = _write(tmp_path / "t.jsonl", *lines)
    payloads = jsonl_to_protobuf(p, {}, max_bytes=1)  # force one resourceSpans per payload
    assert len(payloads) == 5
    assert len(_all_spans(_merge(payloads))) == 5  # nothing lost on split


def test_jsonl_empty_file_yields_no_payloads(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    assert jsonl_to_protobuf(p, {"nemo.experiment.id": "exp-1"}) == []


# ---------------------------------------------------------------------------
# spans_to_protobuf
# ---------------------------------------------------------------------------


def test_spans_builds_valid_protobuf_with_ids_and_name():
    (sp,) = _all_spans(_merge(spans_to_protobuf([_span_row(name="root")], {})))
    assert sp.trace_id.hex() == TRACE_HEX
    assert sp.span_id.hex() == SPAN_HEX
    assert sp.name == "root"


def test_spans_injects_resource_attrs():
    req = _merge(spans_to_protobuf([_span_row()], {"nemo.experiment.id": "exp-42", "nemo.test_case.id": "task1"}))
    attrs = _resource_attrs(req.resource_spans[0])
    assert attrs["nemo.experiment.id"].string_value == "exp-42"
    assert attrs["nemo.test_case.id"].string_value == "task1"


def test_spans_preserves_raw_attributes_from_json_string():
    row = _span_row(raw_attributes=json.dumps({"gen_ai.system": "openai", "llm.token_count.total": 42}))
    (sp,) = _all_spans(_merge(spans_to_protobuf([row], {})))
    span_attrs = {a.key: a.value for a in sp.attributes}
    assert span_attrs["gen_ai.system"].string_value == "openai"
    assert span_attrs["llm.token_count.total"].int_value == 42


def test_spans_accepts_raw_attributes_as_dict():
    (sp,) = _all_spans(_merge(spans_to_protobuf([_span_row(raw_attributes={"k": "v"})], {})))
    assert {a.key: a.value.string_value for a in sp.attributes}["k"] == "v"


def test_spans_renders_each_attr_value_type():
    row = _span_row(raw_attributes={"b": True, "i": 7, "f": 1.5, "s": "x", "obj": {"n": 1}})
    (sp,) = _all_spans(_merge(spans_to_protobuf([row], {})))
    d = {a.key: a.value for a in sp.attributes}
    assert d["b"].bool_value is True
    assert d["i"].int_value == 7
    assert d["f"].double_value == 1.5
    assert d["s"].string_value == "x"
    assert json.loads(d["obj"].string_value) == {"n": 1}  # non-scalar -> JSON string


def test_spans_invalid_raw_attributes_string_ignored():
    (sp,) = _all_spans(_merge(spans_to_protobuf([_span_row(raw_attributes="{not json")], {})))
    assert list(sp.attributes) == []


def test_spans_iso_timestamp_converted_to_unix_nano():
    row = _span_row(started_at="2026-01-01T00:00:00+00:00", ended_at="2026-01-01T00:00:01+00:00")
    (sp,) = _all_spans(_merge(spans_to_protobuf([row], {})))
    base = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    assert sp.start_time_unix_nano == base
    assert sp.end_time_unix_nano == base + 1_000_000_000


def test_spans_z_suffix_timestamp_equivalent_to_offset():
    z = _all_spans(_merge(spans_to_protobuf([_span_row(started_at="2026-01-01T00:00:00Z")], {})))[0]
    offset = _all_spans(_merge(spans_to_protobuf([_span_row(started_at="2026-01-01T00:00:00+00:00")], {})))[0]
    assert z.start_time_unix_nano == offset.start_time_unix_nano


def test_spans_epoch_number_timestamp_passthrough():
    (sp,) = _all_spans(_merge(spans_to_protobuf([_span_row(started_at=1767225600000000000)], {})))
    assert sp.start_time_unix_nano == 1767225600000000000


def test_spans_unparseable_timestamp_is_omitted():
    (sp,) = _all_spans(_merge(spans_to_protobuf([_span_row(started_at="not-a-date")], {})))
    assert sp.start_time_unix_nano == 0  # field left unset


def test_spans_parent_span_id_hex_becomes_bytes():
    (sp,) = _all_spans(_merge(spans_to_protobuf([_span_row(parent_span_id=PARENT_HEX)], {})))
    assert sp.parent_span_id.hex() == PARENT_HEX


def test_spans_accepts_camelcase_intake_keys():
    row = {"traceId": TRACE_HEX, "spanId": SPAN_HEX, "parentSpanId": PARENT_HEX, "startTimeUnixNano": 123}
    (sp,) = _all_spans(_merge(spans_to_protobuf([row], {})))
    assert sp.trace_id.hex() == TRACE_HEX
    assert sp.parent_span_id.hex() == PARENT_HEX
    assert sp.start_time_unix_nano == 123


def test_spans_each_row_becomes_splittable_resource_spans():
    rows = [_span_row(span_id=format(i, "016x")) for i in range(4)]
    payloads = spans_to_protobuf(rows, {}, max_bytes=1)
    assert len(payloads) == 4  # one resourceSpans per span -> one payload each under tiny budget
    assert len(_all_spans(_merge(payloads))) == 4


def test_spans_empty_rows_yield_no_payloads():
    assert spans_to_protobuf([], {"nemo.experiment.id": "exp-1"}) == []
