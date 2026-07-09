# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AIRCORE-800 first cut: the authenticated caller is stamped onto ingested spans.

Proves attribution at ingest: every span records which agent/user posted it, so you
can later answer "which agent made which calls" by filtering on this attribute.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from nmp.intake.spans.ingest.otlp import (
    CALLER_PRINCIPAL_ATTRIBUTE,
    _resolve_caller_principal,
    _span_to_domain,
)
from opentelemetry.proto.trace.v1.trace_pb2 import Span


def _otlp_span() -> Span:
    return Span(trace_id=b"\x01" * 16, span_id=b"\x02" * 8, name="llm-call")


def test_caller_principal_stamped_on_span():
    dom = _span_to_domain(
        workspace="default",
        span=_otlp_span(),
        resource_attributes={},
        scope_data={},
        ingested_at=datetime.now(timezone.utc),
        caller_principal="svc-nemo-ci",
    )
    assert dom.attributes_string[CALLER_PRINCIPAL_ATTRIBUTE] == "svc-nemo-ci"


def test_no_caller_attribute_when_absent():
    dom = _span_to_domain(
        workspace="default",
        span=_otlp_span(),
        resource_attributes={},
        scope_data={},
        ingested_at=datetime.now(timezone.utc),
        caller_principal="",
    )
    assert CALLER_PRINCIPAL_ATTRIBUTE not in dom.attributes_string


def test_resolve_caller_principal():
    on = SimpleNamespace(auth_enabled=True, principal=SimpleNamespace(id="svc-nemo-ci"))
    off = SimpleNamespace(auth_enabled=False, principal=SimpleNamespace(id="ignored"))
    assert _resolve_caller_principal(on) == "svc-nemo-ci"
    assert _resolve_caller_principal(off) == ""
