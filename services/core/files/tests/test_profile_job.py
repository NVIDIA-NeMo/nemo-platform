# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the fileset-profiling job helper and endpoint."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from nemo_platform_plugin.files.dataset_profile import DatasetProfile, SamplingInfo
from nemo_platform_plugin.files.metadata import DatasetMetadataContent, FilesetMetadata
from nmp.common.entities.client import EntityNotFoundError
from nmp.core.files.api.v2.filesets.endpoints import get_fileset_profile, profile_fileset
from nmp.core.files.api.v2.filesets.schemas import ProfileFilesetResponse
from nmp.core.files.app.profile_job import _build_platform_spec, submit_profile_job


def _minimal_profile() -> DatasetProfile:
    return DatasetProfile(
        created_at=datetime(2026, 1, 1),
        sampling=SamplingInfo(rows_scanned=1, rows_present=1, files_read=1, files_present=1, bytes_present=100),
        partitions=[],
    )


def test_build_platform_spec_targets_profiler_task():
    spec = _build_platform_spec("ws1", "fs1")

    steps = spec["steps"]
    assert len(steps) == 1
    step = steps[0]
    assert step["name"] == "profile"
    assert step["config"] == {"workspace": "ws1", "fileset": "fs1"}

    executor = step["executor"]
    assert executor["provider"] == "cpu"
    assert executor["profile"] == "default"

    container = executor["container"]
    assert container["entrypoint"] == ["python", "-m"]
    assert container["command"] == ["nemo_datasets_plugin.tasks.profile"]
    assert "nmp-cpu-tasks" in container["image"]


@pytest.mark.asyncio
async def test_submit_profile_job_creates_job_with_expected_spec():
    job = SimpleNamespace(name="profile-fs1-abcd1234", id="job-id", status="created")
    sdk = SimpleNamespace(jobs=SimpleNamespace(create=AsyncMock(return_value=job)))

    result = await submit_profile_job(sdk, workspace="ws1", fileset_name="fs1")

    assert result is job
    sdk.jobs.create.assert_awaited_once()
    kwargs = sdk.jobs.create.await_args.kwargs
    assert kwargs["source"] == "files"
    assert kwargs["spec"] == {"fileset": "fs1"}
    assert kwargs["workspace"] == "ws1"
    assert kwargs["name"].startswith("profile-fs1-")
    assert kwargs["platform_spec"]["steps"][0]["config"] == {"workspace": "ws1", "fileset": "fs1"}


@pytest.mark.asyncio
async def test_profile_fileset_endpoint_submits_and_returns_job():
    entity_store = AsyncMock()
    entity_store.get.return_value = SimpleNamespace(name="fs1")
    job = SimpleNamespace(name="profile-fs1-abcd1234", id="job-id", status="created")
    sdk = SimpleNamespace(jobs=SimpleNamespace(create=AsyncMock(return_value=job)))

    resp = await profile_fileset("ws1", "fs1", entity_store=entity_store, sdk=sdk)

    assert isinstance(resp, ProfileFilesetResponse)
    assert resp.job_name == "profile-fs1-abcd1234"
    assert resp.job_id == "job-id"
    assert resp.status == "created"
    assert resp.workspace == "ws1"
    assert resp.fileset == "fs1"


@pytest.mark.asyncio
async def test_profile_fileset_endpoint_404_when_missing():
    entity_store = AsyncMock()
    entity_store.get.side_effect = EntityNotFoundError("not found")
    sdk = SimpleNamespace(jobs=SimpleNamespace(create=AsyncMock()))

    with pytest.raises(HTTPException) as exc:
        await profile_fileset("ws1", "missing", entity_store=entity_store, sdk=sdk)

    assert exc.value.status_code == 404
    sdk.jobs.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_fileset_profile_returns_stored_profile():
    profile = _minimal_profile()
    fileset = SimpleNamespace(metadata=FilesetMetadata(dataset=DatasetMetadataContent(profile=profile)))
    entity_store = AsyncMock()
    entity_store.get.return_value = fileset

    result = await get_fileset_profile("ws1", "fs1", entity_store=entity_store)

    assert result is profile


@pytest.mark.asyncio
async def test_get_fileset_profile_404_when_not_profiled():
    fileset = SimpleNamespace(metadata=FilesetMetadata(dataset=None))
    entity_store = AsyncMock()
    entity_store.get.return_value = fileset

    with pytest.raises(HTTPException) as exc:
        await get_fileset_profile("ws1", "fs1", entity_store=entity_store)

    assert exc.value.status_code == 404
