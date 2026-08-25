# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP plumbing for the CLI: a reusable httpx client and error handling.

The control-plane API speaks JSON under a ``/v1`` prefix and reports failures
with an envelope ``{"error": {"code", "message", "details"}}`` (wrapped in
FastAPI's ``detail`` for raised errors). Helpers here turn non-2xx responses
and network faults into ``click.ClickException`` so the CLI exits non-zero with
a clean message and no traceback.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import click
import httpx

DEFAULT_BASE_URL = "http://localhost:8080"
TIMEOUT = 30.0


class ApiError(click.ClickException):
    """Structured control-plane error exposed as a normal Click failure."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _error(resp: httpx.Response) -> ApiError:
    message = _format_error(resp)
    code = None
    try:
        body = resp.json()
        if isinstance(body, dict):
            error = body.get("error")
            if error is None and isinstance(body.get("detail"), dict):
                error = body["detail"].get("error")
            if isinstance(error, dict) and isinstance(error.get("code"), str):
                code = error["code"]
    except (json.JSONDecodeError, ValueError):
        pass
    return ApiError(message, code=code)


def make_client(
    base_url: str,
    token: str | None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """Build the single client reused for every API call in one invocation.

    The ``/v1`` prefix is baked into ``base_url`` so commands pass bare paths
    like ``/tasks``. ``transport`` is an injection seam for tests.

    The token rides as a client-level header, so it is materialized on every
    request this client builds — including ones aimed at presigned object-store
    URLs, where a stray ``Authorization`` can clash with the URL's own
    signature. The presigned helpers below each pop it back off for that reason.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(
        base_url=f"{base_url.rstrip('/')}/v1",
        headers=headers,
        timeout=TIMEOUT,
        transport=transport,
    )


def _format_error(resp: httpx.Response) -> str:
    """Render a non-2xx response as a concise one-or-more-line message."""
    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.text.strip() or f"HTTP {resp.status_code}"

    err = None
    if isinstance(body, dict):
        # Either a bare envelope or one wrapped in FastAPI's ``detail``.
        err = body.get("error")
        if err is None and isinstance(body.get("detail"), dict):
            err = body["detail"].get("error")
        if err is None and body.get("detail") is not None:
            # Pydantic 422 and the like: ``detail`` is a list/string.
            return f"HTTP {resp.status_code}: {json.dumps(body['detail'])}"

    if isinstance(err, dict):
        code = err.get("code", "error")
        message = err.get("message", "")
        text = f"{code}: {message}" if message else str(code)
        if err.get("details"):
            text += f"\n{json.dumps(err['details'], indent=2)}"
        return text

    return f"HTTP {resp.status_code}: {json.dumps(body)}"


def request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Issue an API request, returning parsed JSON or raising ClickException."""
    try:
        resp = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"request to {path} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise _error(resp)
    return resp.json() if resp.content else {}


def upload_file(client: httpx.Client, upload: dict[str, Any], path: Path) -> None:
    """Send a local file to a presigned upload target per its ``upload`` block.

    Honors the server-supplied method/url/headers verbatim. The presigned URL
    is self-authenticating, so the API bearer token is stripped — sending it to
    object storage can clash with the URL's signature.
    """
    url = upload.get("url")
    if not url:
        raise click.ClickException("response has no upload url")
    size_bytes = path.stat().st_size
    headers = dict(upload.get("headers", {}))
    if upload.get("mode") == "gcs_resumable":
        if size_bytes == 0:
            headers["Content-Range"] = "bytes */0"
        else:
            headers["Content-Range"] = f"bytes 0-{size_bytes - 1}/{size_bytes}"
    try:
        with path.open("rb") as source:
            req = client.build_request(
                upload.get("method", "PUT"),
                url,
                content=source,
                headers=headers,
            )
            req.headers["content-length"] = str(size_bytes)
            req.headers.pop("authorization", None)
            resp = client.send(req)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"upload to {url} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise _error(resp)


def upload_multipart_archive(
    client: httpx.Client,
    upload_url: str,
    path: Path,
) -> dict[str, Any]:
    """Upload an archive to an external multipart endpoint without API auth."""
    try:
        with path.open("rb") as source:
            request_ = client.build_request(
                "POST",
                upload_url,
                files={"archive": (path.name, source, "application/gzip")},
            )
            request_.headers.pop("authorization", None)
            response = client.send(request_, auth=None)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"upload to {upload_url} failed: {exc}") from exc
    if response.status_code >= 400:
        raise _error(response)
    payload = response.json()
    if not isinstance(payload, dict):
        raise click.ClickException("Harbor Viewer upload returned a non-object response")
    return payload


def download_artifact(client: httpx.Client, api_path: str, dest: Path) -> None:
    """Download an artifact, following the API's presigned redirect to storage.

    The artifact route answers with a 307 to a presigned GET URL. As with
    uploads, the presigned URL is self-authenticating, so the API bearer token
    is stripped before fetching from object storage.
    """
    try:
        response = client.send(client.build_request("GET", api_path), stream=True)
        if response.is_redirect:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise click.ClickException("artifact redirect carried no location")
            request_ = client.build_request("GET", location)
            request_.headers.pop("authorization", None)
            response = client.send(request_, stream=True)
        _stream_response_to_file(response, dest)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"download of {api_path} failed: {exc}") from exc


def fetch_artifact(client: httpx.Client, api_path: str) -> bytes:
    """Fetch an artifact body, following the API's presigned redirect."""
    try:
        resp = client.get(api_path)
        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                raise click.ClickException("artifact redirect carried no location")
            req = client.build_request("GET", location)
            req.headers.pop("authorization", None)
            resp = client.send(req)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"download of {api_path} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise _error(resp)
    return resp.content


def download_presigned(client: httpx.Client, download: dict[str, Any], dest: Path) -> None:
    """Download from a presigned API response without forwarding API auth."""
    url = download.get("url")
    if not url:
        raise click.ClickException("response has no download url")
    req = client.build_request(download.get("method", "GET"), url)
    if httpx.URL(url).is_absolute_url:
        req.headers.pop("authorization", None)
    try:
        resp = client.send(req, stream=True)
        _stream_response_to_file(resp, dest)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"download from {url} failed: {exc}") from exc


def _stream_response_to_file(response: httpx.Response, dest: Path) -> None:
    """Atomically stream a response to ``dest`` without retaining it in memory."""
    if response.status_code >= 400:
        response.read()
        error = _error(response)
        response.close()
        raise error
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{dest.name}.", dir=dest.parent, delete=False) as output:
            temp_path = Path(output.name)
            for chunk in response.iter_bytes():
                output.write(chunk)
        os.replace(temp_path, dest)
        temp_path = None
    finally:
        response.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def emit(data: dict[str, Any], as_json: bool, summary: list[str]) -> None:
    """Print raw JSON for scripting, or a concise human summary otherwise."""
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for line in summary:
            click.echo(line)


def emit_list(envelope: dict[str, Any], as_json: bool, row: Any) -> None:
    """Print a list envelope: raw JSON, or one ``row(item)`` line per element.

    Surfaces ``next_cursor`` (when present) so scripts/users can page.
    """
    if as_json:
        click.echo(json.dumps(envelope, indent=2))
        return
    items = envelope.get("data", [])
    if not items:
        click.echo("(none)")
    for item in items:
        click.echo(row(item))
    if envelope.get("next_cursor"):
        click.echo(f"next_cursor: {envelope['next_cursor']}")


def load_arg(raw: str) -> str:
    """Resolve a value that may be inline or an ``@file`` reference."""
    if raw.startswith("@"):
        return Path(raw[1:]).read_text()
    return raw


def iter_sse(client: httpx.Client, path: str) -> Iterator[tuple[str, str]]:
    """Yield ``(event, data)`` pairs from a text/event-stream endpoint."""
    try:
        with client.stream("GET", path) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise _error(resp)
            event = "message"
            data: list[str] = []
            for line in resp.iter_lines():
                if line == "":
                    if data:
                        yield event, "\n".join(data)
                    event = "message"
                    data = []
                    continue
                if line.startswith(":"):
                    continue
                field, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if field == "event":
                    event = value
                elif field == "data":
                    data.append(value)
            if data:
                yield event, "\n".join(data)
    except httpx.HTTPError as exc:
        raise click.ClickException(f"stream {path} failed: {exc}") from exc
