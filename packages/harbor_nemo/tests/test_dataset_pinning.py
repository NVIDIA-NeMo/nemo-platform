# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A dataset's members must stay pinned to the exact task content the manifest named."""

from pathlib import Path

import httpx
import pytest
import respx
from harbor.publisher.errors import PublishBackendError
from harbor_nemo.dataset_client import NemoDatasetClient
from harbor_nemo.publisher import NemoPublisher
from harbor_nemo.storage import NemoStorage
from harbor_nemo.task_resolver import NemoTaskResolver

from conftest import TASKS_URL, TASKSETS_URL, WORKSPACE, harbor_task

TASK_URL = f"{TASKS_URL}/nvidia.my-task"
TASKSET_URL = f"{TASKSETS_URL}/nvidia.my-dataset"

ARCHIVE_1 = "a" * 64
ARCHIVE_2 = "b" * 64
REV_1_HASH = "1" * 64
REV_2_HASH = "2" * 64

DATASET_TOML = f"""\
[dataset]
name = "nvidia/my-dataset"
version = "0.1.0"
description = "fixture"

[[tasks]]
name = "nvidia/my-task"
digest = "sha256:{ARCHIVE_1}"
"""


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "my-dataset"
    directory.mkdir()
    (directory / "dataset.toml").write_text(DATASET_TOML)
    return directory


def _publisher(client, config) -> NemoPublisher:
    return NemoPublisher(
        client, config, NemoStorage(client, config), NemoTaskResolver(client, config)
    )


def _mock_two_revisions() -> None:
    respx.get(f"{TASK_URL}/revisions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"revision": 1, "content_hash": REV_1_HASH, "tags": []},
                    {"revision": 2, "content_hash": REV_2_HASH, "tags": ["latest"]},
                ]
            },
        )
    )
    # The head is revision 2 — so pinning revision 1 must NOT be answered from the head.
    respx.get(TASK_URL).mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2, revision=2))
    )
    respx.get(f"{TASK_URL}/revisions/{REV_2_HASH}").mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2, revision=2))
    )
    respx.get(f"{TASK_URL}/revisions/{REV_1_HASH}").mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_1, revision=1))
    )


@respx.mock
async def test_a_manifest_pin_becomes_a_pinned_taskset_member(client, config, dataset_dir):
    """The manifest names an *older* revision by archive digest. The published taskset must
    pin that revision's NeMo digest — not the member's current `latest`, which is a different
    task directory entirely."""
    _mock_two_revisions()
    respx.get(TASKSET_URL).mock(return_value=httpx.Response(404))
    create = respx.post(TASKSET_URL).mock(
        return_value=httpx.Response(201, json={"name": "nvidia.my-dataset", "revision": 1})
    )
    respx.get(f"{TASKSET_URL}/revisions").mock(return_value=httpx.Response(200, json={"data": []}))

    await _publisher(client, config).publish_dataset(dataset_dir)

    body = create.calls.last.request.read().decode()
    assert f"{WORKSPACE}/nvidia.my-task#{REV_1_HASH}" in body
    assert REV_2_HASH not in body, "must not pin the head when the manifest named revision 1"


@respx.mock
async def test_a_pin_that_is_not_published_here_fails_loudly(client, config, dataset_dir):
    """Silently dropping an unresolvable pin would publish a dataset that means something
    different from the one the manifest describes."""
    respx.get(f"{TASK_URL}/revisions").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(TASK_URL).mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2, revision=2))
    )
    respx.get(TASKSET_URL).mock(return_value=httpx.Response(404))

    with pytest.raises(PublishBackendError, match="not published here"):
        await _publisher(client, config).publish_dataset(dataset_dir)


@respx.mock
async def test_a_pinned_member_reads_back_as_that_archive_digest(client, config):
    """Round trip: the dataset client must report the pinned revision's archive digest, which
    is what Harbor turns into `PackageTaskId(ref="sha256:...")`."""
    _mock_two_revisions()
    taskset = {
        "name": "nvidia.my-dataset",
        "revision": 1,
        "description": "fixture",
        "tasks": [f"{WORKSPACE}/nvidia.my-task#{REV_1_HASH}"],
        "metadata": [],
    }
    # A bare `org/name` parses with ref "latest", so the lookup goes through the revision
    # selector rather than the head.
    respx.get(f"{TASKSET_URL}/revisions/latest").mock(return_value=httpx.Response(200, json=taskset))
    respx.get(TASKSET_URL).mock(return_value=httpx.Response(200, json=taskset))
    respx.get(f"{TASKSET_URL}/revisions").mock(
        return_value=httpx.Response(200, json={"data": [{"revision": 1, "content_hash": "d" * 64}]})
    )

    metadata = await NemoDatasetClient(
        client, config, NemoStorage(client, config)
    )._get_dataset_metadata("nvidia/my-dataset")

    assert [task.ref for task in metadata.task_ids] == [f"sha256:{ARCHIVE_1}"]


@respx.mock
async def test_a_sha256_prefixed_dataset_ref_is_normalised(client, config):
    """`version` on the metadata we return carries Harbor's `sha256:` prefix, and Harbor feeds
    it straight back when re-resolving a dataset. NeMo fragments are bare hex, and the route's
    path pattern rejects the ':' with a 422 — which is how `harbor run -d` broke."""
    revision_hash = "d" * 64
    route = respx.get(f"{TASKSET_URL}/revisions/{revision_hash}").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "nvidia.my-dataset",
                "revision": 1,
                "description": "",
                "tasks": [],
                "metadata": [],
            },
        )
    )
    respx.get(f"{TASKSET_URL}/revisions").mock(
        return_value=httpx.Response(200, json={"data": [{"revision": 1, "content_hash": revision_hash}]})
    )

    await NemoDatasetClient(client, config, NemoStorage(client, config))._get_dataset_metadata(
        f"nvidia/my-dataset@sha256:{revision_hash}"
    )
    assert route.called
