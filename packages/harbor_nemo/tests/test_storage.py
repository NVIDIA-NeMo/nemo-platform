# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import httpx
import respx
from harbor_nemo.storage import NemoStorage

from conftest import FILES_URL, FILESET, WORKSPACE

BARE_PATH = "packages/nvidia.my-task/abc/dist.tar.gz"
FULL_REF = f"{WORKSPACE}/{FILESET}#{BARE_PATH}"


def test_a_bare_path_resolves_against_the_configured_fileset(client, config):
    storage = NemoStorage(client, config)
    assert storage._resolve(BARE_PATH) == (WORKSPACE, FILESET, BARE_PATH)


def test_a_full_reference_is_used_as_given(client, config):
    """This is what makes a stored archive path immune to a changed environment: the
    reference names its own workspace and fileset, so it cannot be pointed elsewhere."""
    storage = NemoStorage(client, config)
    assert storage._resolve(f"other-ws/other-fs#{BARE_PATH}") == ("other-ws", "other-fs", BARE_PATH)


def test_a_fileset_only_reference_falls_back_to_the_configured_workspace(client, config):
    storage = NemoStorage(client, config)
    assert storage._resolve(f"just-a-fileset#{BARE_PATH}") == (WORKSPACE, "just-a-fileset", BARE_PATH)


def test_bare_paths_are_rendered_as_self_describing_references(client, config):
    assert NemoStorage(client, config).to_fileset_ref(BARE_PATH) == FULL_REF


@respx.mock
async def test_upload_creates_the_fileset_once_then_reuses_it(client, config):
    """`publish_tasks` runs 50-wide against a possibly empty workspace, so the first publishes
    race to create the fileset. Creating it once per process keeps that to one request."""
    create = respx.post(FILES_URL).mock(return_value=httpx.Response(201, json={"name": FILESET}))
    put = respx.put(f"{FILES_URL}/{FILESET}/-/{BARE_PATH}").mock(return_value=httpx.Response(200, json={}))

    storage = NemoStorage(client, config)
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        blob = Path(tmp) / "dist.tar.gz"
        blob.write_bytes(b"payload")
        await storage.upload_file(blob, BARE_PATH)
        await storage.upload_file(blob, BARE_PATH)

    assert create.call_count == 1
    assert put.call_count == 2


@respx.mock
async def test_a_concurrent_fileset_creation_is_not_an_error(client, config):
    """Losing the create race means someone else made it, which is the outcome we wanted."""
    respx.post(FILES_URL).mock(
        return_value=httpx.Response(409, json={"detail": "fileset already exists"})
    )
    respx.put(f"{FILES_URL}/{FILESET}/-/{BARE_PATH}").mock(return_value=httpx.Response(200, json={}))

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        blob = Path(tmp) / "dist.tar.gz"
        blob.write_bytes(b"payload")
        await NemoStorage(client, config).upload_file(blob, BARE_PATH)


@respx.mock
async def test_exists_uses_head_rather_than_downloading(client, config):
    head = respx.head(f"{FILES_URL}/{FILESET}/-/{BARE_PATH}").mock(return_value=httpx.Response(200))
    assert await NemoStorage(client, config).exists(BARE_PATH) is True
    assert head.called


@respx.mock
async def test_exists_is_false_on_404(client, config):
    respx.head(f"{FILES_URL}/{FILESET}/-/{BARE_PATH}").mock(return_value=httpx.Response(404))
    assert await NemoStorage(client, config).exists(BARE_PATH) is False


@respx.mock
async def test_download_writes_the_bytes_and_creates_parent_directories(client, config, tmp_path):
    respx.get(f"{FILES_URL}/{FILESET}/-/{BARE_PATH}").mock(
        return_value=httpx.Response(200, content=b"archive-bytes")
    )
    target = tmp_path / "nested" / "deeper" / "dist.tar.gz"
    await NemoStorage(client, config).download_file(FULL_REF, target)
    assert target.read_bytes() == b"archive-bytes"
