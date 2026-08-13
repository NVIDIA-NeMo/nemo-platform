# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The publish contracts: idempotency reported not raised, and preflight before packaging."""

from pathlib import Path

import httpx
import pytest
import respx
from harbor.publisher.base import BasePublisher
from harbor.publisher.packager import Packager
from harbor_nemo.publisher import NemoPublisher
from harbor_nemo.storage import NemoStorage
from harbor_nemo.task_resolver import NemoTaskResolver

from conftest import FILES_URL, FILESET, TASKS_URL, WORKSPACE, harbor_task

TASK_URL = f"{TASKS_URL}/nvidia.my-task"

TASK_TOML = """\
schema_version = "1.1"

[task]
name = "nvidia/my-task"
description = "fixture"

[verifier]
timeout_sec = 60.0

[agent]
timeout_sec = 60.0
"""


@pytest.fixture
def task_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "my-task"
    (directory / "environment").mkdir(parents=True)
    (directory / "tests").mkdir()
    (directory / "task.toml").write_text(TASK_TOML)
    (directory / "instruction.md").write_text("do it")
    (directory / "environment" / "Dockerfile").write_text("FROM alpine:3.22\n")
    (directory / "tests" / "test.sh").write_text("#!/bin/bash\ntrue\n")
    return directory


def _publisher(client, config) -> NemoPublisher:
    return NemoPublisher(client, config, NemoStorage(client, config), NemoTaskResolver(client, config))


@respx.mock
async def test_first_publish_uploads_and_creates(client, config, task_dir):
    content_hash, _ = Packager.compute_content_hash(task_dir)
    respx.get(TASK_URL).mock(return_value=httpx.Response(404))
    respx.post(FILES_URL).mock(return_value=httpx.Response(201, json={}))
    upload = respx.put(url__startswith=f"{FILES_URL}/{FILESET}/-/").mock(
        return_value=httpx.Response(200, json={})
    )
    create = respx.post(TASK_URL).mock(
        return_value=httpx.Response(201, json=harbor_task(archive_digest=content_hash))
    )

    result = await _publisher(client, config).publish_task(task_dir)

    assert upload.called
    assert create.called
    assert result.skipped is False
    assert result.revision == 1
    assert result.content_hash == content_hash
    assert result.tags == ["latest"]


@respx.mock
async def test_republishing_identical_content_reports_skipped_and_never_packages(
    client, config, task_dir
):
    """Contract: idempotency is reported, not raised — and the existence check happens
    *before* an archive is built, so a no-op publish does no packaging and no upload."""
    content_hash, _ = Packager.compute_content_hash(task_dir)
    respx.get(TASK_URL).mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=content_hash))
    )
    upload = respx.put(url__startswith=f"{FILES_URL}/{FILESET}/-/").mock(
        return_value=httpx.Response(200, json={})
    )
    replace = respx.put(TASK_URL).mock(return_value=httpx.Response(200, json=harbor_task()))

    result = await _publisher(client, config).publish_task(task_dir)

    assert result.skipped is True
    assert result.db_skipped is True
    assert result.revision is None
    assert result.archive_size_bytes == 0
    assert not upload.called, "identical content must not be re-uploaded"
    assert not replace.called, "identical content with identical tags needs no request at all"


@respx.mock
async def test_identical_content_with_a_new_tag_still_moves_the_tag(client, config, task_dir):
    """Skipping the *package* must not mean skipping the tag the user asked for."""
    content_hash, _ = Packager.compute_content_hash(task_dir)
    respx.get(TASK_URL).mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=content_hash))
    )
    upload = respx.put(url__startswith=f"{FILES_URL}/{FILESET}/-/").mock(
        return_value=httpx.Response(200, json={})
    )
    replace = respx.put(TASK_URL).mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=content_hash))
    )

    result = await _publisher(client, config).publish_task(task_dir, tags={"stable"})

    assert replace.called, "a requested tag that is not applied must still be published"
    assert not upload.called, "the archive is unchanged, so it must not be re-uploaded"
    assert result.skipped is True
    assert result.tags == ["latest", "stable"]


@respx.mock
async def test_the_platforms_200_versus_201_is_the_skipped_signal(client, config, task_dir):
    """A PUT that dedups server-side answers 200; a new revision answers 201. That status
    code is the only place the distinction appears."""
    respx.get(TASK_URL).mock(return_value=httpx.Response(200, json=harbor_task(archive_digest="f" * 64)))
    respx.post(FILES_URL).mock(return_value=httpx.Response(201, json={}))
    respx.put(url__startswith=f"{FILES_URL}/{FILESET}/-/").mock(return_value=httpx.Response(200, json={}))
    respx.put(TASK_URL).mock(return_value=httpx.Response(200, json=harbor_task()))

    result = await _publisher(client, config).publish_task(task_dir)
    assert result.skipped is True
    assert result.db_skipped is True


@respx.mock
async def test_a_concurrent_creator_falls_back_to_publishing_a_revision(client, config, task_dir):
    """`publish_tasks` runs 50-wide, so another publisher can create the task between our
    preflight and our POST. Losing that race must not fail the publish."""
    respx.get(TASK_URL).mock(return_value=httpx.Response(404))
    respx.post(FILES_URL).mock(return_value=httpx.Response(201, json={}))
    respx.put(url__startswith=f"{FILES_URL}/{FILESET}/-/").mock(return_value=httpx.Response(200, json={}))
    respx.post(TASK_URL).mock(
        return_value=httpx.Response(409, json={"detail": "Task 'nvidia.my-task' already exists."})
    )
    replace = respx.put(TASK_URL).mock(return_value=httpx.Response(201, json=harbor_task(revision=2)))

    result = await _publisher(client, config).publish_task(task_dir)

    assert replace.called
    assert result.revision == 2


@respx.mock
async def test_the_blob_is_uploaded_before_the_task_is_registered(client, config, task_dir):
    """Order matters: registering first would let a crash leave a task pointing at an archive
    that was never written, and every later publish would then report "skipped" forever."""
    calls: list[str] = []
    respx.get(TASK_URL).mock(return_value=httpx.Response(404))
    respx.post(FILES_URL).mock(return_value=httpx.Response(201, json={}))
    respx.put(url__startswith=f"{FILES_URL}/{FILESET}/-/").mock(
        side_effect=lambda request: calls.append("upload") or httpx.Response(200, json={})
    )
    respx.post(TASK_URL).mock(
        side_effect=lambda request: calls.append("register") or httpx.Response(201, json=harbor_task())
    )

    await _publisher(client, config).publish_task(task_dir)
    assert calls == ["upload", "register"]


@respx.mock
async def test_publish_file_skips_an_upload_when_the_blob_is_present(client, config, tmp_path):
    blob = tmp_path / "metric.py"
    blob.write_text("def score(): return 1.0\n")
    content_hash = Packager.compute_file_hash(blob)
    remote = BasePublisher.remote_path("nvidia/my-dataset", content_hash, "metric.py")

    respx.head(f"{FILES_URL}/{FILESET}/-/{remote}").mock(return_value=httpx.Response(200))
    upload = respx.put(f"{FILES_URL}/{FILESET}/-/{remote}").mock(return_value=httpx.Response(200, json={}))

    result = await _publisher(client, config).publish_file("nvidia/my-dataset", blob)

    assert result.skipped is True
    assert not upload.called
    # The self-describing reference, because this becomes DatasetFileInfo.storage_path and is
    # later handed straight back to download_file.
    assert result.remote_path == f"{WORKSPACE}/{FILESET}#{remote}"


@respx.mock
async def test_an_unrepresentable_name_fails_the_publish_loudly(client, config, tmp_path):
    """On the read path a bad name reads as "absent"; on the publish path it is a real,
    actionable failure and must be reported as one."""
    from harbor.publisher.errors import PublishBackendError

    directory = tmp_path / "my-task"
    (directory / "environment").mkdir(parents=True)
    (directory / "tests").mkdir()
    (directory / "task.toml").write_text(TASK_TOML.replace("nvidia/my-task", "nvidia.labs/my-task"))
    (directory / "instruction.md").write_text("do it")
    (directory / "environment" / "Dockerfile").write_text("FROM alpine:3.22\n")
    (directory / "tests" / "test.sh").write_text("#!/bin/bash\ntrue\n")

    with pytest.raises(PublishBackendError, match="contains a '.'"):
        await _publisher(client, config).publish_task(directory)


def test_archive_construction_is_inherited_untouched():
    """Overriding either of these would break byte-identity with the public Hub, and with it
    the comparability of historical eval results across a migration."""
    assert "_create_archive" not in NemoPublisher.__dict__
    assert "remote_path" not in NemoPublisher.__dict__
    assert "publish_tasks" not in NemoPublisher.__dict__
