# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the fileset-profiling job helper and endpoints."""

import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from nemo_platform_plugin.files.dataset_profile import DatasetProfile, SamplingInfo
from nemo_platform_plugin.files.metadata import DatasetMetadataContent, FilesetMetadata
from nemo_platform_plugin.files.types import UpdateFilesetRequest
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from nemo_platform_plugin.jobs.spec import NAME_PATTERN
from nmp.common.entities.client import EntityNotFoundError
from nmp.common.files.storage_config import LocalStorageConfig
from nmp.core.files.api.v2.filesets.endpoints import (
    get_fileset_profile,
    profile_fileset,
    update_fileset_metadata,
)
from nmp.core.files.api.v2.filesets.schemas import (
    FilesetProfileResponse,
    SubmitProfileJobResponse,
    fileset_output_from_entity,
)
from nmp.core.files.app.profile_job import (
    _build_platform_spec,
    _is_active,
    _job_name_for_fileset,
    submit_profile_job,
)
from nmp.core.files.entities import Fileset, FilesetPurpose


def _minimal_profile() -> DatasetProfile:
    return DatasetProfile(
        created_at=datetime(2026, 1, 1),
        sampling=SamplingInfo(rows_scanned=1, rows_present=1, files_read=1, files_present=1, bytes_present=100),
        partitions=[],
    )


def _dataset_fileset(*, purpose=FilesetPurpose.DATASET, profile=None) -> Fileset:
    return Fileset(
        name="fs1",
        workspace="ws1",
        storage=LocalStorageConfig(path="/tmp/x"),
        purpose=purpose,
        metadata=FilesetMetadata(dataset=DatasetMetadataContent(profile=profile)),
    )


def _job_list(*jobs):
    """A fresh async iterable of jobs, mimicking ``sdk.jobs.list(...)``."""

    async def _gen():
        for job in jobs:
            yield job

    return _gen()


def _sdk(*, jobs=(), create_returns=None):
    return SimpleNamespace(
        jobs=SimpleNamespace(
            list=lambda **_kwargs: _job_list(*jobs),
            create=AsyncMock(return_value=create_returns),
        )
    )


# --- submission helper -------------------------------------------------------


def test_build_platform_spec_targets_profiler_task():
    spec = _build_platform_spec("ws1", "fs1")

    step = spec["steps"][0]
    assert step["name"] == "profile"
    assert step["config"] == {"workspace": "ws1", "fileset": "fs1"}
    container = step["executor"]["container"]
    assert container["entrypoint"] == ["python", "-m"]
    assert container["command"] == ["nemo_datasets_plugin.tasks.profile"]
    assert "nmp-cpu-tasks" in container["image"]


@pytest.mark.asyncio
async def test_submit_profile_job_creates_job_with_expected_spec():
    job = SimpleNamespace(name="profile-fs1-abcd1234", id="job-id", status="created")
    sdk = SimpleNamespace(jobs=SimpleNamespace(create=AsyncMock(return_value=job)))

    result = await submit_profile_job(sdk, workspace="ws1", fileset_name="fs1")

    assert result is job
    kwargs = sdk.jobs.create.await_args.kwargs
    assert kwargs["source"] == "files"
    assert kwargs["spec"] == {"fileset": "fs1"}
    assert kwargs["name"].startswith("profile-fs1-")


def test_job_name_slugs_the_fileset_name():
    assert _job_name_for_fileset("GSM8K").startswith("profile-gsm8k-")


@pytest.mark.parametrize("fileset_name", ["GSM8K", "My_Dataset.v2", "-leading", "a--b", "Ünïcødé", "x" * 80, "___"])
def test_job_name_is_valid_for_gnarly_fileset_names(fileset_name):
    # Fileset names permit characters the Jobs name pattern forbids (uppercase, . / _, -- runs,
    # leading/trailing punctuation, length); the slugged job name must still satisfy it.
    name = _job_name_for_fileset(fileset_name)
    assert re.match(NAME_PATTERN, name), name


# --- POST /profile -----------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_fileset_submits_when_no_active_job():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset()
    job = SimpleNamespace(name="profile-fs1-abcd1234", id="job-id", status="created")
    sdk = _sdk(jobs=(), create_returns=job)

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert isinstance(resp, SubmitProfileJobResponse)
    assert resp.job_name == "profile-fs1-abcd1234"
    assert resp.reused is False
    sdk.jobs.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_fileset_rejects_non_dataset():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(purpose=FilesetPurpose.MODEL)
    sdk = _sdk()

    with pytest.raises(HTTPException) as exc:
        await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert exc.value.status_code == 400
    sdk.jobs.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_fileset_dedupes_active_job():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset()
    active = SimpleNamespace(name="profile-fs1-running", id="eid", status="active", spec={"fileset": "fs1"})
    sdk = _sdk(jobs=(active,))

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.reused is True
    assert resp.job_name == "profile-fs1-running"
    sdk.jobs.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_fileset_submits_when_only_terminal_jobs():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset()
    done = SimpleNamespace(name="profile-fs1-old", id="oid", status="completed", spec={"fileset": "fs1"})
    job = SimpleNamespace(name="profile-fs1-new", id="nid", status="created")
    sdk = _sdk(jobs=(done,), create_returns=job)

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.reused is False
    sdk.jobs.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_fileset_ignores_active_job_for_other_fileset():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset()
    other = SimpleNamespace(name="profile-other-x", id="oid", status="active", spec={"fileset": "other"})
    job = SimpleNamespace(name="profile-fs1-new", id="nid", status="created")
    sdk = _sdk(jobs=(other,), create_returns=job)

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.reused is False
    sdk.jobs.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_fileset_404_when_missing():
    entity_store = AsyncMock()
    entity_store.get.side_effect = EntityNotFoundError("not found")
    sdk = _sdk()

    with pytest.raises(HTTPException) as exc:
        await profile_fileset("ws1", "missing", entity_store=entity_store, sdk=sdk)

    assert exc.value.status_code == 404
    sdk.jobs.create.assert_not_awaited()


# --- GET /profile ------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fileset_profile_ready_without_querying_jobs():
    profile = _minimal_profile()
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=profile)
    # jobs.list would raise if called — a ready profile must not query the Jobs service.
    sdk = SimpleNamespace(jobs=SimpleNamespace(list=AsyncMock(side_effect=AssertionError("should not query jobs"))))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert isinstance(resp, FilesetProfileResponse)
    assert resp.state == "ready"
    assert resp.profile is profile


@pytest.mark.asyncio
async def test_get_fileset_profile_running():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=None)
    active = SimpleNamespace(name="profile-fs1-running", id="i", status="active", spec={"fileset": "fs1"})
    sdk = _sdk(jobs=(active,))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "running"
    assert resp.job_name == "profile-fs1-running"


@pytest.mark.asyncio
async def test_get_fileset_profile_absent():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=None)
    sdk = _sdk(jobs=())

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "absent"
    assert resp.profile is None


@pytest.mark.asyncio
async def test_get_fileset_profile_failed():
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=None)
    errored = SimpleNamespace(
        name="profile-fs1-err", id="e", status="error", spec={"fileset": "fs1"}, created_at=datetime(2026, 1, 1)
    )
    sdk = _sdk(jobs=(errored,))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "failed"
    assert resp.job_name == "profile-fs1-err"
    assert resp.profile is None


@pytest.mark.asyncio
async def test_get_fileset_profile_absent_when_last_job_completed():
    # A completed job normally leaves a profile (→ ready); a completed terminal with no stored
    # profile is not a failure, so the state is "absent", not "failed".
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=None)
    done = SimpleNamespace(
        name="profile-fs1-done", id="d", status="completed", spec={"fileset": "fs1"}, created_at=datetime(2026, 1, 1)
    )
    sdk = _sdk(jobs=(done,))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "absent"


@pytest.mark.asyncio
async def test_get_fileset_profile_failed_uses_latest_terminal():
    # With multiple terminal jobs and no stored profile, the most recent one decides the state.
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=None)
    old_done = SimpleNamespace(
        name="old", id="o", status="completed", spec={"fileset": "fs1"}, created_at=datetime(2026, 1, 1)
    )
    new_err = SimpleNamespace(
        name="new", id="n", status="error", spec={"fileset": "fs1"}, created_at=datetime(2026, 2, 1)
    )
    sdk = _sdk(jobs=(old_done, new_err))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "failed"
    assert resp.job_name == "new"


@pytest.mark.asyncio
async def test_get_fileset_profile_cancelled_is_not_failed():
    # A deliberate stop is not a breakage: nothing needs investigating and the remedy is just to
    # re-run, so it must not surface as "failed".
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=None)
    cancelled = SimpleNamespace(
        name="profile-fs1-cxl",
        id="c",
        status="cancelled",
        spec={"fileset": "fs1"},
        created_at=datetime(2026, 1, 1),
    )
    sdk = _sdk(jobs=(cancelled,))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "cancelled"
    assert resp.job_name == "profile-fs1-cxl"
    assert resp.profile is None


@pytest.mark.asyncio
async def test_get_fileset_profile_latest_terminal_decides_between_cancelled_and_failed():
    # The two terminal outcomes are distinct states, so which one wins still follows recency.
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=None)
    old_err = SimpleNamespace(
        name="old-err", id="o", status="error", spec={"fileset": "fs1"}, created_at=datetime(2026, 1, 1)
    )
    new_cancelled = SimpleNamespace(
        name="new-cxl", id="n", status="cancelled", spec={"fileset": "fs1"}, created_at=datetime(2026, 2, 1)
    )
    sdk = _sdk(jobs=(old_err, new_cancelled))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "cancelled"
    assert resp.job_name == "new-cxl"


@pytest.mark.asyncio
async def test_get_fileset_profile_ready_wins_over_a_cancelled_rerun():
    # Cancelling a re-profile must not hide an existing profile: the stored one still answers.
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=_minimal_profile())
    cancelled = SimpleNamespace(
        name="profile-fs1-cxl", id="c", status="cancelled", spec={"fileset": "fs1"}, created_at=datetime(2026, 1, 1)
    )
    sdk = _sdk(jobs=(cancelled,))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "ready"
    assert resp.profile is not None


# --- payload bloat -----------------------------------------------------------


def test_fileset_output_strips_profile():
    entity = _dataset_fileset(profile=_minimal_profile())

    out = fileset_output_from_entity(entity)

    assert out.metadata.dataset.profile is None


def test_fileset_output_strips_profile_from_dict_metadata():
    # The PATCH handler builds an entity whose ``.metadata`` is a raw dict via
    # ``model_copy(update=...)``; the converter must handle that without crashing.
    profile_dict = _minimal_profile().model_dump()
    entity = _dataset_fileset().model_copy(update={"metadata": {"dataset": {"profile": profile_dict}}})

    out = fileset_output_from_entity(entity)

    assert out.metadata.dataset.profile is None


# --- status normalization ----------------------------------------------------


def test_is_active_normalizes_enum_and_string_status():
    # Today's SDK returns plain lowercase strings; a future enum must classify the same way
    # (str(PlatformJobStatus.COMPLETED) would be "platformjobstatus.completed" without .value).
    assert _is_active(SimpleNamespace(status=PlatformJobStatus.ACTIVE, spec={})) is True
    for terminal in (PlatformJobStatus.COMPLETED, PlatformJobStatus.ERROR, PlatformJobStatus.CANCELLED):
        assert _is_active(SimpleNamespace(status=terminal, spec={})) is False
    assert _is_active(SimpleNamespace(status="active", spec={})) is True
    assert _is_active(SimpleNamespace(status="completed", spec={})) is False


# --- profile preservation across a metadata PATCH ----------------------------


def _auth(principal_id="user:test"):
    return SimpleNamespace(principal=SimpleNamespace(id=principal_id))


@pytest.mark.asyncio
async def test_patch_preserves_profile_when_request_omits_it():
    # A client edits the schema; it never saw the (stripped) profile, so its PATCH omits it.
    # The server must re-graft the stored profile rather than nulling it out.
    stored = Fileset(
        name="fs1",
        workspace="ws1",
        storage=LocalStorageConfig(path="/tmp/x"),
        purpose=FilesetPurpose.DATASET,
        metadata=FilesetMetadata(
            dataset=DatasetMetadataContent(schema_defs={"row": {"type": "object"}}, profile=_minimal_profile())
        ),
    )
    entity_store = AsyncMock()
    entity_store.get.return_value = stored
    request = UpdateFilesetRequest(
        metadata=FilesetMetadata(dataset=DatasetMetadataContent(schema_defs={"row": {"type": "string"}}))
    )

    await update_fileset_metadata("ws1", "fs1", request, entity_store=entity_store, auth_client=_auth())

    persisted = FilesetMetadata.model_validate(entity_store.update.await_args.args[0].metadata)
    assert persisted.dataset.profile is not None
    assert persisted.dataset.profile.content_digest == "sha256:test"  # preserved
    assert persisted.dataset.schema_defs == {"row": {"type": "string"}}  # edit applied


@pytest.mark.asyncio
async def test_patch_overwrites_profile_when_request_provides_one():
    # The profiler task writes a fresh profile through this same PATCH path; it must win.
    entity_store = AsyncMock()
    entity_store.get.return_value = _dataset_fileset(profile=_minimal_profile())
    fresh = _minimal_profile().model_copy(update={"content_digest": "sha256:fresh"})
    request = UpdateFilesetRequest(metadata=FilesetMetadata(dataset=DatasetMetadataContent(profile=fresh)))

    await update_fileset_metadata("ws1", "fs1", request, entity_store=entity_store, auth_client=_auth())

    persisted = FilesetMetadata.model_validate(entity_store.update.await_args.args[0].metadata)
    assert persisted.dataset.profile.content_digest == "sha256:fresh"
