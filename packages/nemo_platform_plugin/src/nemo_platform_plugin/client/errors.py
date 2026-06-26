# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP error hierarchy for the NemoClient.

Status-code-specific subclasses also inherit from the corresponding
Stainless SDK exception so that existing ``except ConflictError``
(imported from ``nemo_platform``) catches our exceptions too.

TODO: Once all consumers import from ``nemo_platform_plugin.client.errors``,
remove the Stainless base classes.
"""

from __future__ import annotations

import httpx


class NemoHTTPError(Exception):
    """Raised on non-2xx HTTP responses.

    Attributes:
        http_response: The raw httpx response.
        status_code: The HTTP status code.
        detail: A human-readable error message extracted from the response
            body (``{"detail": "..."}`` convention used by FastAPI / NeMo
            Platform), or the raw response text as a fallback.
        body: The parsed JSON response body, or None.
    """

    def __init__(self, http_response: httpx.Response) -> None:
        self.http_response = http_response
        self.status_code = http_response.status_code
        self.detail = self._extract_detail(http_response)
        self.body = self._extract_body(http_response)
        # Call Exception.__init__ directly to avoid Stainless APIStatusError.__init__
        # which expects different arguments.  Our subclasses inherit from both
        # NemoHTTPError and the Stainless exception for isinstance() compatibility.
        Exception.__init__(self, f"HTTP {self.status_code}: {self.detail}")

    @staticmethod
    def _extract_body(resp: httpx.Response) -> object | None:
        try:
            return resp.json()
        except Exception:
            return None

    @staticmethod
    def _extract_detail(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                return body["detail"]
        except Exception:
            pass
        try:
            return resp.text
        except httpx.ResponseNotRead:
            return f"HTTP {resp.status_code}"


# ---------------------------------------------------------------------------
# Status-code-specific errors
# ---------------------------------------------------------------------------


def _stainless_base(name: str) -> type:
    """Import a Stainless SDK exception by name, falling back to NemoHTTPError."""
    try:
        import nemo_platform._exceptions as exc

        return getattr(exc, name)
    except (ImportError, AttributeError):
        return NemoHTTPError


class BadRequestError(NemoHTTPError, _stainless_base("BadRequestError")):  # type: ignore[misc]
    """HTTP 400"""


class AuthenticationError(NemoHTTPError, _stainless_base("AuthenticationError")):  # type: ignore[misc]
    """HTTP 401"""


class PermissionDeniedError(NemoHTTPError, _stainless_base("PermissionDeniedError")):  # type: ignore[misc]
    """HTTP 403"""


class NotFoundError(NemoHTTPError, _stainless_base("NotFoundError")):  # type: ignore[misc]
    """HTTP 404"""


class ConflictError(NemoHTTPError, _stainless_base("ConflictError")):  # type: ignore[misc]
    """HTTP 409"""


class UnprocessableEntityError(NemoHTTPError, _stainless_base("UnprocessableEntityError")):  # type: ignore[misc]
    """HTTP 422"""


class RateLimitError(NemoHTTPError, _stainless_base("RateLimitError")):  # type: ignore[misc]
    """HTTP 429"""


class InternalServerError(NemoHTTPError, _stainless_base("InternalServerError")):  # type: ignore[misc]
    """HTTP 500+"""


_STATUS_CODE_TO_ERROR: dict[int, type[NemoHTTPError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    429: RateLimitError,
    500: InternalServerError,
}


def raise_for_status(http_response: httpx.Response) -> None:
    """Raise status-code-specific NemoHTTPError subclass for non-2xx responses."""
    if 200 <= http_response.status_code < 300:
        return
    error_cls = _STATUS_CODE_TO_ERROR.get(http_response.status_code, NemoHTTPError)
    if error_cls is NemoHTTPError and http_response.status_code >= 500:
        error_cls = InternalServerError
    raise error_cls(http_response)
