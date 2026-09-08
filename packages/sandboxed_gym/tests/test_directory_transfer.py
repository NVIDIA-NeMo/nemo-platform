# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for directory transfer across the broker (``PUT``/``GET /episodes/{id}/dirs``).

No layer below the broker has a directory primitive -- NeMo-Gym's provider contract is one file at
a time, with no listing call -- so directory transfer is synthesized from ``upload_file`` and
``exec``. These tests cover both halves of that: the archive helpers backends share, and the
endpoints a client sees.
"""

from __future__ import annotations

import base64
import io
import shlex
import tarfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sandboxed_gym.backends.archive import download_dir_via_archive, upload_dir_via_archive
from sandboxed_gym.backends.base import DirectoryTransferError
from sandboxed_gym.backends.memory import InMemoryEpisodeBackend
from sandboxed_gym.config import EpisodeBrokerConfig
from sandboxed_gym.egress import build_egress_policy
from sandboxed_gym.http_app import build_broker_app
from sandboxed_gym.sandbox_types import SandboxExecResult
from sandboxed_gym.wire import BROKER_AUTH_HEADER, BROKER_PROTOCOL_VERSION

TOKEN = "test-broker-token"
APPROVED_IMAGE = "registry.example.com/swe/grader:1.0"


def make_config(**overrides: Any) -> EpisodeBrokerConfig:
    settings: dict[str, Any] = {
        "job_id": "job-1",
        "backend": "memory",
        "allow_insecure_memory_backend": True,
        "approved_images": (APPROVED_IMAGE,),
    }
    settings.update(overrides)
    return EpisodeBrokerConfig(**settings)


def make_archive(entries: dict[str, bytes]) -> bytes:
    """A gzipped tar with ``entries`` as members, named relative to the archive root."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in entries.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def read_archive(archive: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return {
            member.name.removeprefix("./"): (tar.extractfile(member) or io.BytesIO()).read()
            for member in tar.getmembers()
            if member.isfile()
        }


@pytest.fixture
def client() -> Iterator[TestClient]:
    config = make_config()
    backend = InMemoryEpisodeBackend(build_egress_policy(config.egress_allowlist))
    app = build_broker_app(backend=backend, config=config, token=TOKEN)
    with TestClient(app) as test_client:
        test_client.headers.update({BROKER_AUTH_HEADER: TOKEN})
        yield test_client


def create_episode(client: TestClient) -> str:
    response = client.post("/episodes", json={"image": APPROVED_IMAGE})
    assert response.status_code == 201, response.text
    return response.json()["episode_id"]


# --------------------------------------------------------------------------------------------
# Round trip through the endpoints
# --------------------------------------------------------------------------------------------


def test_a_directory_survives_the_round_trip_through_the_broker(client) -> None:
    # The property the endpoints exist for: what a client seeds is what it gets back, with the
    # tree structure intact rather than flattened.
    episode_id = create_episode(client)
    entries = {"run.sh": b"#!/bin/sh\necho hi\n", "nested/data.json": b'{"k": 1}'}

    upload = client.put(
        f"/episodes/{episode_id}/dirs",
        json={"path": "/work", "archive_b64": base64.b64encode(make_archive(entries)).decode()},
    )
    assert upload.status_code == 204, upload.text

    download = client.get(f"/episodes/{episode_id}/dirs", params={"path": "/work"})
    assert download.status_code == 200, download.text

    assert read_archive(base64.b64decode(download.json()["archive_b64"])) == entries


def test_a_relative_directory_path_is_refused(client) -> None:
    # Absolute paths are what the sanitizer can reason about; a relative one resolves against
    # whatever the backend's working directory happens to be.
    episode_id = create_episode(client)

    response = client.get(f"/episodes/{episode_id}/dirs", params={"path": "work/out"})

    assert response.status_code == 400, response.text


def test_an_archive_member_escaping_the_target_is_refused(client) -> None:
    """The archive arrives from the job sandbox, so traversal is an expected thing to try."""
    episode_id = create_episode(client)
    archive = make_archive({"../../etc/passwd": b"root:x:0:0"})

    response = client.put(
        f"/episodes/{episode_id}/dirs",
        json={"path": "/work", "archive_b64": base64.b64encode(archive).decode()},
    )

    assert response.status_code == 502, response.text
    assert "/etc/passwd" not in response.text, "the refusal must not echo the traversal target back"


def test_an_oversized_archive_is_refused_with_the_limit_named() -> None:
    # A directory is the likelier payload to hit the cap, and a caller that cannot see the limit
    # cannot decide whether to split the transfer or raise it. Driven through a backend that
    # returns an oversized archive: the endpoint bounds what it will *serialize*, which is a
    # separate check from the request-body limit on the way in.
    config = make_config(max_request_bytes=512)

    class _BigDownloadBackend(InMemoryEpisodeBackend):
        async def download_dir(self, backend_id: str, path: str) -> bytes:
            return b"x" * 4096

    backend = _BigDownloadBackend(build_egress_policy(config.egress_allowlist))
    app = build_broker_app(backend=backend, config=config, token=TOKEN)
    with TestClient(app) as small_client:
        small_client.headers.update({BROKER_AUTH_HEADER: TOKEN})
        episode_id = create_episode(small_client)

        response = small_client.get(f"/episodes/{episode_id}/dirs", params={"path": "/work"})

    assert response.status_code == 413, response.text
    assert "512" in response.text, "the limit has to be in the message to be actionable"


def test_the_protocol_version_advertises_directory_support(client) -> None:
    # A v2 client talking to a v1 broker gets 404s from /dirs. The version is how it finds out
    # first, so it has to move when the capability does.
    assert BROKER_PROTOCOL_VERSION == "2"
    assert client.get("/health").json()["protocol_version"] == "2"


# --------------------------------------------------------------------------------------------
# The shared archive helpers, which backends without a native transport delegate to
# --------------------------------------------------------------------------------------------


class _FakeBackend:
    """Records exec calls and file writes; fails the command matched by ``fail_substring``."""

    def __init__(self, *, fail_substring: str | None = None, stderr: str = "") -> None:
        self.commands: list[str] = []
        self.files: dict[str, bytes] = {}
        self._fail_substring = fail_substring
        self._stderr = stderr

    async def exec(self, backend_id: str, command: str, **kwargs: Any) -> SandboxExecResult:
        self.commands.append(command)
        if self._fail_substring and self._fail_substring in command:
            return SandboxExecResult(stdout=None, stderr=self._stderr, return_code=2)
        return SandboxExecResult(stdout="", stderr=None, return_code=0)

    async def upload_file(self, backend_id: str, path: str, content: bytes) -> None:
        self.files[path] = content

    async def download_file(self, backend_id: str, path: str) -> bytes:
        return self.files.get(path, b"archive-bytes")


async def test_upload_stages_the_archive_then_extracts_and_cleans_up() -> None:
    backend = _FakeBackend()

    await upload_dir_via_archive(backend, "ep-1", "/work/out", b"tar-bytes")

    staged = next(iter(backend.files))
    assert backend.files[staged] == b"tar-bytes"
    assert f"tar -xzf {staged} -C /work/out" in backend.commands[0]
    assert backend.commands[-1] == f"rm -f {staged}", "the staged archive must not be left behind"


async def test_download_packs_relative_members_so_the_tree_does_not_nest() -> None:
    # `tar -C path .` is what keeps members relative. Packing the path itself would unpack one
    # directory deeper than the caller asked for, which is silent rather than loud.
    backend = _FakeBackend()

    await download_dir_via_archive(backend, "ep-1", "/work/out")

    assert "-C /work/out ." in backend.commands[0]


async def test_the_staged_archive_is_removed_even_when_the_transfer_fails() -> None:
    backend = _FakeBackend(fail_substring="tar -xzf", stderr="tar: not found")

    with pytest.raises(DirectoryTransferError):
        await upload_dir_via_archive(backend, "ep-1", "/work", b"tar-bytes")

    assert backend.commands[-1].startswith("rm -f "), "a failed extract must still clean up"


async def test_a_failed_transfer_names_what_the_image_is_missing() -> None:
    """The common cause is a minimal image with no ``tar``, which the exit code alone does not say."""
    backend = _FakeBackend(fail_substring="tar -czf", stderr="sh: tar: not found")

    with pytest.raises(DirectoryTransferError) as excinfo:
        await download_dir_via_archive(backend, "ep-1", "/work")

    message = str(excinfo.value)
    assert "tar" in message
    assert "/work" in message, "the message should name the path that failed"


@pytest.mark.parametrize("path", ["/work; rm -rf /", "/work$(whoami)", "/work'`id`"])
async def test_paths_are_quoted_into_the_shell_command(path: str) -> None:
    # These paths reach the helpers already validated as absolute, but validation is not quoting:
    # the command is assembled as a shell string, so a path is only safe once escaped. Absolute
    # says nothing about metacharacters -- `/work; rm -rf /` is a valid absolute path.
    backend = _FakeBackend()

    await download_dir_via_archive(backend, "ep-1", path)

    command = backend.commands[0]
    assert shlex.quote(path) in command, "the path must reach the command in its quoted form"
    assert f"-C {path} " not in command, "and never unquoted"
