# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Client for querying job logs via Files service.

This is a thin wrapper that delegates log queries to the Files service's
OTLP query endpoint using the typed FilesClient.
"""

import logging

from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import NotFoundError
from nemo_platform_plugin.files.client import AsyncFilesClient
from nemo_platform_plugin.files.types import OtlpLogQueryRequest
from nmp.common.jobs.schemas import PlatformJobLogPage
from nmp.common.sdk_factory import get_async_platform_sdk

logger = logging.getLogger(__name__)


class JobLogsClient:
    """Client for job logs - delegates to Files service via typed FilesClient.

    This client uses the FilesClient to call the Files service's OTLP query
    endpoint, which runs DuckDB queries with direct storage access.
    """

    def __init__(self, sdk: AsyncNeMoPlatform | None = None):
        """Initialize the log client.

        Args:
            sdk: AsyncNeMoPlatform SDK instance. If not provided,
                 creates one using platform config.
        """
        self._sdk = sdk or get_async_platform_sdk()
        self._files_client = client_from_platform(self._sdk, AsyncFilesClient)

    async def query_logs(
        self,
        fileset: str,
        workspace: str,
        filters: dict[str, str] | None = None,
        page_size: int = 100,
        page_cursor: str | None = None,
    ) -> PlatformJobLogPage:
        """Query job logs via Files service OTLP endpoint.

        Args:
            fileset: Fileset containing the parquet logs
            workspace: Workspace name
            filters: Dictionary of filters (job, job_attempt, job_step, job_task)
            page_size: Number of results per page
            page_cursor: Encoded cursor for pagination

        Returns:
            PlatformJobLogPage with data, total count, and pagination cursors
        """
        try:
            body = OtlpLogQueryRequest(
                filters=filters or {},
                limit=page_size,
                page_cursor=page_cursor,
            )
            resp = await self._files_client.query_otlp_logs(
                name=fileset,
                workspace=workspace,
                body=body,
            )
            return resp.data()
        except NotFoundError:
            logger.debug(f"Fileset '{fileset}' not found, returning empty page")
            return PlatformJobLogPage(data=[], total=0, next_page=None, prev_page=None)
        except Exception as e:
            logger.error(f"Error querying logs: {e}")
            raise


def dep_job_logs_client() -> JobLogsClient:
    """FastAPI dependency for JobLogsClient."""
    return JobLogsClient()
