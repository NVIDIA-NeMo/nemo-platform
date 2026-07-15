# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from nemo_platform_plugin.client.errors import ConflictError as ClientConflictError
from nemo_platform_plugin.client.errors import NemoTransportError
from nemo_platform_plugin.jobs.result_manager import CreateJobResultError
from nmp.common.config import Configuration
from nmp.common.jobs import result_manager as rm
from nmp.common.jobs.file_manager import AsyncFilesetFileManager, FilesetFileManager, TmpDirPath


def _resp(data):
    """Wrap a payload in a NemoResponse-like object whose ``.data()`` returns it."""
    m = MagicMock()
    m.data.return_value = data
    return m


def _conflict_error() -> ClientConflictError:
    """Build the ConflictError the typed client raises on a 409 response."""
    request = httpx.Request("POST", "http://test")
    return ClientConflictError(httpx.Response(status_code=409, json={}, request=request))


# =============================================================================
# FilesetFileManager Factory Tests
# =============================================================================


@patch("nemo_platform_plugin.jobs.file_manager.FilesetFileSystem")
@patch.object(Configuration, "get_platform_config")
def test_result_manager_factory_fileset(mock_platform_config, mock_fs_class, mock_sdk):
    """Test factory creates ResultManager with FilesetFileManager class."""
    mock_platform_config.return_value.base_url = "http://localhost:8080"

    mgr = rm.result_manager_factory(
        job_name="test-job",
        workspace="my-workspace",
        files_sdk=mock_sdk,
        is_async=False,
    )

    assert isinstance(mgr, rm.ResultManager)
    assert mgr.file_manager_cls is FilesetFileManager
    assert mgr.workspace == "my-workspace"
    assert mgr.files_sdk is mock_sdk


@patch("nemo_platform_plugin.jobs.file_manager.FilesetFileSystem")
@patch.object(Configuration, "get_platform_config")
def test_result_manager_factory_fileset_async(mock_platform_config, mock_fs_class, mock_sdk):
    """Test factory creates AsyncResultManager with AsyncFilesetFileManager class."""
    mock_platform_config.return_value.base_url = "http://localhost:8080"

    mgr = rm.result_manager_factory(
        job_name="test-job",
        workspace="my-workspace",
        files_sdk=mock_sdk,
    )

    assert isinstance(mgr, rm.AsyncResultManager)
    assert mgr.file_manager_cls is AsyncFilesetFileManager
    assert mgr.workspace == "my-workspace"


@pytest.mark.asyncio
@patch("nmp.common.jobs.result_manager.result_manager_factory")
async def test_download_from_result_info(mock_factory, tmp_path, mock_sdk):
    """Test download_from_result_info creates manager and downloads artifact."""
    test_file = tmp_path / "artifact.bin"
    test_file.write_bytes(b"test content")

    mock_result_manager = MagicMock()
    mock_result_manager.download_artifact = AsyncMock(return_value=TmpDirPath(tmp_dir=tmp_path, path=test_file))
    mock_factory.return_value = mock_result_manager

    await rm.download_from_result_info(
        result_name="my-result",
        job_name="test-job",
        artifact_url="my-workspace/url-fileset-name#path/to/artifact",
        workspace="my-workspace",
        files_sdk=mock_sdk,
    )

    # Verify factory was called with correct parameters
    call_kwargs = mock_factory.call_args.kwargs
    assert call_kwargs["job_name"] == "test-job"
    assert call_kwargs["workspace"] == "my-workspace"
    assert call_kwargs["files_sdk"] is mock_sdk


def test_create_result_returns_existing_on_conflict_sync(tmp_path, mock_sdk, mock_nmp_sdk, mock_sync_file_manager):
    """Test that sync create_result returns existing result when ConflictError is raised."""
    test_file = tmp_path / "artifact.bin"
    test_file.write_bytes(b"test content")

    # Configure the typed jobs client to raise ConflictError on create, return existing on retrieve.
    existing_result = MagicMock(name="my-result")
    mock_jobs = MagicMock()
    mock_jobs.create_job_result.side_effect = _conflict_error()
    mock_jobs.get_job_result.return_value = _resp(existing_result)
    # Job retrieval provides the fileset name.
    mock_jobs.get_job.return_value = _resp(MagicMock(attempt_id="att-123", fileset="test-fileset"))

    mgr = rm.ResultManager(
        job_name="test-job",
        workspace="test-ws",
        file_manager_cls=FilesetFileManager,
        files_sdk=mock_sdk,
        jobs_sdk=mock_nmp_sdk,
    )

    # Patch the _create_file_manager method to return our mock, and the typed-client
    # factory to return our mock jobs client.
    with (
        patch.object(mgr, "_create_file_manager", return_value=mock_sync_file_manager),
        patch("nemo_platform_plugin.jobs.result_manager.client_from_platform", return_value=mock_jobs),
    ):
        result = mgr.create_result("my-result", test_file)

    mock_jobs.get_job_result.assert_called_once_with(name="my-result", job="test-job", workspace="test-ws")
    assert result is existing_result


def test_create_result_wraps_transport_errors_sync(tmp_path, mock_sdk, mock_nmp_sdk, mock_sync_file_manager):
    test_file = tmp_path / "artifact.bin"
    test_file.write_bytes(b"test content")
    request = httpx.Request("POST", "http://test/apis/jobs/v2/workspaces/test-ws/jobs/test-job/results/my-result")
    mock_jobs = MagicMock()
    mock_jobs.get_job.return_value = _resp(MagicMock(attempt_id="att-123", fileset="test-fileset"))
    mock_jobs.create_job_result.side_effect = NemoTransportError(
        httpx.ConnectError("Connection refused", request=request)
    )
    mgr = rm.ResultManager(
        job_name="test-job",
        workspace="test-ws",
        file_manager_cls=FilesetFileManager,
        files_sdk=mock_sdk,
        jobs_sdk=mock_nmp_sdk,
    )

    with (
        patch.object(mgr, "_create_file_manager", return_value=mock_sync_file_manager),
        patch("nemo_platform_plugin.jobs.result_manager.client_from_platform", return_value=mock_jobs),
        pytest.raises(CreateJobResultError, match="Error creating job result"),
    ):
        mgr.create_result("my-result", test_file)


@pytest.mark.asyncio
async def test_create_result_returns_existing_on_conflict_async(
    tmp_path, mock_sdk, mock_async_nmp_sdk, mock_async_file_manager
):
    """Test that async create_result returns existing result when ConflictError is raised."""
    test_file = tmp_path / "artifact.bin"
    test_file.write_bytes(b"test content")

    # Configure the typed async jobs client to raise ConflictError on create, return existing on retrieve.
    existing_result = MagicMock(name="my-result")
    mock_jobs = MagicMock()
    mock_jobs.create_job_result = AsyncMock(side_effect=_conflict_error())
    mock_jobs.get_job_result = AsyncMock(return_value=_resp(existing_result))
    # Job retrieval provides the fileset name.
    mock_jobs.get_job = AsyncMock(return_value=_resp(MagicMock(attempt_id="att-123", fileset="test-fileset")))

    mgr = rm.AsyncResultManager(
        job_name="test-job",
        workspace="test-ws",
        file_manager_cls=AsyncFilesetFileManager,
        files_sdk=mock_sdk,
        jobs_sdk=mock_async_nmp_sdk,
    )

    # Patch the _create_file_manager method to return our mock, and the typed-client
    # factory to return our mock jobs client.
    with (
        patch.object(mgr, "_create_file_manager", return_value=mock_async_file_manager),
        patch("nemo_platform_plugin.jobs.result_manager.client_from_platform", return_value=mock_jobs),
    ):
        result = await mgr.create_result("my-result", test_file)

    mock_jobs.get_job_result.assert_called_once_with(name="my-result", job="test-job", workspace="test-ws")
    assert result is existing_result


@pytest.mark.asyncio
async def test_create_result_wraps_transport_errors_async(
    tmp_path, mock_sdk, mock_async_nmp_sdk, mock_async_file_manager
):
    test_file = tmp_path / "artifact.bin"
    test_file.write_bytes(b"test content")
    request = httpx.Request("POST", "http://test/apis/jobs/v2/workspaces/test-ws/jobs/test-job/results/my-result")
    mock_jobs = MagicMock()
    mock_jobs.get_job = AsyncMock(return_value=_resp(MagicMock(attempt_id="att-123", fileset="test-fileset")))
    mock_jobs.create_job_result = AsyncMock(
        side_effect=NemoTransportError(httpx.ConnectError("Connection refused", request=request))
    )
    mgr = rm.AsyncResultManager(
        job_name="test-job",
        workspace="test-ws",
        file_manager_cls=AsyncFilesetFileManager,
        files_sdk=mock_sdk,
        jobs_sdk=mock_async_nmp_sdk,
    )

    with (
        patch.object(mgr, "_create_file_manager", return_value=mock_async_file_manager),
        patch("nemo_platform_plugin.jobs.result_manager.client_from_platform", return_value=mock_jobs),
        pytest.raises(CreateJobResultError, match="Error creating job result"),
    ):
        await mgr.create_result("my-result", test_file)


@pytest.mark.asyncio
@patch("nmp.common.jobs.result_manager.result_manager_factory")
@patch("nmp.common.jobs.result_manager.get_async_platform_sdk")
async def test_download_from_result_info_defaults_sdk(mock_get_sdk, mock_factory, tmp_path):
    """Test that download_from_result_info auto-creates SDK when files_sdk is None."""
    mock_sdk = MagicMock()
    mock_get_sdk.return_value = mock_sdk

    test_file = tmp_path / "artifact.bin"
    test_file.write_bytes(b"test content")
    mock_mgr = MagicMock()
    mock_mgr.download_artifact = AsyncMock(return_value=TmpDirPath(tmp_dir=tmp_path, path=test_file))
    mock_factory.return_value = mock_mgr

    await rm.download_from_result_info(
        result_name="my-result",
        job_name="test-job",
        artifact_url="workspace/fileset#path",
        workspace="workspace",
    )

    mock_get_sdk.assert_called_once_with()
    mock_factory.assert_called_once_with(
        job_name="test-job",
        workspace="workspace",
        files_sdk=mock_sdk,
    )
