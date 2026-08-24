# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Dependency-free, read-only HTTP access to Intake."""

import ipaddress
import json
import os
from collections.abc import Iterator, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class IntakeError(RuntimeError):
    """An Intake read failed with guidance for the next action."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _is_loopback(hostname: str) -> bool:
    if hostname.rstrip(".").lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _validated_origin(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url.strip())
        hostname = parsed.hostname
        _ = parsed.port  # Evaluated because a malformed port only raises on access.
    except ValueError as exc:
        raise ValueError(f"NMP_BASE_URL is invalid: {exc}") from exc
    if not hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("NMP_BASE_URL must use HTTPS, or HTTP for a loopback target.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("NMP_BASE_URL must not contain userinfo.")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("NMP_BASE_URL must contain an origin without a path, query, or fragment.")
    if parsed.scheme == "http" and not _is_loopback(hostname):
        raise ValueError("Remote NMP_BASE_URL targets must use HTTPS.")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _deep_items(name: str, value: Any) -> Iterator[tuple[str, str]]:
    if value is None:
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _deep_items(f"{name}[{key}]", child)
        return
    if isinstance(value, list | tuple):
        if not value:
            raise ValueError(f"{name} must not be empty because omitting it would broaden the query.")
        for child in value:
            child_items = list(_deep_items(name, child))
            if not child_items:
                raise ValueError(f"{name} must not be empty because omitting it would broaden the query.")
            yield from child_items
        return
    if isinstance(value, bool):
        yield name, str(value).lower()
        return
    yield name, str(value)


def encode_query(params: Mapping[str, Any]) -> str:
    """Encode mappings as the deep-object query format that Intake accepts."""
    items: list[tuple[str, str]] = []
    for name, value in params.items():
        if isinstance(value, Mapping):
            items.extend(_deep_items(name, value))
        elif isinstance(value, list | tuple):
            items.extend(_deep_items(name, value))
        elif value is not None:
            items.append((name, str(value)))
    return urlencode(items)


class IntakeClient:
    """Make authenticated, no-redirect GET requests to one Intake workspace."""

    def __init__(
        self,
        base_url: str,
        workspace: str,
        *,
        access_token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not workspace:
            raise ValueError("workspace must not be empty.")
        self.base_url = _validated_origin(base_url)
        self.workspace = workspace
        self.access_token = access_token
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect())

    @classmethod
    def from_env(cls, workspace: str, *, timeout: float = 30.0) -> "IntakeClient":
        base_url = os.environ.get("NMP_BASE_URL")
        if not base_url:
            raise ValueError("Set NMP_BASE_URL to the Platform origin.")
        return cls(
            base_url,
            workspace,
            access_token=os.environ.get("NMP_ACCESS_TOKEN"),
            timeout=timeout,
        )

    def _url(self, endpoint: str, params: Mapping[str, Any]) -> str:
        path = f"/apis/intake/v2/workspaces/{quote(self.workspace, safe='')}/{endpoint.lstrip('/')}"
        query = encode_query(params)
        return f"{self.base_url}{path}" + (f"?{query}" if query else "")

    def get(self, endpoint: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return one decoded JSON object from a read-only Intake endpoint."""
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        request = Request(self._url(endpoint, params or {}), headers=headers, method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = response.read()
        except HTTPError as exc:
            raise self._http_error(exc, endpoint) from exc
        except URLError as exc:
            raise IntakeError(
                f"Reading Intake failed: the Platform is unreachable at {self.base_url}. "
                "Check NMP_BASE_URL and that the services are running."
            ) from exc
        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntakeError(f"Intake returned invalid JSON while reading {endpoint}.") from exc
        if not isinstance(decoded, dict):
            raise IntakeError(f"Intake returned a {type(decoded).__name__}, but {endpoint} must return an object.")
        return decoded

    def _http_error(self, exc: HTTPError, endpoint: str) -> IntakeError:
        detail = _error_detail(exc)
        if 300 <= exc.code < 400:
            return IntakeError(
                f"Reading Intake refused HTTP {exc.code} redirect from {endpoint}. "
                "Set NMP_BASE_URL to the final Platform origin."
            )
        if exc.code in {401, 403}:
            return IntakeError(
                "Credentials were rejected. Refresh NMP_ACCESS_TOKEN, then confirm that "
                f"NMP_BASE_URL owns workspace '{self.workspace}'."
            )
        if exc.code == 404:
            return IntakeError(
                f"Intake returned 404 for workspace '{self.workspace}'. Confirm the workspace and trace ID."
            )
        if exc.code in {400, 422}:
            return IntakeError(
                f"Intake rejected the query with HTTP {exc.code}: {detail}. Check the filter fields and operators."
            )
        return IntakeError(f"Intake returned HTTP {exc.code} while reading {endpoint}: {detail}.")

    def drain(
        self,
        endpoint: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Read page-based results, preserving the caller's row limit."""
        rows: list[dict[str, Any]] = []
        page = 1
        truncated = False
        while True:
            page_params = {**(params or {}), "page": page}
            response = self.get(endpoint, page_params)
            data = response.get("data")
            pagination = response.get("pagination")
            if not isinstance(data, list) or not isinstance(pagination, dict):
                raise IntakeError(f"Intake returned an invalid page while reading {endpoint}.")
            if any(not isinstance(row, dict) for row in data):
                raise IntakeError(f"Intake returned a non-object row while reading {endpoint}.")

            remaining = len(data) if limit is None else max(0, limit - len(rows))
            rows.extend(data[:remaining])
            total_results = pagination.get("total_results")
            total_pages = pagination.get("total_pages", page)
            if limit is not None and len(rows) >= limit:
                truncated = (
                    len(data) > remaining
                    or (isinstance(total_results, int) and total_results > len(rows))
                    or (isinstance(total_pages, int) and page < total_pages)
                )
                break
            if not isinstance(total_pages, int) or page >= total_pages:
                break
            page += 1
        return rows, truncated


def _error_detail(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return exc.reason or "request failed"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
    return str(payload)
