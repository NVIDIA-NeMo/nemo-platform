# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import threading

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import AsyncFilesClient
from nemo_platform_plugin.jobs.client import AsyncJobsClient
from nemo_platform_plugin.jobs.schemas import PlatformJobStatus
from nmp.common.api.filter import ComparisonOperation, FilterOperator
from nmp.common.controller.controller import Controller
from nmp.common.observability import start_span_with_ctx
from nmp.core.entities.app.ctx import WorkspaceCleanupContext
from nmp.core.entities.app.repository.workspace import WorkspaceRepositoryInterface
from nmp.core.entities.entities import Workspace, WorkspaceDeletionStage
from opentelemetry import metrics, trace

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)
logger = logging.getLogger(__name__)

_TERMINAL_JOB_STATUSES: frozenset[PlatformJobStatus] = frozenset(
    {PlatformJobStatus.COMPLETED, PlatformJobStatus.ERROR, PlatformJobStatus.CANCELLED}
)


class WorkspaceCleanup(Controller):
    def __init__(
        self,
        nmp_sdk: AsyncNeMoPlatform,
        workspace_repository: WorkspaceRepositoryInterface,
        stop_signal: threading.Event | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._nmp_sdk = nmp_sdk
        self._workspace_repository = workspace_repository
        self._stop_signal = stop_signal
        self._is_healthy = False
        self._loop = loop or asyncio.new_event_loop()

        self._cleanup_total = meter.create_counter(
            name="nmp.entities.workspace.cleanup.total",
            description="Total number of workspace cleanup attempts",
        )
        self._cleanup_errors = meter.create_counter(
            name="nmp.entities.workspace.cleanup.errors",
            description="Number of workspace cleanup errors",
        )

    @property
    def is_healthy(self) -> bool:
        return self._is_healthy

    def step(self):
        if self._stop_signal and self._stop_signal.is_set():
            logger.debug("Stop signal received, skipping cleanup step")
            return
        logger.debug("Running workspace cleanup routine")
        try:
            self._loop.run_until_complete(self._async_step())
            self._is_healthy = True
        except Exception as e:
            logger.error(f"Workspace cleanup step failed: {e}", exc_info=True)
            self._is_healthy = False

    async def _async_step(self):
        with tracer.start_as_current_span("workspace_cleanup/fetch_pending"):
            cleanup_filter = ComparisonOperation(
                operator=FilterOperator.EQ,
                field="deletion_stage",
                value=WorkspaceDeletionStage.PENDING,
            )
            workspaces, _ = await self._workspace_repository.list_workspaces(
                filter_op=cleanup_filter,
                page_size=1,
            )
            if not workspaces:
                logger.debug("No workspaces pending deletion")
                return

        workspace = workspaces[0]
        self._cleanup_total.add(1)

        with start_span_with_ctx(
            tracer,
            "workspace_cleanup/delete_workspace",
            WorkspaceCleanupContext(workspace_name=workspace.name),
        ):
            logger.info(f"Processing workspace deletion: {workspace.name}")

            try:
                success = await self._workspace_repository.mark_workspace_for_deletion(
                    name=workspace.name,
                    deletion_stage=WorkspaceDeletionStage.DELETING,
                )
                if not success:
                    logger.info(f"Workspace already being processed: {workspace.name}")
                    return

                await self._cleanup_jobs(workspace)
                await self._cleanup_deployments(workspace)
                await self._cleanup_filesets(workspace)

                await self._workspace_repository.delete_workspace(name=workspace.name)
                logger.info(f"Successfully deleted workspace: {workspace.name}")

            except Exception as e:
                logger.error(
                    f"Failed to cleanup workspace {workspace.name}: {e}",
                    exc_info=True,
                )
                self._cleanup_errors.add(
                    1,
                    attributes={"error_type": "cleanup_failed"},
                )
                await self._workspace_repository.mark_workspace_for_deletion(
                    name=workspace.name,
                    deletion_stage=WorkspaceDeletionStage.FAILED,
                )

    @tracer.start_as_current_span("workspace_cleanup/cleanup_jobs")
    async def _cleanup_jobs(self, workspace: Workspace) -> None:
        logger.info(f"Cleaning up jobs for workspace: {workspace.name}")
        try:
            jobs_client = client_from_platform(self._nmp_sdk, AsyncJobsClient)
            jobs = [job async for job in (await jobs_client.list_jobs(workspace=workspace.name)).items()]

            for job in jobs:
                if job.status not in _TERMINAL_JOB_STATUSES:
                    try:
                        logger.info(f"Cancelling job: {job.name}")
                        await jobs_client.cancel_job(
                            name=job.name,
                            workspace=workspace.name,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to cancel job {job.name}: {e}")

                try:
                    logger.info(f"Deleting job: {job.name}")
                    await jobs_client.delete_job(
                        name=job.name,
                        workspace=workspace.name,
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete job {job.name}: {e}")

        except Exception as e:
            logger.error(f"Failed to list jobs for workspace {workspace.name}: {e}")
            raise

    @tracer.start_as_current_span("workspace_cleanup/cleanup_deployments")
    async def _cleanup_deployments(self, workspace: Workspace) -> None:
        logger.info(f"Cleaning up deployments for workspace: {workspace.name}")
        try:
            deployments_response = await self._nmp_sdk.inference.deployments.list(workspace=workspace.name)
            deployments = [deployment async for deployment in deployments_response]

            for deployment in deployments:
                try:
                    logger.info(f"Deleting deployment: {deployment.name}")
                    await self._nmp_sdk.inference.deployments.delete(
                        name=deployment.name,
                        workspace=workspace.name,
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete deployment {deployment.name}: {e}")

        except Exception as e:
            logger.error(f"Failed to list deployments for workspace {workspace.name}: {e}")
            raise

    @tracer.start_as_current_span("workspace_cleanup/cleanup_filesets")
    async def _cleanup_filesets(self, workspace: Workspace) -> None:
        logger.info(f"Cleaning up filesets for workspace: {workspace.name}")
        try:
            files = client_from_platform(self._nmp_sdk, AsyncFilesClient)
            filesets_response = await files.list_filesets(workspace=workspace.name)

            async for fileset in filesets_response.items():
                try:
                    logger.info(f"Deleting fileset: {fileset.name}")
                    await files.delete_fileset(
                        name=fileset.name,
                        workspace=workspace.name,
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete fileset {fileset.name}: {e}")

        except Exception as e:
            logger.error(f"Failed to list filesets for workspace {workspace.name}: {e}")
            raise
