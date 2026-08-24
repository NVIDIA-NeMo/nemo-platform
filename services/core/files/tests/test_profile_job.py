# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the fileset-profiling job helper, profile store, and endpoints."""

import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from nemo_platform_plugin.files.dataset_profile import DatasetProfile, SamplingInfo
from nemo_platform_plugin.files.metadata import DatasetMetadataContent, FilesetMetadata
from nemo_platform_plugin.files.types import PutFilesetProfileRequest, UpdateFilesetRequest
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from nemo_platform_plugin.jobs.spec import NAME_PATTERN
from nmp.common.entities.client import EntityNotFoundError
from nmp.common.files.storage_config import LocalStorageConfig
from nmp.core.files.api.v2.filesets.endpoints import (
    get_fileset_profile,
    profile_fileset,
    put_fileset_profile,
    update_fileset_metadata,
)
from nmp.core.files.api.v2.filesets.schemas import (
    FilesetProfileResponse,
    ProfileFilesetRequest,
    SubmitProfileJobResponse,
    fileset_output_from_entity,
)
from nmp.core.files.app.profile_job import (
    _CANCELLED_JOB_STATES,
    _COMPLETED_JOB_STATES,
    _FAILED_JOB_STATES,
    _PAUSED_JOB_STATES,
    _RUNNING_JOB_STATES,
    _build_platform_spec,
    _job_name_for_fileset,
    is_running_job,
    submit_profile_job,
)
from nmp.core.files.app.profile_store import delete_profile, get_profile, put_profile
from nmp.core.files.entities import FILESET_PROFILE_ENTITY_NAME, Fileset, FilesetProfile, FilesetPurpose


def _minimal_profile(created_at: datetime | None = None) -> DatasetProfile:
    return DatasetProfile(
        created_at=created_at or datetime(2026, 1, 1),
        sampling=SamplingInfo(rows_scanned=1, rows_present=1, files_read=1, files_present=1, bytes_present=100),
        partitions=[],
    )


def _dataset_fileset(*, purpose=FilesetPurpose.DATASET) -> Fileset:
    return Fileset(
        name="fs1",
        workspace="ws1",
        storage=LocalStorageConfig(path="/tmp/x"),
        purpose=purpose,
        metadata=FilesetMetadata(dataset=DatasetMetadataContent()),
    )


def _stored_profile_entity(fileset: Fileset, profile: DatasetProfile) -> FilesetProfile:
    return FilesetProfile(
        name=FILESET_PROFILE_ENTITY_NAME,
        workspace=fileset.workspace,
        fileset=fileset.id,
        profile=profile,
    )


def _entity_store(*, fileset: Fileset | None = None, profile: DatasetProfile | None = None) -> AsyncMock:
    """An entity store serving one fileset and, optionally, its stored-profile child entity."""
    store = AsyncMock()
    target = fileset if fileset is not None else _dataset_fileset()
    stored = _stored_profile_entity(target, profile) if profile is not None else None

    async def _get(entity_type, *_args, **_kwargs):
        if entity_type is FilesetProfile:
            if stored is None:
                raise EntityNotFoundError("profile not found")
            return stored
        return target

    store.get.side_effect = _get
    return store


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


def _job(name, status, *, fileset="fs1", created_at=None, id="jid"):
    return SimpleNamespace(name=name, id=id, status=status, spec={"fileset": fileset}, created_at=created_at)


# --- submission helper -------------------------------------------------------


def test_build_platform_spec_targets_profiler_task():
    spec = _build_platform_spec("ws1", "fs1", None)

    step = spec["steps"][0]
    assert step["name"] == "profile"
    assert step["config"] == {"workspace": "ws1", "fileset": "fs1"}
    container = step["executor"]["container"]
    assert container["entrypoint"] == ["python", "-m"]
    assert container["command"] == ["nemo_datasets_plugin.tasks.profile"]
    assert "nmp-cpu-tasks" in container["image"]


def test_build_platform_spec_omits_an_unset_row_budget():
    # Left out entirely rather than restated here, so the task applies the profiler's own default.
    assert "row_budget" not in _build_platform_spec("ws1", "fs1", None)["steps"][0]["config"]


def test_build_platform_spec_passes_a_requested_row_budget():
    config = _build_platform_spec("ws1", "fs1", 25)["steps"][0]["config"]
    assert config["row_budget"] == 25


def test_build_platform_spec_passes_a_zero_row_budget():
    # 0 means "read every row" and must survive as 0, not be dropped as falsey.
    config = _build_platform_spec("ws1", "fs1", 0)["steps"][0]["config"]
    assert config["row_budget"] == 0


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
    entity_store = _entity_store()
    job = SimpleNamespace(name="profile-fs1-abcd1234", id="job-id", status="created")
    sdk = _sdk(jobs=(), create_returns=job)

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert isinstance(resp, SubmitProfileJobResponse)
    assert resp.job_name == "profile-fs1-abcd1234"
    assert resp.reused is False
    sdk.jobs.create.assert_awaited_once()


def test_the_step_config_keys_are_the_ones_the_task_reads():
    """The step config is a contract between two files that never import each other.

    A key spelled differently on the two sides is silently ignored rather than rejected: this wrote
    `rows_per_file` while the task read `row_budget`, so every request that asked for a bounded
    profile got an uncapped full scan instead -- over ranged reads, the whole fileset pulled over
    the wire. Reading the task's own resolver is what keeps the two spellings from drifting again.
    """
    from nemo_datasets_plugin.tasks.profile import run as profile_task

    config = _build_platform_spec("ws1", "fs1", 25)["steps"][0]["config"]

    assert profile_task._resolve_row_budget(config) == 25
    # ...and the keys the task requires to know what to profile at all.
    assert config["workspace"] == "ws1"
    assert config["fileset"] == "fs1"
    # An unset budget must leave the task on its own default rather than a restated one.
    assert profile_task._resolve_row_budget(_build_platform_spec("ws1", "fs1", None)["steps"][0]["config"]) is None


@pytest.mark.asyncio
async def test_profile_fileset_forwards_a_requested_row_budget():
    entity_store = _entity_store()
    sdk = _sdk(create_returns=SimpleNamespace(name="j", id="i", status="created"))

    await profile_fileset(
        "ws1", "fs1", request=ProfileFilesetRequest(row_budget=25), entity_store=entity_store, sdk=sdk
    )

    config = sdk.jobs.create.await_args.kwargs["platform_spec"]["steps"][0]["config"]
    assert config["row_budget"] == 25


def test_profile_request_rejects_a_negative_row_budget():
    with pytest.raises(ValueError):
        ProfileFilesetRequest(row_budget=-1)


@pytest.mark.asyncio
async def test_profile_fileset_rejects_non_dataset():
    entity_store = _entity_store(fileset=_dataset_fileset(purpose=FilesetPurpose.MODEL))
    sdk = _sdk()

    with pytest.raises(HTTPException) as exc:
        await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert exc.value.status_code == 400
    sdk.jobs.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_fileset_dedupes_running_job():
    entity_store = _entity_store()
    sdk = _sdk(jobs=(_job("profile-fs1-running", "active", id="eid"),))

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.reused is True
    assert resp.job_name == "profile-fs1-running"
    sdk.jobs.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_fileset_resubmits_past_a_paused_job():
    # A paused job produces nothing until someone resumes it, so letting it hold the dedup slot
    # would block profiling this fileset forever with no way out through this API.
    entity_store = _entity_store()
    sdk = _sdk(
        jobs=(_job("profile-fs1-paused", "paused"),),
        create_returns=SimpleNamespace(name="profile-fs1-new", id="nid", status="created"),
    )

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.reused is False
    assert resp.job_name == "profile-fs1-new"
    sdk.jobs.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_fileset_submits_when_only_terminal_jobs():
    entity_store = _entity_store()
    sdk = _sdk(
        jobs=(_job("profile-fs1-old", "completed", id="oid"),),
        create_returns=SimpleNamespace(name="profile-fs1-new", id="nid", status="created"),
    )

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.reused is False
    sdk.jobs.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_fileset_ignores_active_job_for_other_fileset():
    entity_store = _entity_store()
    sdk = _sdk(
        jobs=(_job("profile-other-x", "active", fileset="other", id="oid"),),
        create_returns=SimpleNamespace(name="profile-fs1-new", id="nid", status="created"),
    )

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
    entity_store = _entity_store(profile=profile)
    # jobs.list would raise if called — a ready profile must not query the Jobs service.
    sdk = SimpleNamespace(jobs=SimpleNamespace(list=AsyncMock(side_effect=AssertionError("should not query jobs"))))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert isinstance(resp, FilesetProfileResponse)
    assert resp.state == "ready"
    assert resp.profile is profile


@pytest.mark.asyncio
async def test_get_fileset_profile_running():
    entity_store = _entity_store()
    sdk = _sdk(jobs=(_job("profile-fs1-running", "active"),))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "running"
    assert resp.job_name == "profile-fs1-running"


@pytest.mark.asyncio
async def test_get_fileset_profile_paused_is_reported_not_hidden():
    # Reporting `absent` while a suspended job sits there would send the caller off to re-profile
    # when what they actually need is to resume or cancel the job they already have.
    entity_store = _entity_store()
    sdk = _sdk(jobs=(_job("profile-fs1-paused", "paused"),))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "paused"
    assert resp.job_name == "profile-fs1-paused"


@pytest.mark.asyncio
async def test_get_fileset_profile_running_wins_over_paused():
    entity_store = _entity_store()
    sdk = _sdk(jobs=(_job("paused-one", "paused"), _job("running-one", "active")))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "running"
    assert resp.job_name == "running-one"


@pytest.mark.asyncio
async def test_get_fileset_profile_absent():
    entity_store = _entity_store()
    sdk = _sdk(jobs=())

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "absent"
    assert resp.profile is None


@pytest.mark.asyncio
async def test_get_fileset_profile_failed():
    entity_store = _entity_store()
    sdk = _sdk(jobs=(_job("profile-fs1-err", "error", created_at=datetime(2026, 1, 1)),))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "failed"
    assert resp.job_name == "profile-fs1-err"
    assert resp.profile is None


@pytest.mark.asyncio
async def test_get_fileset_profile_absent_when_last_job_completed():
    # A completed job normally leaves a profile (→ ready); a completed terminal with no stored
    # profile is not a failure, so the state is "absent", not "failed".
    entity_store = _entity_store()
    sdk = _sdk(jobs=(_job("profile-fs1-done", "completed", created_at=datetime(2026, 1, 1)),))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "absent"


@pytest.mark.asyncio
async def test_get_fileset_profile_failed_uses_latest_terminal():
    # With multiple terminal jobs and no stored profile, the most recent one decides the state.
    entity_store = _entity_store()
    sdk = _sdk(
        jobs=(
            _job("old", "completed", created_at=datetime(2026, 1, 1)),
            _job("new", "error", created_at=datetime(2026, 2, 1)),
        )
    )

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "failed"
    assert resp.job_name == "new"


@pytest.mark.asyncio
async def test_get_fileset_profile_cancelled_is_not_failed():
    # A deliberate stop is not a breakage: nothing needs investigating and the remedy is just to
    # re-run, so it must not surface as "failed".
    entity_store = _entity_store()
    sdk = _sdk(jobs=(_job("profile-fs1-cxl", "cancelled", created_at=datetime(2026, 1, 1)),))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "cancelled"
    assert resp.job_name == "profile-fs1-cxl"
    assert resp.profile is None


@pytest.mark.asyncio
async def test_get_fileset_profile_latest_terminal_decides_between_cancelled_and_failed():
    # The two terminal outcomes are distinct states, so which one wins still follows recency.
    entity_store = _entity_store()
    sdk = _sdk(
        jobs=(
            _job("old-err", "error", created_at=datetime(2026, 1, 1)),
            _job("new-cxl", "cancelled", created_at=datetime(2026, 2, 1)),
        )
    )

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "cancelled"
    assert resp.job_name == "new-cxl"


@pytest.mark.asyncio
async def test_get_fileset_profile_ready_wins_over_a_cancelled_rerun():
    # Cancelling a re-profile must not hide an existing profile: the stored one still answers.
    entity_store = _entity_store(profile=_minimal_profile())
    sdk = _sdk(jobs=(_job("profile-fs1-cxl", "cancelled", created_at=datetime(2026, 1, 1)),))

    resp = await get_fileset_profile("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert resp.state == "ready"
    assert resp.profile is not None


# --- profile kind --------------------------------------------------------


def test_profile_kind_defaults_to_dataset():
    assert _minimal_profile().kind == "dataset"


def test_a_profile_written_before_kind_existed_still_validates():
    # `kind` has a default precisely so already-stored profiles keep loading — the reason it is
    # cheap to add now and expensive once a discriminated union is in the wire format.
    stored = _minimal_profile().model_dump(mode="json")
    del stored["kind"]

    assert DatasetProfile.model_validate(stored).kind == "dataset"


def test_profile_kind_is_pinned_not_free_text():
    with pytest.raises(ValueError):
        DatasetProfile.model_validate(_minimal_profile().model_dump(mode="json") | {"kind": "model"})


# --- PUT /profile (internal write path) --------------------------------------


@pytest.mark.asyncio
async def test_put_fileset_profile_creates_when_none_stored():
    entity_store = _entity_store()

    resp = await put_fileset_profile(
        "ws1", "fs1", PutFilesetProfileRequest(profile=_minimal_profile()), entity_store=entity_store
    )

    assert resp.created_at == datetime(2026, 1, 1)
    created = entity_store.create.await_args.args[0]
    assert isinstance(created, FilesetProfile)
    assert created.name == FILESET_PROFILE_ENTITY_NAME
    entity_store.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_put_fileset_profile_replaces_an_existing_one():
    # Profiling is re-runnable by design, so a second run over changed data must land, not conflict.
    entity_store = _entity_store(profile=_minimal_profile(datetime(2026, 1, 1)))

    await put_fileset_profile(
        "ws1",
        "fs1",
        PutFilesetProfileRequest(profile=_minimal_profile(datetime(2026, 2, 2))),
        entity_store=entity_store,
    )

    updated = entity_store.update.await_args.args[0]
    assert updated.profile.created_at == datetime(2026, 2, 2)
    entity_store.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_put_fileset_profile_404_when_fileset_missing():
    entity_store = AsyncMock()
    entity_store.get.side_effect = EntityNotFoundError("not found")

    with pytest.raises(HTTPException) as exc:
        await put_fileset_profile(
            "ws1", "missing", PutFilesetProfileRequest(profile=_minimal_profile()), entity_store=entity_store
        )

    assert exc.value.status_code == 404


# --- profile store -----------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile_returns_none_when_never_profiled():
    fileset = _dataset_fileset()
    assert await get_profile(_entity_store(fileset=fileset), fileset) is None


@pytest.mark.asyncio
async def test_put_profile_scopes_the_child_to_its_fileset():
    fileset = _dataset_fileset()
    entity_store = _entity_store(fileset=fileset)

    await put_profile(entity_store, fileset, _minimal_profile())

    created = entity_store.create.await_args.args[0]
    assert created.fileset == fileset.id
    assert created.parent == fileset.id  # parent-scoped uniqueness, as PlatformJobResult does it


@pytest.mark.asyncio
async def test_delete_profile_removes_the_child_entity():
    fileset = _dataset_fileset()
    entity_store = _entity_store(fileset=fileset, profile=_minimal_profile())

    await delete_profile(entity_store, fileset)

    entity_store.delete_by_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_profile_is_a_noop_when_never_profiled():
    fileset = _dataset_fileset()
    entity_store = _entity_store(fileset=fileset)

    await delete_profile(entity_store, fileset)

    entity_store.delete_by_id.assert_not_awaited()


# --- payload bloat -----------------------------------------------------------


def test_fileset_output_carries_no_profile():
    # The profile is a separate entity, so it is never loaded into a fileset to begin with.
    out = fileset_output_from_entity(_dataset_fileset())

    assert not hasattr(out.metadata.dataset, "profile")


# --- status classification ---------------------------------------------------


def test_every_job_status_is_classified():
    # Adding a status upstream must be a decision here, not a silent default into "in flight".
    classified = (
        _RUNNING_JOB_STATES | _PAUSED_JOB_STATES | _CANCELLED_JOB_STATES | _FAILED_JOB_STATES | _COMPLETED_JOB_STATES
    )
    assert classified == {status.value for status in PlatformJobStatus}


def test_job_status_sets_are_disjoint():
    sets = [_RUNNING_JOB_STATES, _PAUSED_JOB_STATES, _CANCELLED_JOB_STATES, _FAILED_JOB_STATES, _COMPLETED_JOB_STATES]
    assert sum(len(s) for s in sets) == len(set().union(*sets))


def test_is_running_normalizes_enum_and_string_status():
    # Today's SDK returns plain lowercase strings; a future enum must classify the same way
    # (str(PlatformJobStatus.COMPLETED) would be "platformjobstatus.completed" without .value).
    assert is_running_job(SimpleNamespace(status=PlatformJobStatus.ACTIVE, spec={})) is True
    for terminal in (PlatformJobStatus.COMPLETED, PlatformJobStatus.ERROR, PlatformJobStatus.CANCELLED):
        assert is_running_job(SimpleNamespace(status=terminal, spec={})) is False
    assert is_running_job(SimpleNamespace(status="active", spec={})) is True
    assert is_running_job(SimpleNamespace(status="completed", spec={})) is False


# --- metadata PATCH cannot reach the profile ---------------------------------


def _auth(principal_id="user:test"):
    return SimpleNamespace(principal=SimpleNamespace(id=principal_id))


@pytest.mark.asyncio
async def test_patch_cannot_clear_the_stored_profile():
    # The profile lives outside the fileset entity, so even a metadata PATCH that wipes the whole
    # dataset block leaves it untouched — nothing here writes the profile's entity.
    fileset = _dataset_fileset()
    entity_store = _entity_store(fileset=fileset, profile=_minimal_profile())
    request = UpdateFilesetRequest(metadata=FilesetMetadata())

    await update_fileset_metadata("ws1", "fs1", request, entity_store=entity_store, auth_client=_auth())

    assert await get_profile(entity_store, fileset) is not None


@pytest.mark.asyncio
async def test_patch_cannot_forge_a_profile():
    # `profile` is not a field of the metadata model any more, so a client sending one gets it
    # dropped on the way in rather than stored and later served as a real profile.
    assert "profile" not in DatasetMetadataContent.model_fields

    fileset = _dataset_fileset()
    entity_store = _entity_store(fileset=fileset)
    forged = UpdateFilesetRequest.model_validate(
        {"metadata": {"dataset": {"profile": _minimal_profile().model_dump(mode="json")}}}
    )

    await update_fileset_metadata("ws1", "fs1", forged, entity_store=entity_store, auth_client=_auth())

    persisted = entity_store.update.await_args.args[0]
    assert "profile" not in persisted.metadata["dataset"]
    # And the read path still says "never profiled", not "ready" with a made-up profile.
    assert await get_profile(entity_store, fileset) is None


@pytest.mark.asyncio
async def test_patch_still_applies_ordinary_metadata_edits():
    fileset = _dataset_fileset()
    entity_store = _entity_store(fileset=fileset, profile=_minimal_profile())
    request = UpdateFilesetRequest(
        metadata=FilesetMetadata(dataset=DatasetMetadataContent(schema_defs={"row": {"type": "string"}}))
    )

    await update_fileset_metadata("ws1", "fs1", request, entity_store=entity_store, auth_client=_auth())

    persisted = FilesetMetadata.model_validate(entity_store.update.await_args.args[0].metadata)
    assert persisted.dataset.schema_defs == {"row": {"type": "string"}}
