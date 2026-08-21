# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenAI-shaped error envelopes for the gateway's OpenAI-compatible surface.

Requests proxied under ``/-/v1/*`` are advertised as OpenAI-compatible, and clients
reach them with the official OpenAI SDKs. Those SDKs read an error body **only**
through its ``error`` key — the Node SDK's ``APIError.generate`` inspects
``body["error"]`` and reports ``"<status> status code (no body)"`` when it is absent —
so FastAPI's ``{"detail": ...}`` arrives as a bare status line with the real message
discarded before any client code can see it.

Error responses on that surface therefore carry **both** keys: ``error`` for the
OpenAI contract and ``detail`` for existing readers of the FastAPI shape. OpenAI
clients ignore unknown top-level keys, so one body serves both. Proxied paths
outside ``/-/v1/*`` and the CRUD routes are untouched and stay ``detail``-only.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

# Bound the response: upstream bodies can be arbitrarily large.
UPSTREAM_BODY_MAX_CHARS = 500

_OPENAI_COMPATIBLE_PREFIX = "v1"

# Error codes reach us inside the message text, not as a field: an adapter raises
# ``AdapterRelayError("claude_relay_unavailable", "...")``, whose rendering is
# "... failed (claude_relay_unavailable): NeMo Relay CLI executable was not found".
_EMBEDDED_CODE_PATTERN = re.compile(r"\(([a-z][a-z0-9_]*)\)\s*:")

_ERROR_TYPE_BY_STATUS = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    409: "conflict_error",
    429: "rate_limit_error",
}

UPSTREAM_ERROR_TYPE = "upstream_error"


def is_openai_compatible_uri(trailing_uri: str) -> bool:
    """Whether *trailing_uri* addresses the OpenAI-compatible surface (``/-/v1/...``)."""
    head, _, _ = trailing_uri.lstrip("/").partition("/")
    return head == _OPENAI_COMPATIBLE_PREFIX


def openai_error_body(message: str, *, error_type: str, code: str | None = None) -> dict[str, Any]:
    """Build the OpenAI error envelope. ``param`` is always null; we never fault a field."""
    return {"error": {"message": message, "type": error_type, "code": code, "param": None}}


def unwrap_upstream_error(body: bytes) -> tuple[str, str | None]:
    """Lift a human message and a machine code out of an upstream agent's error body.

    Agent servers are FastAPI too, so the body is normally ``{"detail": "..."}``; one
    that is already OpenAI-shaped is read directly. Falls back to the decoded text when
    the body is not JSON, or is JSON carrying none of the fields we recognize. The
    returned message is truncated; the caller can embed it without further bounding.
    """
    text = body.decode(errors="replace")
    try:
        parsed: Any = json.loads(text)
    except ValueError:
        return _truncate(text), None

    message: str | None = None
    code: str | None = None

    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            message = _first_str(error, "message", "detail")
            code = _first_str(error, "code")
        elif isinstance(error, str):
            message = error or None
        if message is None:
            message = _first_str(parsed, "detail", "message")
        if code is None:
            code = _first_str(parsed, "code")
    elif isinstance(parsed, str):
        message = parsed or None

    if message is None:
        message = text
    return _truncate(message), code or _embedded_code(message)


class UpstreamAgentError(HTTPException):
    """A proxied agent returned 5xx; the gateway reports 502 Bad Gateway.

    Carries the unwrapped upstream message and code alongside the status so the
    OpenAI-compatible surface can render them without re-parsing ``detail``, which
    keeps its historical wrapped form for readers of the FastAPI shape.
    """

    def __init__(self, upstream_status: int, body: bytes) -> None:
        self.upstream_status = upstream_status
        self.openai_message, self.openai_code = unwrap_upstream_error(body)
        super().__init__(
            status_code=502,
            detail=f"Agent returned {upstream_status}: {_truncate(body.decode(errors='replace'))}",
        )


def openai_error_response(exc: HTTPException) -> JSONResponse:
    """Render *exc* with the OpenAI ``error`` envelope and FastAPI's ``detail`` side by side."""
    if isinstance(exc, UpstreamAgentError):
        message, code, error_type = exc.openai_message, exc.openai_code, UPSTREAM_ERROR_TYPE
    else:
        message, code, error_type = _detail_message(exc.detail), None, _error_type(exc.status_code)

    content = openai_error_body(message, error_type=error_type, code=code)
    content["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


def _error_type(status_code: int) -> str:
    if (known := _ERROR_TYPE_BY_STATUS.get(status_code)) is not None:
        return known
    return "invalid_request_error" if status_code < 500 else "server_error"


def _detail_message(detail: Any) -> str:
    return detail if isinstance(detail, str) else json.dumps(detail, default=str)


def _first_str(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _embedded_code(message: str) -> str | None:
    match = _EMBEDDED_CODE_PATTERN.search(message)
    return match.group(1) if match else None


def _truncate(text: str) -> str:
    return text[:UPSTREAM_BODY_MAX_CHARS]
