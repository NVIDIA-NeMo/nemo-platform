# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the GitHub storage backend."""

from collections.abc import AsyncIterator, Callable
from unittest.mock import patch

import pytest
from nmp.common.api.common import SecretRef
from nmp.core.files.app.backends.base import ByteRange
from nmp.core.files.app.backends.factory import storage_impl_factory
from nmp.core.files.app.backends.github import (
    GithubAccessError,
    GithubBackendError,
    GithubConfigError,
    GithubStorageConfig,
    GithubStorageImpl,
    GithubUnavailableError,
    raise_for_github_status,
)
from nmp.core.files.exceptions import NotFoundError


class _FakeContent:
    def __init__(self, chunks: tuple[bytes, ...]):
        self._chunks = chunks

    async def iter_chunked(self, _size: int) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class _FakeResponse:
    def __init__(self, status=200, json_body=None, chunks=(), headers=None):
        self.status = status
        self.headers = headers or {}
        self.content = _FakeContent(chunks)
        self._json_body = json_body

    async def json(self):
        return self._json_body


class _FakeRequest:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, *_exc) -> bool:
        return False


class _FakeSession:
    def __init__(self, handler: Callable[[str], _FakeResponse]):
        self._handler = handler
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str] | None = None) -> _FakeRequest:
        self.requests.append((url, headers or {}))
        return _FakeRequest(self._handler(url))


def _session_for(handler: Callable[[str], _FakeResponse]) -> _FakeSession:
    return _FakeSession(handler)


def _tree(*entries: dict, truncated: bool = False) -> dict:
    return {"truncated": truncated, "tree": list(entries)}


def _blob(path: str, size: int = 1) -> dict:
    return {"path": path, "type": "blob", "size": size}


def _config(**overrides) -> GithubStorageConfig:
    return GithubStorageConfig(owner="acme", repo="agents", **{"revision": "main", **overrides})


def _impl(config: GithubStorageConfig | None = None, secrets: dict[str, str] | None = None) -> GithubStorageImpl:
    return GithubStorageImpl(config or _config(), secrets if secrets is not None else {})


class TestRaiseForGithubStatus:
    def test_success_statuses_do_not_raise(self):
        raise_for_github_status(200, "repo")
        raise_for_github_status(206, "repo")

    def test_missing_or_invisible_repository_is_a_config_error(self):
        with pytest.raises(GithubConfigError, match="cannot see it"):
            raise_for_github_status(404, "repository acme/agents")

    def test_forbidden_is_an_access_error(self):
        with pytest.raises(GithubAccessError):
            raise_for_github_status(403, "repository acme/agents")

    def test_exhausted_rate_limit_is_unavailable_not_access_denied(self):
        with pytest.raises(GithubUnavailableError, match="rate limit"):
            raise_for_github_status(403, "repository acme/agents", {"x-ratelimit-remaining": "0"})

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    def test_server_side_failures_are_unavailable(self, status: int):
        with pytest.raises(GithubUnavailableError):
            raise_for_github_status(status, "repository acme/agents")

    def test_other_client_errors_are_backend_errors(self):
        with pytest.raises(GithubBackendError, match="418"):
            raise_for_github_status(418, "repository acme/agents")


class TestResolveConfig:
    @pytest.mark.asyncio
    async def test_pins_the_revision_to_a_commit_sha(self):
        session = _session_for(lambda _url: _FakeResponse(json_body={"sha": "abc123"}))
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            resolved = await _impl().resolve_config()

        assert resolved.revision == "abc123"
        assert resolved.original_revision == "main"
        assert session.requests[0][0].endswith("/repos/acme/agents/commits/main")

    @pytest.mark.asyncio
    async def test_keeps_the_first_original_revision_across_resolutions(self):
        session = _session_for(lambda _url: _FakeResponse(json_body={"sha": "def456"}))
        config = _config(revision="abc123", original_revision="main")
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            resolved = await GithubStorageImpl(config, {}).resolve_config()

        assert resolved.original_revision == "main"

    @pytest.mark.asyncio
    async def test_rejects_a_response_carrying_no_sha(self):
        session = _session_for(lambda _url: _FakeResponse(json_body={}))
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            with pytest.raises(GithubConfigError, match="no commit SHA"):
                await _impl().resolve_config()


class TestListFiles:
    @pytest.mark.asyncio
    async def test_returns_blobs_and_skips_trees(self):
        session = _session_for(
            lambda _url: _FakeResponse(
                json_body=_tree(
                    _blob("agent.yaml", 80),
                    {"path": "mcps", "type": "tree"},
                    _blob("mcps/calculator.py", 20),
                )
            )
        )
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            files = await _impl().list_files()

        assert [(f.path, f.size) for f in files] == [("agent.yaml", 80), ("mcps/calculator.py", 20)]

    @pytest.mark.asyncio
    async def test_strips_the_configured_directory_prefix(self):
        session = _session_for(
            lambda _url: _FakeResponse(
                json_body=_tree(
                    _blob("agents/calc/agent.yaml"),
                    _blob("agents/other/agent.yaml"),
                    _blob("README.md"),
                )
            )
        )
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            files = await _impl(_config(path="agents/calc")).list_files()

        assert [f.path for f in files] == ["agent.yaml"]

    @pytest.mark.asyncio
    async def test_filters_to_a_requested_subpath(self):
        session = _session_for(
            lambda _url: _FakeResponse(json_body=_tree(_blob("agent.yaml"), _blob("mcps/calculator.py")))
        )
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            files = await _impl().list_files("mcps")

        assert [f.path for f in files] == ["mcps/calculator.py"]

    @pytest.mark.asyncio
    async def test_raises_not_found_for_a_subpath_with_no_blobs(self):
        session = _session_for(lambda _url: _FakeResponse(json_body=_tree(_blob("agent.yaml"))))
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            with pytest.raises(NotFoundError):
                await _impl().list_files("nope")

    @pytest.mark.asyncio
    async def test_refuses_a_tree_github_could_not_list_in_full(self):
        session = _session_for(lambda _url: _FakeResponse(json_body=_tree(_blob("agent.yaml"), truncated=True)))
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            with pytest.raises(GithubConfigError, match="too large"):
                await _impl().list_files()

    @pytest.mark.asyncio
    async def test_maps_a_404_onto_a_config_error(self):
        session = _session_for(lambda _url: _FakeResponse(status=404))
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            with pytest.raises(GithubConfigError):
                await _impl().list_files()


class TestDownload:
    async def _collect(self, impl: GithubStorageImpl, session: _FakeSession, byte_range=None) -> bytes:
        with patch("nmp.core.files.app.backends.github.get_http_session", return_value=session):
            stream = await impl.download("agent.yaml", byte_range)
            return b"".join([chunk async for chunk in stream])

    @pytest.mark.asyncio
    async def test_streams_file_contents_at_the_pinned_revision(self):
        session = _session_for(lambda _url: _FakeResponse(chunks=(b"name: ", b"calc\n")))
        body = await self._collect(_impl(_config(revision="abc123")), session)

        assert body == b"name: calc\n"
        url, headers = session.requests[0]
        assert url.endswith("/repos/acme/agents/contents/agent.yaml?ref=abc123")
        assert headers["Accept"] == "application/vnd.github.raw"

    @pytest.mark.asyncio
    async def test_sends_the_token_for_a_private_repository(self):
        session = _session_for(lambda _url: _FakeResponse(chunks=(b"x",)))
        await self._collect(_impl(secrets={"token": "ghp_secret"}), session)

        assert session.requests[0][1]["Authorization"] == "Bearer ghp_secret"

    @pytest.mark.asyncio
    async def test_omits_authorization_without_a_token(self):
        session = _session_for(lambda _url: _FakeResponse(chunks=(b"x",)))
        await self._collect(_impl(), session)

        assert "Authorization" not in session.requests[0][1]

    @pytest.mark.asyncio
    async def test_prefixes_the_configured_directory(self):
        session = _session_for(lambda _url: _FakeResponse(chunks=(b"x",)))
        await self._collect(_impl(_config(path="agents/calc")), session)

        assert "/contents/agents/calc/agent.yaml?ref=" in session.requests[0][0]

    @pytest.mark.asyncio
    async def test_forwards_a_byte_range(self):
        session = _session_for(lambda _url: _FakeResponse(status=206, chunks=(b"me",)))
        await self._collect(_impl(), session, ByteRange(start=2, end=3))

        assert session.requests[0][1]["Range"] == "bytes=2-3"

    @pytest.mark.asyncio
    async def test_maps_a_denied_download_onto_an_access_error(self):
        session = _session_for(lambda _url: _FakeResponse(status=403))
        with pytest.raises(GithubAccessError):
            await self._collect(_impl(), session)


class TestStorageContract:
    @pytest.mark.asyncio
    async def test_upload_and_delete_are_refused(self):
        impl = _impl()
        with pytest.raises(NotImplementedError):
            await impl.upload("agent.yaml", iter(()), None)
        with pytest.raises(NotImplementedError):
            await impl.delete("agent.yaml")

    def test_the_platform_does_not_own_the_source_data(self):
        assert _config().owns_storage_data is False

    @pytest.mark.asyncio
    async def test_cache_key_is_scoped_to_the_revision(self):
        impl = _impl(_config(revision="abc123"))

        assert await impl.get_cache_path_key() == "cache/github/acme/agents/abc123"
        assert await impl.get_cache_path_key("agent.yaml") == "cache/github/acme/agents/abc123/agent.yaml"

    @pytest.mark.asyncio
    async def test_cache_keys_of_two_revisions_do_not_collide(self):
        first = await _impl(_config(revision="abc")).get_cache_path_key("agent.yaml")
        second = await _impl(_config(revision="def")).get_cache_path_key("agent.yaml")

        assert first != second

    def test_the_factory_builds_the_github_backend(self):
        impl = storage_impl_factory(_config(), {"token": "ghp_secret"})

        assert isinstance(impl, GithubStorageImpl)
        assert impl.secrets == {"token": "ghp_secret"}

    def test_config_declares_its_token_secret(self):
        config = _config(token_secret=SecretRef("github-pat"))

        assert config.get_secret_references() == {"token": SecretRef("github-pat")}

    def test_config_without_a_token_declares_no_secret(self):
        assert _config().get_secret_references() == {}

    def test_config_normalizes_a_slash_wrapped_path(self):
        assert _config(path="/agents/calc/").path == "agents/calc"


class TestValidateStorage:
    @pytest.mark.asyncio
    async def test_rejects_a_host_outside_the_allowlist(self):
        impl = _impl(_config(api_base_url="https://github.internal.example.com/api/v3"))
        with pytest.raises(Exception, match="not"):
            await impl.validate_storage()
