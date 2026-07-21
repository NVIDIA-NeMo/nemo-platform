# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tarfile
import threading
import time

import httpx
import pytest
from nmp.core.jobs.controllers.backends.workload_tokens import (
    OAuthPasswordGrantSubjectTokenIssuer,
    SubjectToken,
    SubjectTokenRefreshLoop,
    build_token_archive,
)


def test_build_token_archive_contains_read_only_token_file() -> None:
    archive = build_token_archive("subject-token", name="token.tmp")

    with tarfile.open(fileobj=archive, mode="r") as tar:
        member = tar.getmember("token.tmp")
        extracted = tar.extractfile(member)

        assert member.mode == 0o400
        assert extracted is not None
        assert extracted.read() == b"subject-token"


def test_oauth_password_grant_issuer_requests_subject_token(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_post(url: str, *, data: dict, timeout: float) -> httpx.Response:
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return httpx.Response(200, json={"access_token": "subject-token", "expires_in": 120})

    monkeypatch.setattr("nmp.core.jobs.controllers.backends.workload_tokens.httpx.post", fake_post)

    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint="https://idp.example.com/token",
        client_id="nemo-platform",
        client_secret="secret",
        username="svc-nemo",
        password="app-password",
        scope="openid email groups",
        timeout=5.0,
    )
    before = time.time()

    token = issuer.issue()

    assert token.value == "subject-token"
    assert token.expires_at >= before + 120
    assert captured == {
        "url": "https://idp.example.com/token",
        "data": {
            "grant_type": "password",
            "client_id": "nemo-platform",
            "client_secret": "secret",
            "username": "svc-nemo",
            "password": "app-password",
            "scope": "openid email groups",
        },
        "timeout": 5.0,
    }


def test_oauth_password_grant_issuer_reports_idp_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, *, data: dict, timeout: float) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "bad credentials"},
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr("nmp.core.jobs.controllers.backends.workload_tokens.httpx.post", fake_post)

    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint="https://idp.example.com/token",
        client_id="nemo-platform",
        username="svc-nemo",
        password="bad-password",
    )

    with pytest.raises(RuntimeError, match="invalid_grant - bad credentials"):
        issuer.issue()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json=["invalid"], headers={"content-type": "application/json"}),
        httpx.Response(400, json="invalid", headers={"content-type": "application/json"}),
        httpx.Response(400, json=None, headers={"content-type": "application/json"}),
        httpx.Response(400, content=b"not-json", headers={"content-type": "application/json"}),
    ],
)
def test_oauth_password_grant_issuer_ignores_non_object_error_json(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response
) -> None:
    def fake_post(url: str, *, data: dict, timeout: float) -> httpx.Response:
        return response

    monkeypatch.setattr("nmp.core.jobs.controllers.backends.workload_tokens.httpx.post", fake_post)

    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint="https://idp.example.com/token",
        client_id="nemo-platform",
        username="svc-nemo",
        password="bad-password",
    )

    with pytest.raises(RuntimeError, match="unknown_error - "):
        issuer.issue()


def test_oauth_password_grant_issuer_rejects_non_loopback_http_before_sending_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(*args, **kwargs) -> httpx.Response:
        raise AssertionError("token endpoint should not be called")

    monkeypatch.setattr("nmp.core.jobs.controllers.backends.workload_tokens.httpx.post", fake_post)

    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint="http://authentik-server:9000/application/o/token/",
        client_id="nemo-platform",
        username="svc-nemo",
        password="app-password",
    )

    with pytest.raises(RuntimeError, match="token_endpoint must use https://"):
        issuer.issue()


@pytest.mark.parametrize("token_endpoint", ["http://localhost:18080/token", "http://127.0.0.1:18080/token"])
def test_oauth_password_grant_issuer_allows_loopback_http_for_local_development(
    monkeypatch: pytest.MonkeyPatch, token_endpoint: str
) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, *, data: dict, timeout: float) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, json={"access_token": "subject-token", "expires_in": 120})

    monkeypatch.setattr("nmp.core.jobs.controllers.backends.workload_tokens.httpx.post", fake_post)

    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint=token_endpoint,
        client_id="nemo-platform",
        username="svc-nemo",
        password="app-password",
    )

    assert issuer.issue().value == "subject-token"
    assert captured["url"] == token_endpoint


def test_oauth_password_grant_issuer_uses_configured_default_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, *, data: dict, timeout: float) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "subject-token"})

    monkeypatch.setattr("nmp.core.jobs.controllers.backends.workload_tokens.httpx.post", fake_post)

    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint="https://idp.example.com/token",
        client_id="nemo-platform",
        username="svc-nemo",
        password="app-password",
        default_expires_in_seconds=45,
    )
    before = time.time()

    token = issuer.issue()

    assert token.value == "subject-token"
    assert token.expires_at >= before + 45


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "Token endpoint response was not a JSON object"),
        ({}, "Token endpoint response did not include a non-empty access_token"),
        ({"access_token": ""}, "Token endpoint response did not include a non-empty access_token"),
        ({"access_token": None}, "Token endpoint response did not include a non-empty access_token"),
        (
            {"access_token": "subject-token", "expires_in": None},
            "Token endpoint response did not include a positive numeric expires_in",
        ),
        (
            {"access_token": "subject-token", "expires_in": "120"},
            "Token endpoint response did not include a positive numeric expires_in",
        ),
        (
            {"access_token": "subject-token", "expires_in": 0},
            "Token endpoint response did not include a positive numeric expires_in",
        ),
        (
            {"access_token": "subject-token", "expires_in": -1},
            "Token endpoint response did not include a positive numeric expires_in",
        ),
        (
            b'{"access_token": "subject-token", "expires_in": NaN}',
            "Token endpoint response did not include a positive numeric expires_in",
        ),
        (
            b'{"access_token": "subject-token", "expires_in": Infinity}',
            "Token endpoint response did not include a positive numeric expires_in",
        ),
        (
            b'{"access_token": "subject-token", "expires_in": -Infinity}',
            "Token endpoint response did not include a positive numeric expires_in",
        ),
        (
            {"access_token": "subject-token", "expires_in": True},
            "Token endpoint response did not include a positive numeric expires_in",
        ),
    ],
)
def test_oauth_password_grant_issuer_rejects_invalid_success_response(
    monkeypatch: pytest.MonkeyPatch, payload: object, message: str
) -> None:
    def fake_post(url: str, *, data: dict, timeout: float) -> httpx.Response:
        if isinstance(payload, bytes):
            return httpx.Response(200, content=payload)
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("nmp.core.jobs.controllers.backends.workload_tokens.httpx.post", fake_post)

    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint="https://idp.example.com/token",
        client_id="nemo-platform",
        username="svc-nemo",
        password="app-password",
    )

    with pytest.raises(RuntimeError, match=f"invalid_response - {message}"):
        issuer.issue()


def test_oauth_password_grant_issuer_repr_excludes_secrets() -> None:
    issuer = OAuthPasswordGrantSubjectTokenIssuer(
        token_endpoint="https://idp.example.com/token",
        client_id="nemo-platform",
        client_secret="super-sensitive-client-secret",
        username="svc-nemo",
        password="super-sensitive-password",
    )

    issuer_repr = repr(issuer)

    assert "client_secret=" not in issuer_repr
    assert "password=" not in issuer_repr
    assert "super-sensitive-client-secret" not in issuer_repr
    assert "super-sensitive-password" not in issuer_repr


def test_refresh_loop_refresh_once_writes_issued_token() -> None:
    class FakeIssuer:
        def issue(self) -> SubjectToken:
            return SubjectToken(value="subject-token", expires_at=time.time() + 120)

    writes: list[str] = []
    refresher = SubjectTokenRefreshLoop(issuer=FakeIssuer(), write_token=writes.append)

    token = refresher.refresh_once()

    assert token.value == "subject-token"
    assert writes == ["subject-token"]


def test_refresh_loop_can_restart_after_stop() -> None:
    class FakeIssuer:
        def __init__(self) -> None:
            self.issued = 0

        def issue(self) -> SubjectToken:
            self.issued += 1
            return SubjectToken(value=f"subject-token-{self.issued}", expires_at=time.time() + 120)

    writes: list[str] = []
    wrote = threading.Event()

    def write_token(token: str) -> None:
        writes.append(token)
        wrote.set()

    refresher = SubjectTokenRefreshLoop(
        issuer=FakeIssuer(),
        write_token=write_token,
        min_sleep_seconds=0.01,
    )

    refresher.start()
    assert wrote.wait(timeout=1)
    refresher.stop()

    wrote.clear()
    refresher.start()
    assert wrote.wait(timeout=1)
    refresher.stop()

    assert writes[:2] == ["subject-token-1", "subject-token-2"]


def test_refresh_loop_stop_timeout_preserves_thread_and_prevents_late_write() -> None:
    issue_started = threading.Event()
    release_issue = threading.Event()
    writes: list[str] = []

    class BlockingIssuer:
        def issue(self) -> SubjectToken:
            issue_started.set()
            if not release_issue.wait(timeout=1):
                raise RuntimeError("issuer was not released")
            return SubjectToken(value="late-subject-token", expires_at=time.time() + 120)

    refresher = SubjectTokenRefreshLoop(
        issuer=BlockingIssuer(),
        write_token=writes.append,
        min_sleep_seconds=0.01,
    )
    refresher._stop_timeout_seconds = 0.01

    refresher.start()
    assert issue_started.wait(timeout=1)

    with pytest.raises(RuntimeError, match="Timed out stopping workload identity subject token refresher"):
        refresher.stop()

    thread = refresher._thread
    assert thread is not None
    assert thread.is_alive()

    release_issue.set()
    thread.join(timeout=1)
    assert not thread.is_alive()

    refresher.stop()

    assert refresher._thread is None
    assert writes == []


def test_refresh_loop_backs_off_failures_and_resets_after_success() -> None:
    class FakeIssuer:
        def __init__(self) -> None:
            self.calls = 0

        def issue(self) -> SubjectToken:
            self.calls += 1
            if self.calls in {1, 2, 3, 5}:
                raise RuntimeError("idp unavailable")
            return SubjectToken(value="subject-token", expires_at=time.time())

    class FakeStop(threading.Event):
        def __init__(self) -> None:
            super().__init__()
            self.waits: list[float] = []
            self.stopped = False

        def is_set(self) -> bool:
            return self.stopped

        def wait(self, timeout: float | None = None) -> bool:
            assert timeout is not None
            self.waits.append(timeout)
            if len(self.waits) == 5:
                self.stopped = True
                return True
            return False

    stop = FakeStop()
    writes: list[str] = []
    refresher = SubjectTokenRefreshLoop(
        issuer=FakeIssuer(),
        write_token=writes.append,
        min_sleep_seconds=1.0,
        max_failure_backoff_seconds=4.0,
    )
    refresher._stop = stop

    refresher._run()

    assert writes == ["subject-token"]
    assert stop.waits == [1.0, 2.0, 4.0, 1.0, 1.0]


def test_subject_token_seconds_until_refresh_never_negative() -> None:
    token = SubjectToken(value="expired", expires_at=time.time() - 10)

    assert token.seconds_until_refresh(margin_seconds=60) == 0.0
