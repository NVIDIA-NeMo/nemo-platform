# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nmp.core.entities.controllers.workspace_cleanup import WorkspaceCleanup
from nmp.core.entities.entities import Workspace, WorkspaceDeletionStage


def _make_workspace(name: str = "test-workspace") -> Workspace:
    now = datetime.now(tz=timezone.utc)
    return Workspace(
        id="ws-123",
        name=name,
        description="test",
        created_at=now,
        updated_at=now,
    )


class _AsyncIterator:
    """Helper to mock async iterators returned by the NeMo Platform SDK."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


class _MockAsyncPaginatedResponse:
    """Mock for AsyncNemoPaginatedResponse that exposes .items() as an async generator."""

    def __init__(self, items):
        self._items = items

    async def items(self):
        for item in self._items:
            yield item


def _make_mock_files_client(filesets: list | None = None) -> AsyncMock:
    """Build a mock AsyncFilesClient with list_filesets/delete_fileset."""
    mock_files = AsyncMock()
    mock_files.list_filesets = AsyncMock(return_value=_MockAsyncPaginatedResponse(filesets or []))
    mock_files.delete_fileset = AsyncMock()
    return mock_files


def _make_sdk(
    jobs: list | None = None,
    deployments: list | None = None,
    filesets: list | None = None,
) -> tuple[MagicMock, AsyncMock]:
    """Build a MagicMock SDK with async mocks wired to the correct paths.

    Returns (sdk, mock_files_client) so tests can assert on files client calls.
    """
    sdk = MagicMock()
    sdk.jobs.list = AsyncMock(return_value=_AsyncIterator(jobs or []))
    sdk.jobs.cancel = AsyncMock()
    sdk.jobs.delete = AsyncMock()
    sdk.inference.deployments.list = AsyncMock(return_value=_AsyncIterator(deployments or []))
    sdk.inference.deployments.delete = AsyncMock()
    mock_files = _make_mock_files_client(filesets)
    return sdk, mock_files


def _make_job(name: str, status: str = "completed") -> MagicMock:
    job = MagicMock()
    job.name = name
    job.status = status
    return job


def _make_controller(
    workspace_repo: AsyncMock | None = None,
    nmp_sdk: MagicMock | None = None,
) -> WorkspaceCleanup:
    if workspace_repo is None:
        workspace_repo = AsyncMock()
    if nmp_sdk is None:
        nmp_sdk = MagicMock()

    return WorkspaceCleanup(
        nmp_sdk=nmp_sdk,
        workspace_repository=workspace_repo,
    )


_FILES_CLIENT_PATCH = "nmp.core.entities.controllers.workspace_cleanup.client_from_platform"


class TestWorkspaceCleanupStep:
    def test_step_skips_when_stop_signal_set(self):
        import threading

        stop = threading.Event()
        stop.set()
        repo = AsyncMock()
        controller = WorkspaceCleanup(
            nmp_sdk=MagicMock(),
            workspace_repository=repo,
            stop_signal=stop,
        )

        controller.step()

        repo.list_workspaces.assert_not_called()

    def test_step_uses_provided_loop(self):
        loop = asyncio.new_event_loop()
        repo = AsyncMock()
        repo.list_workspaces.return_value = ([], None)
        controller = WorkspaceCleanup(
            nmp_sdk=MagicMock(),
            workspace_repository=repo,
            loop=loop,
        )

        assert controller._loop is loop
        controller.step()
        assert controller.is_healthy
        repo.list_workspaces.assert_called_once()
        loop.close()

    def test_step_sets_healthy_on_success(self):
        repo = AsyncMock()
        repo.list_workspaces.return_value = ([], None)
        controller = _make_controller(workspace_repo=repo)

        assert not controller.is_healthy
        controller.step()
        assert controller.is_healthy

    def test_step_sets_unhealthy_on_failure(self):
        repo = AsyncMock()
        repo.list_workspaces.side_effect = Exception("db error")
        controller = _make_controller(workspace_repo=repo)

        controller.step()
        assert not controller.is_healthy


class TestWorkspaceCleanupAsyncStep:
    @pytest.mark.asyncio
    async def test_no_pending_workspaces(self):
        repo = AsyncMock()
        repo.list_workspaces.return_value = ([], None)
        controller = _make_controller(workspace_repo=repo)

        await controller._async_step()

        repo.mark_workspace_for_deletion.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_workspace_deletion(self):
        workspace = _make_workspace()
        repo = AsyncMock()
        repo.list_workspaces.return_value = ([workspace], None)
        repo.mark_workspace_for_deletion.return_value = True

        sdk = MagicMock()
        sdk.jobs.list = AsyncMock(return_value=_AsyncIterator([]))
        sdk.inference.deployments.list = AsyncMock(return_value=_AsyncIterator([]))

        mock_files = _make_mock_files_client([])
        controller = _make_controller(workspace_repo=repo, nmp_sdk=sdk)

        with patch(_FILES_CLIENT_PATCH, return_value=mock_files):
            await controller._async_step()

        repo.mark_workspace_for_deletion.assert_any_call(
            name="test-workspace",
            deletion_stage=WorkspaceDeletionStage.DELETING,
        )
        repo.delete_workspace.assert_awaited_once_with(name="test-workspace")

    @pytest.mark.asyncio
    async def test_workspace_already_being_processed(self):
        workspace = _make_workspace()
        repo = AsyncMock()
        repo.list_workspaces.return_value = ([workspace], None)
        repo.mark_workspace_for_deletion.return_value = False

        controller = _make_controller(workspace_repo=repo)

        await controller._async_step()

        repo.delete_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_failure_marks_workspace_failed(self):
        workspace = _make_workspace()
        repo = AsyncMock()
        repo.list_workspaces.return_value = ([workspace], None)
        repo.mark_workspace_for_deletion.return_value = True

        sdk = MagicMock()
        sdk.jobs.list = AsyncMock(side_effect=Exception("jobs service down"))

        controller = _make_controller(workspace_repo=repo, nmp_sdk=sdk)

        await controller._async_step()

        repo.mark_workspace_for_deletion.assert_any_call(
            name="test-workspace",
            deletion_stage=WorkspaceDeletionStage.FAILED,
        )
        repo.delete_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_failure_increments_error_counter(self):
        workspace = _make_workspace()
        repo = AsyncMock()
        repo.list_workspaces.return_value = ([workspace], None)
        repo.mark_workspace_for_deletion.return_value = True

        sdk = MagicMock()
        sdk.jobs.list = AsyncMock(side_effect=Exception("boom"))

        controller = _make_controller(workspace_repo=repo, nmp_sdk=sdk)

        with patch.object(controller._cleanup_errors, "add") as mock_add:
            await controller._async_step()
            mock_add.assert_called_once_with(1, attributes={"error_type": "cleanup_failed"})


class TestWorkspaceCleanupJobs:
    @pytest.mark.asyncio
    async def test_cancels_running_jobs_before_deleting(self):
        workspace = _make_workspace()
        running_job = MagicMock()
        running_job.name = "running-job"
        running_job.status = "active"

        sdk = MagicMock()
        sdk.jobs.list = AsyncMock(return_value=_AsyncIterator([running_job]))
        sdk.jobs.cancel = AsyncMock()
        sdk.jobs.delete = AsyncMock()

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        sdk.jobs.cancel.assert_awaited_once_with(
            name="running-job",
            workspace="test-workspace",
        )
        sdk.jobs.delete.assert_awaited_once_with(
            name="running-job",
            workspace="test-workspace",
        )

    @pytest.mark.asyncio
    async def test_deletes_completed_jobs_without_cancelling(self):
        workspace = _make_workspace()
        completed_job = MagicMock()
        completed_job.name = "completed-job"
        completed_job.status = "completed"

        sdk = MagicMock()
        sdk.jobs.list = AsyncMock(return_value=_AsyncIterator([completed_job]))
        sdk.jobs.cancel = AsyncMock()
        sdk.jobs.delete = AsyncMock()

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        sdk.jobs.cancel.assert_not_awaited()
        sdk.jobs.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_continues_on_individual_job_failure(self):
        workspace = _make_workspace()
        job1 = MagicMock()
        job1.name = "fail-job"
        job1.status = "completed"
        job2 = MagicMock()
        job2.name = "ok-job"
        job2.status = "completed"

        sdk = MagicMock()
        sdk.jobs.list = AsyncMock(return_value=_AsyncIterator([job1, job2]))
        sdk.jobs.delete = AsyncMock(side_effect=[Exception("fail"), None])

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        assert sdk.jobs.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_on_list_failure(self):
        workspace = _make_workspace()
        sdk = MagicMock()
        sdk.jobs.list = AsyncMock(side_effect=Exception("unavailable"))

        controller = _make_controller(nmp_sdk=sdk)

        with pytest.raises(Exception, match="unavailable"):
            await controller._cleanup_jobs(workspace)


class TestWorkspaceCleanupDeployments:
    @pytest.mark.asyncio
    async def test_deletes_deployments(self):
        workspace = _make_workspace()
        deployment = MagicMock()
        deployment.name = "test-deployment"

        sdk = MagicMock()
        sdk.inference.deployments.list = AsyncMock(return_value=_AsyncIterator([deployment]))
        sdk.inference.deployments.delete = AsyncMock()

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_deployments(workspace)

        sdk.inference.deployments.delete.assert_awaited_once_with(
            name="test-deployment",
            workspace="test-workspace",
        )

    @pytest.mark.asyncio
    async def test_continues_on_individual_deployment_failure(self):
        workspace = _make_workspace()
        dep1 = MagicMock()
        dep1.name = "dep1"
        dep2 = MagicMock()
        dep2.name = "dep2"

        sdk = MagicMock()
        sdk.inference.deployments.list = AsyncMock(return_value=_AsyncIterator([dep1, dep2]))
        sdk.inference.deployments.delete = AsyncMock(side_effect=[Exception("fail"), None])

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_deployments(workspace)

        assert sdk.inference.deployments.delete.await_count == 2


class TestWorkspaceCleanupFilesets:
    @pytest.mark.asyncio
    async def test_deletes_filesets(self):
        workspace = _make_workspace()
        fileset = MagicMock()
        fileset.name = "test-fileset"

        mock_files = _make_mock_files_client([fileset])
        controller = _make_controller()

        with patch(_FILES_CLIENT_PATCH, return_value=mock_files):
            await controller._cleanup_filesets(workspace)

        mock_files.delete_fileset.assert_awaited_once_with(
            name="test-fileset",
            workspace="test-workspace",
        )

    @pytest.mark.asyncio
    async def test_continues_on_individual_fileset_failure(self):
        workspace = _make_workspace()
        fs1 = MagicMock()
        fs1.name = "fs1"
        fs2 = MagicMock()
        fs2.name = "fs2"

        mock_files = _make_mock_files_client([fs1, fs2])
        mock_files.delete_fileset = AsyncMock(side_effect=[Exception("fail"), None])
        controller = _make_controller()

        with patch(_FILES_CLIENT_PATCH, return_value=mock_files):
            await controller._cleanup_filesets(workspace)

        assert mock_files.delete_fileset.await_count == 2


class TestJobCancellationBranches:
    """Tests for job cancellation logic — covers branches that were previously dead code."""

    @pytest.mark.asyncio
    async def test_cancels_pending_jobs(self):
        workspace = _make_workspace()
        sdk, _ = _make_sdk(jobs=[_make_job("pending-job", status="pending")])

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        sdk.jobs.cancel.assert_awaited_once_with(name="pending-job", workspace="test-workspace")
        sdk.jobs.delete.assert_awaited_once_with(name="pending-job", workspace="test-workspace")

    @pytest.mark.asyncio
    async def test_cancels_created_jobs(self):
        workspace = _make_workspace()
        sdk, _ = _make_sdk(jobs=[_make_job("created-job", status="created")])

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        sdk.jobs.cancel.assert_awaited_once()
        sdk.jobs.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_cancel_terminal_jobs(self):
        workspace = _make_workspace()
        jobs = [
            _make_job("done", status="completed"),
            _make_job("failed", status="error"),
            _make_job("stopped", status="cancelled"),
        ]
        sdk, _ = _make_sdk(jobs=jobs)

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        sdk.jobs.cancel.assert_not_awaited()
        assert sdk.jobs.delete.await_count == 3

    @pytest.mark.asyncio
    async def test_cancel_failure_still_deletes(self):
        """Regression: cancel() throwing must not prevent delete()."""
        workspace = _make_workspace()
        sdk, _ = _make_sdk(jobs=[_make_job("flaky-job", status="active")])
        sdk.jobs.cancel = AsyncMock(side_effect=Exception("cancel failed"))

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        sdk.jobs.cancel.assert_awaited_once()
        sdk.jobs.delete.assert_awaited_once_with(name="flaky-job", workspace="test-workspace")

    @pytest.mark.asyncio
    async def test_mixed_statuses(self):
        workspace = _make_workspace()
        jobs = [
            _make_job("active-job", status="active"),
            _make_job("done-job", status="completed"),
            _make_job("pending-job", status="pending"),
        ]
        sdk, _ = _make_sdk(jobs=jobs)

        controller = _make_controller(nmp_sdk=sdk)
        await controller._cleanup_jobs(workspace)

        cancel_calls = [c.kwargs["name"] for c in sdk.jobs.cancel.call_args_list]
        assert set(cancel_calls) == {"active-job", "pending-job"}
        assert sdk.jobs.delete.await_count == 3
