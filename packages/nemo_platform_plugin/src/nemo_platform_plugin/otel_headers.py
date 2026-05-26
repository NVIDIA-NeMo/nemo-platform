# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Lightweight OTEL header propagation context.

This module holds the request/response header bits of NeMo's observability story
that plugins need at runtime (constants + context-var). The heavy `initialize_obs`
coordinator and OTLP exporters stay in nmp.common.observability — they're
server-side concerns and pull in the full opentelemetry SDK.

Service-side callers can still import these symbols from
``nmp.common.observability.otel`` for backward compatibility.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar, Token
from typing import Dict

INTERNAL_REQUEST_HEADER = "X-NMP-Internal"
MARK_INTERNAL_REQUEST_HEADERS = {INTERNAL_REQUEST_HEADER: "true"}

otel_headers_context: ContextVar[Dict[str, str] | None] = ContextVar("otel_headers_context", default=None)


def set_otel_headers(headers: Dict[str, str]) -> Token[Dict[str, str] | None]:
    """Set headers to propagate through the request chain (e.g., X-NMP-Internal).

    Returns a token that can be passed to ``otel_headers_context.reset()`` to
    restore the previous value.
    """
    return otel_headers_context.set(headers.copy())


def get_otel_headers() -> Dict[str, str]:
    """Return a shallow copy of the propagation headers, or empty dict if none set."""
    headers = otel_headers_context.get()
    return headers.copy() if headers else {}


@contextlib.contextmanager
def scoped_otel_headers(headers: Dict[str, str]) -> Iterator[None]:
    """Context manager that sets propagation headers and resets them on exit.

    Use this instead of bare ``set_otel_headers`` when the caller is not
    request-scoped middleware (which already resets via the token). Prevents
    headers from leaking to unrelated downstream calls in the same async task.
    """
    token = set_otel_headers(headers)
    try:
        yield
    finally:
        otel_headers_context.reset(token)
