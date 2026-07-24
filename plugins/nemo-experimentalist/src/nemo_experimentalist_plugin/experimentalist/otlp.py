# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""OTLP protobuf helpers for reading and uploading JSONL traces."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from google.protobuf.json_format import ParseDict
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import ResourceRef
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

logger = logging.getLogger(__name__)

# Intake rejects OTLP bodies over 5 MiB; pack chunks under a 4 MiB budget to leave
# headroom for protobuf framing so no single request trips the server limit.
_MAX_OTLP_BYTES = 4 * 1024 * 1024


def read_trace_id(ref: ResourceRef) -> str:
    """Return the hex trace_id from the first span in a JSONL trace file.

    Normalises to lowercase hex regardless of whether the JSONL stores the id as
    hex (16/32 hex chars) or base64 (standard or URL-safe), so the result is always
    safe to embed as a URL path component.

    Args:
        ref(ResourceRef): Resource reference to the JSONL trace file.

    Returns:
        str: The lowercase hex trace_id.
    """
    path = Path(urlparse(ref.uri).path)
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        for rs in json.loads(raw).get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                for span in ss.get("spans", []):
                    if tid := span.get("traceId"):
                        if len(tid) in (16, 32) and all(c in "0123456789abcdefABCDEF" for c in tid):
                            return tid.lower()
                        # base64 (standard or URL-safe) → bytes → hex
                        padded = tid.replace("-", "+").replace("_", "/")
                        padded += "=" * (-len(padded) % 4)
                        return base64.b64decode(padded).hex()
    raise ValueError(f"No traceId found in {ref.uri}")


def _to_unix_nano(value: object) -> str | None:
    """Coerce an Intake timestamp (ISO string or epoch number) to unix-nanos string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(int(value))
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return str(int(dt.timestamp() * 1_000_000_000))


def _attr_value(value: object) -> dict:
    """Render a Python value as an OTLP AnyValue dict."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    return {"stringValue": json.dumps(value)}


def _serialize_chunks(resource_spans: list[dict], max_bytes: int) -> list[bytes]:
    """Pack resourceSpans into ExportTraceServiceRequest payloads under *max_bytes* each.

    Re-ingesting OTLP is idempotent per span_id, so splitting one trace's spans across
    several requests is safe: Intake merges them back into the same trace.
    """
    payloads: list[bytes] = []
    batch: list[dict] = []
    for rs in resource_spans:
        batch.append(rs)
        req = ExportTraceServiceRequest()
        ParseDict({"resourceSpans": batch}, req)
        payload = req.SerializeToString()
        if len(payload) > max_bytes and len(batch) > 1:
            batch.pop()
            prev = ExportTraceServiceRequest()
            ParseDict({"resourceSpans": batch}, prev)
            payloads.append(prev.SerializeToString())
            batch = [rs]
    if batch:
        req = ExportTraceServiceRequest()
        ParseDict({"resourceSpans": batch}, req)
        payload = req.SerializeToString()
        if len(payload) > max_bytes:
            logger.warning(
                f"Single span exceeds Intake limit ({len(payload)} > {max_bytes} bytes); upload will likely fail"
            )
        payloads.append(payload)
    return payloads


def spans_to_protobuf(
    span_rows: list[dict], extra_resource_attrs: dict[str, str], max_bytes: int = _MAX_OTLP_BYTES
) -> list[bytes]:
    """Rebuild OTLP ExportTraceServiceRequest payloads from Intake span records.

    Args:
        span_rows(list[dict]): List of span rows from Intake.
        extra_resource_attrs(dict[str, str]): Extra resource attributes to add to the spans.
        max_bytes(int): Maximum bytes per payload.

    Returns:
        list[bytes]: List of OTLP ExportTraceServiceRequest payloads.
    """

    def _hex_b64(val: object) -> str | None:
        s = str(val) if val else ""
        if s and len(s) in (16, 32) and all(c in "0123456789abcdefABCDEF" for c in s):
            return base64.b64encode(bytes.fromhex(s)).decode()
        return s or None

    resource_attrs = [{"key": k, "value": {"stringValue": v}} for k, v in extra_resource_attrs.items()]
    resource_spans: list[dict] = []
    for row in span_rows:
        raw_attrs = row.get("raw_attributes")
        if isinstance(raw_attrs, str):
            try:
                raw_attrs = json.loads(raw_attrs)
            except json.JSONDecodeError:
                raw_attrs = {}
        if not isinstance(raw_attrs, dict):
            raw_attrs = {}

        span: dict = {
            "traceId": _hex_b64(row.get("trace_id") or row.get("traceId")),
            "spanId": _hex_b64(row.get("span_id") or row.get("spanId")),
            "attributes": [{"key": k, "value": _attr_value(v)} for k, v in raw_attrs.items()],
        }
        parent = _hex_b64(row.get("parent_span_id") or row.get("parentSpanId"))
        if parent:
            span["parentSpanId"] = parent
        if name := row.get("name"):
            span["name"] = str(name)
        if start := _to_unix_nano(row.get("started_at") or row.get("startTimeUnixNano")):
            span["startTimeUnixNano"] = start
        if end := _to_unix_nano(row.get("ended_at") or row.get("endTimeUnixNano")):
            span["endTimeUnixNano"] = end
        resource_spans.append({"resource": {"attributes": resource_attrs}, "scopeSpans": [{"spans": [span]}]})

    return _serialize_chunks(resource_spans, max_bytes)


def jsonl_to_protobuf(
    path: Path, extra_resource_attrs: dict[str, str], max_bytes: int = _MAX_OTLP_BYTES
) -> list[bytes]:
    """Merge JSONL spans into OTLP ExportTraceServiceRequest payloads under *max_bytes* each.

    Args:
        path(Path): Path to the JSONL file.
        extra_resource_attrs(dict[str, str]): Extra resource attributes to add to the spans.
        max_bytes(int): Maximum bytes per payload.

    Returns:
        list[bytes]: List of OTLP ExportTraceServiceRequest payloads.
    """
    resource_spans: list[dict] = []
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        for rs in json.loads(raw).get("resourceSpans", []):
            attrs = {a["key"]: a for a in rs.setdefault("resource", {}).setdefault("attributes", [])}
            for key, value in extra_resource_attrs.items():
                attrs[key] = {"key": key, "value": {"stringValue": value}}
            resource = {
                **rs.get("resource", {}),
                "attributes": list(attrs.values()),
            }
            for ss in rs.get("scopeSpans", []):
                scope = ss.get("scope", {})
                for span in ss.get("spans", []):
                    for field in ("traceId", "spanId", "parentSpanId"):
                        val = span.get(field)
                        if val and len(val) in (16, 32) and all(c in "0123456789abcdefABCDEF" for c in val):
                            span[field] = base64.b64encode(bytes.fromhex(val)).decode()
                    # One span per resourceSpan so _serialize_chunks has span-level granularity
                    resource_spans.append({"resource": resource, "scopeSpans": [{"scope": scope, "spans": [span]}]})

    return _serialize_chunks(resource_spans, max_bytes)
