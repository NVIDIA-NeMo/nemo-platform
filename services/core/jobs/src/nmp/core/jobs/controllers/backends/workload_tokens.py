# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for controller-managed workload identity subject tokens."""

from __future__ import annotations

import io
import json
import logging
import tarfile
import threading
import time
from dataclasses import dataclass, field
from ipaddress import ip_address
from math import isfinite
from typing import Callable, Protocol
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SUBJECT_TOKEN_TTL_SECONDS = 600
DEFAULT_SUBJECT_TOKEN_REFRESH_MARGIN_SECONDS = 60
DEFAULT_SUBJECT_TOKEN_FAILURE_BACKOFF_MAX_SECONDS = 60.0
DEFAULT_SUBJECT_TOKEN_STOP_TIMEOUT_SECONDS = 5.0


def _is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_token_endpoint(token_endpoint: str) -> None:
    parsed = urlparse(token_endpoint)
    scheme = parsed.scheme.lower()
    if scheme == "https" and parsed.netloc:
        return
    if scheme == "http" and _is_loopback_host(parsed.hostname):
        return
    raise RuntimeError(
        "Invalid Docker workload identity token_endpoint configuration: "
        "token_endpoint must use https://, except http:// is allowed for loopback hosts only"
    )


@dataclass(frozen=True)
class SubjectToken:
    """Issued workload identity subject token and its refresh deadline metadata."""

    value: str
    expires_at: float

    def seconds_until_refresh(self, margin_seconds: int) -> float:
        return max(0.0, self.expires_at - time.time() - margin_seconds)


class SubjectTokenIssuer(Protocol):
    """Issues a subject token suitable for SDK RFC 8693 token exchange."""

    def issue(self) -> SubjectToken: ...


@dataclass(frozen=True)
class OAuthPasswordGrantSubjectTokenIssuer:
    """Demo issuer that obtains a short-lived subject token with OAuth password grant."""

    token_endpoint: str
    client_id: str
    username: str
    password: str = field(repr=False)
    client_secret: str | None = field(default=None, repr=False)
    scope: str | None = None
    default_expires_in_seconds: int = DEFAULT_SUBJECT_TOKEN_TTL_SECONDS
    timeout: float = 30.0

    def issue(self) -> SubjectToken:
        _validate_token_endpoint(self.token_endpoint)
        data = {
            "grant_type": "password",
            "client_id": self.client_id,
            "username": self.username,
            "password": self.password,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        if self.scope:
            data["scope"] = self.scope

        response = httpx.post(self.token_endpoint, data=data, timeout=self.timeout)
        if response.status_code != 200:
            error_data: dict[str, object] = {}
            if response.headers.get("content-type", "").startswith("application/json"):
                try:
                    payload = response.json()
                except (json.JSONDecodeError, ValueError):
                    payload = {}
                if isinstance(payload, dict):
                    error_data = payload
            error = error_data.get("error", "unknown_error")
            description = error_data.get("error_description", response.text)
            raise RuntimeError(f"Failed to issue workload subject token: {error} - {description}")

        try:
            token_data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(
                "Failed to issue workload subject token: invalid_response - "
                "Token endpoint response was not a JSON object"
            ) from exc
        if not isinstance(token_data, dict):
            raise RuntimeError(
                "Failed to issue workload subject token: invalid_response - "
                "Token endpoint response was not a JSON object"
            )

        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise RuntimeError(
                "Failed to issue workload subject token: invalid_response - "
                "Token endpoint response did not include a non-empty access_token"
            )

        if "expires_in" in token_data:
            expires_in = token_data["expires_in"]
            if (
                isinstance(expires_in, bool)
                or not isinstance(expires_in, int | float)
                or not isfinite(expires_in)
                or expires_in <= 0
            ):
                raise RuntimeError(
                    "Failed to issue workload subject token: invalid_response - "
                    "Token endpoint response did not include a positive numeric expires_in"
                )
        else:
            expires_in = self.default_expires_in_seconds
        return SubjectToken(value=access_token, expires_at=time.time() + expires_in)


def build_token_archive(token: str, *, name: str = "token.tmp") -> io.BytesIO:
    """Build a tar archive containing one token file."""
    data = token.encode("utf-8")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo(name=name)
        info.size = len(data)
        info.mode = 0o400
        tar.addfile(info, io.BytesIO(data))
    archive.seek(0)
    return archive


class SubjectTokenRefreshLoop:
    """Background refresher for a controller-owned workload subject token file."""

    def __init__(
        self,
        *,
        issuer: SubjectTokenIssuer,
        write_token: Callable[[str], None],
        refresh_margin_seconds: int = DEFAULT_SUBJECT_TOKEN_REFRESH_MARGIN_SECONDS,
        min_sleep_seconds: float = 1.0,
        max_failure_backoff_seconds: float = DEFAULT_SUBJECT_TOKEN_FAILURE_BACKOFF_MAX_SECONDS,
    ) -> None:
        self._issuer = issuer
        self._write_token = write_token
        self._refresh_margin_seconds = refresh_margin_seconds
        self._min_sleep_seconds = min_sleep_seconds
        self._max_failure_backoff_seconds = max(min_sleep_seconds, max_failure_backoff_seconds)
        self._stop_timeout_seconds = DEFAULT_SUBJECT_TOKEN_STOP_TIMEOUT_SECONDS
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="nmp-workload-token-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return

        thread.join(timeout=self._stop_timeout_seconds)
        if thread.is_alive():
            raise RuntimeError("Timed out stopping workload identity subject token refresher")
        self._thread = None

    def refresh_once(self) -> SubjectToken:
        token = self._issuer.issue()
        self._write_token(token.value)
        return token

    def _refresh_once_for_worker(self) -> SubjectToken | None:
        token = self._issuer.issue()
        if self._stop.is_set():
            return None
        self._write_token(token.value)
        return token

    def _run(self) -> None:
        token: SubjectToken | None = None
        failure_sleep_seconds = self._min_sleep_seconds
        while not self._stop.is_set():
            try:
                token = self._refresh_once_for_worker()
            except Exception:
                logger.exception("Failed to refresh workload identity subject token")
                if self._stop.wait(failure_sleep_seconds):
                    return
                failure_sleep_seconds = min(self._max_failure_backoff_seconds, failure_sleep_seconds * 2)
                continue
            if token is None:
                return

            failure_sleep_seconds = self._min_sleep_seconds
            sleep_seconds = max(self._min_sleep_seconds, token.seconds_until_refresh(self._refresh_margin_seconds))
            self._stop.wait(sleep_seconds)
