# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import httpx
import pytest
import respx
from harbor.publisher.errors import PublishAuthError
from harbor_nemo.task_resolver import NemoTaskResolver

from conftest import TASKS_URL, harbor_task

TASK_URL = f"{TASKS_URL}/nvidia.my-task"

REV_1_HASH = "1" * 64
REV_2_HASH = "2" * 64
ARCHIVE_1 = "a" * 64
ARCHIVE_2 = "b" * 64


def _revisions_payload() -> dict:
    return {
        "data": [
            {"revision": 1, "content_hash": REV_1_HASH, "tags": []},
            {"revision": 2, "content_hash": REV_2_HASH, "tags": ["latest"]},
        ]
    }


@respx.mock
async def test_resolves_a_tag_and_reports_harbors_hash_not_nemos(client, config):
    """`content_hash` must carry the *archive* digest: Harbor keys its download cache on it."""
    respx.get(f"{TASK_URL}/revisions/latest").mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2, revision=2))
    )
    resolved = await NemoTaskResolver(client, config).resolve_version("nvidia", "my-task")
    assert resolved.content_hash == ARCHIVE_2
    assert resolved.archive_path.startswith("default/harbor-packages#")
    assert resolved.revision == 2


@respx.mock
async def test_a_missing_task_is_a_value_error(client, config):
    """Load bearing: `package_type` tells absent from broken by catching exactly ValueError."""
    respx.get(f"{TASK_URL}/revisions/latest").mock(return_value=httpx.Response(404))
    with pytest.raises(ValueError, match="not found"):
        await NemoTaskResolver(client, config).resolve_version("nvidia", "my-task")


@respx.mock
async def test_an_auth_failure_is_not_downgraded_to_not_found(client, config):
    """If this leaked as ValueError, a logged-out user would be told the package is missing."""
    respx.get(f"{TASK_URL}/revisions/latest").mock(return_value=httpx.Response(401))
    with pytest.raises(PublishAuthError):
        await NemoTaskResolver(client, config).resolve_version("nvidia", "my-task")


@respx.mock
async def test_an_agent_eval_task_is_not_a_harbor_package(client, config):
    """A name collision with a non-Harbor task must read as absent, so `package_type` can
    fall through to the dataset probe rather than exploding."""
    respx.get(f"{TASK_URL}/revisions/latest").mock(
        return_value=httpx.Response(200, json=harbor_task(kind="evaluator"))
    )
    with pytest.raises(ValueError, match="not a Harbor package"):
        await NemoTaskResolver(client, config).resolve_version("nvidia", "my-task")


@respx.mock
async def test_a_content_pinned_ref_hits_the_head_without_scanning(client, config):
    """Re-resolving the current content is the common case and must cost one request."""
    head = respx.get(TASK_URL).mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2, revision=2))
    )
    listing = respx.get(f"{TASK_URL}/revisions").mock(return_value=httpx.Response(200, json={"data": []}))

    resolved = await NemoTaskResolver(client, config).resolve_version(
        "nvidia", "my-task", f"sha256:{ARCHIVE_2}"
    )
    assert resolved.content_hash == ARCHIVE_2
    assert head.called
    assert not listing.called


@respx.mock
async def test_a_content_pinned_ref_scans_revisions_by_content_hash_not_ordinal(client, config):
    """The regression this pins: the platform reads a non-digest fragment as a *tag*, so
    fetching `/revisions/1` looks for a tag named "1" and 404s. Every digest-pinned download
    that was not the head failed with a bogus "task version not found"."""
    respx.get(TASK_URL).mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2, revision=2))
    )
    respx.get(f"{TASK_URL}/revisions").mock(
        return_value=httpx.Response(200, json=_revisions_payload())
    )
    by_ordinal = respx.get(f"{TASK_URL}/revisions/1").mock(return_value=httpx.Response(404))
    respx.get(f"{TASK_URL}/revisions/{REV_2_HASH}").mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2, revision=2))
    )
    respx.get(f"{TASK_URL}/revisions/{REV_1_HASH}").mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_1, revision=1))
    )

    resolved = await NemoTaskResolver(client, config).resolve_version(
        "nvidia", "my-task", f"sha256:{ARCHIVE_1}"
    )
    assert resolved.content_hash == ARCHIVE_1
    assert resolved.revision == 1
    assert not by_ordinal.called


@respx.mock
async def test_a_revision_ordinal_ref_is_translated_to_a_content_hash(client, config):
    """Harbor documents `ref` as "a tag, a revision, or a digest". A bare ordinal is not a
    valid platform selector, so it has to be looked up rather than passed through."""
    respx.get(f"{TASK_URL}/revisions").mock(
        return_value=httpx.Response(200, json=_revisions_payload())
    )
    respx.get(f"{TASK_URL}/revisions/{REV_1_HASH}").mock(
        return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_1, revision=1))
    )
    resolved = await NemoTaskResolver(client, config).resolve_version("nvidia", "my-task", "1")
    assert resolved.revision == 1


@respx.mock
async def test_an_unknown_ordinal_is_a_value_error(client, config):
    respx.get(f"{TASK_URL}/revisions").mock(
        return_value=httpx.Response(200, json=_revisions_payload())
    )
    with pytest.raises(ValueError, match="no revision 7"):
        await NemoTaskResolver(client, config).resolve_version("nvidia", "my-task", "7")


@respx.mock
async def test_a_content_hash_that_no_revision_carries_is_a_value_error(client, config):
    respx.get(TASK_URL).mock(return_value=httpx.Response(200, json=harbor_task(archive_digest=ARCHIVE_2)))
    respx.get(f"{TASK_URL}/revisions").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(ValueError, match="No revision"):
        await NemoTaskResolver(client, config).resolve_version(
            "nvidia", "my-task", f"sha256:{'c' * 64}"
        )


async def test_an_unrepresentable_name_reads_as_absent(client, config):
    """No request is made: a name NeMo could never have stored is one NeMo does not have."""
    with pytest.raises(ValueError):
        await NemoTaskResolver(client, config).resolve_version("nvidia", "X" * 80)


async def test_record_download_is_a_no_op(client, config):
    """Deliberate: no counter primitive exists, so implementing it would mean a
    read-modify-write on the hottest entity per package for best-effort telemetry."""
    assert await NemoTaskResolver(client, config).record_download("anything") is None
