# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OTLP log management endpoints for the Files Service."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from nemo_platform import AsyncNeMoPlatform
from nmp.common.auth import AuthClient, get_auth_client
from nmp.common.entities.client import (
    EntityClient,
)
from nmp.common.jobs.schemas import PlatformJobLogPage
from nmp.common.service.dependencies import get_entity_client, get_sdk_client
from nmp.core.files.api.endpoint_helpers import (
    get_fileset,
    resolve_storage_secrets_for_user,
)
from nmp.core.files.api.v2.otlp.schemas import (
    OtelExportLogsPartialSuccess,
    OtelExportLogsServiceRequest,
    OtelExportLogsServiceResponse,
    convert_proto_to_request,
    extract_string_value,
    get_resource_attribute,
)
from nmp.core.files.app.backends import storage_impl_factory
from nmp.core.files.app.log_storage import LogEntry, LogStorage, dep_log_storage
from nmp.core.files.exceptions import InvalidFilterError
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2
from pydantic import BaseModel, Field
from starlette.status import (
    HTTP_200_OK,
)

logger = logging.getLogger(__name__)


class LogQueryRequest(BaseModel):
    """Request body for querying logs from a fileset."""

    filters: dict[str, str] = Field(
        default_factory=dict,
        description="Key-value filters to apply to the query",
    )
    limit: int = Field(
        default=100,
        gt=0,
        le=1000,
        description="Maximum number of results to return",
    )
    page_cursor: str | None = Field(
        default=None,
        description="Cursor for pagination",
    )


router = APIRouter()


@router.post(
    "/v2/workspaces/{workspace}/filesets/{name}/otlp/v1/logs/query",
    summary="Query OTLP Logs from Fileset",
    response_model=PlatformJobLogPage,
    status_code=HTTP_200_OK,
)
async def query_otlp_logs(
    workspace: str,
    name: str,
    request: LogQueryRequest,
    entity_store: EntityClient = Depends(get_entity_client),
    log_storage: LogStorage = Depends(dep_log_storage),
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
    auth_client: AuthClient = Depends(get_auth_client),
) -> PlatformJobLogPage:
    """Query logs from parquet files in a fileset.

    This is an internal endpoint that runs DuckDB queries with direct storage
    access.
    """
    logger.debug(
        "Received OTLP logs query request for fileset '%s' in workspace '%s'",
        name,
        workspace,
    )
    fileset = await get_fileset(workspace, name, entity_store)
    secrets = await resolve_storage_secrets_for_user(fileset.storage, workspace, sdk, auth_client)
    storage = storage_impl_factory(fileset.storage, secrets)

    try:
        return await log_storage.query_logs(
            storage=storage,
            filters=request.filters,
            page_size=request.limit,
            page_cursor=request.page_cursor,
        )
    except InvalidFilterError as e:
        logger.error(f"Invalid filter: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid filter: {str(e)}")
    except Exception as e:
        logger.error(f"Error querying logs: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal error processing query request")


@router.post(
    "/v2/workspaces/{workspace}/filesets/{name}/otlp/v1/logs",
    summary="Upload OTLP Logs to Fileset",
    response_model=OtelExportLogsServiceResponse,
    status_code=HTTP_200_OK,
)
async def upload_otlp_logs(
    workspace: str,
    name: str,
    raw_request: Request,
    content_type: str = Header(default="application/json"),
    entity_store: EntityClient = Depends(get_entity_client),
    log_storage: LogStorage = Depends(dep_log_storage),
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
    auth_client: AuthClient = Depends(get_auth_client),
) -> OtelExportLogsServiceResponse:
    """
    Upload OTLP logs to a specified fileset in JSON or Protobuf format.

    Supports both application/json and application/x-protobuf content types.
    """

    logger.debug(
        "Received OTLP logs upload request for fileset '%s' in workspace '%s'",
        name,
        workspace,
    )
    fileset = await get_fileset(workspace, name, entity_store)
    secrets = await resolve_storage_secrets_for_user(fileset.storage, workspace, sdk, auth_client)
    storage = storage_impl_factory(fileset.storage, secrets)

    # Parse request based on content type
    if "protobuf" in content_type.lower():
        # Parse protobuf
        body = await raw_request.body()
        proto_request = logs_service_pb2.ExportLogsServiceRequest()
        try:
            proto_request.ParseFromString(body)
        except Exception as e:
            logger.error(f"Failed to parse protobuf request: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid protobuf format: {str(e)}")
        # Convert to Pydantic model
        request = convert_proto_to_request(proto_request)
    else:
        # Parse JSON
        try:
            json_data = await raw_request.json()
            request = OtelExportLogsServiceRequest(**json_data)
        except Exception as e:
            logger.error(f"Failed to parse JSON request: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

    try:
        log_entries: list[LogEntry] = []
        rejected_count = 0
        error_messages = []
        # Process each ResourceLogs batch
        for resource_logs in request.resourceLogs:
            # Extract required attributes from resource level (applies to all logs in this resource)
            job = get_resource_attribute(resource_logs, "job")
            job_attempt = get_resource_attribute(resource_logs, "job_attempt")
            job_step = get_resource_attribute(resource_logs, "job_step")
            job_task = get_resource_attribute(resource_logs, "job_task")

            # Validate that all required resource attributes are present
            if not job or not job_attempt or not job_step or not job_task:
                missing = []
                if not job:
                    missing.append("job")
                if not job_attempt:
                    missing.append("job_attempt")
                if not job_step:
                    missing.append("job_step")
                if not job_task:
                    missing.append("job_task")
                error_msg = f"Missing required resource attributes: {', '.join(missing)}"
                logger.warning(error_msg)
                # Reject all logs in this resource batch
                for scope_logs in resource_logs.scopeLogs:
                    rejected_count += len(scope_logs.logRecords)
                error_messages.append(error_msg)
                continue

            # Process each ScopeLogs
            for scope_logs in resource_logs.scopeLogs:
                # Process each LogRecord
                for log_record in scope_logs.logRecords:
                    try:
                        # Extract log message from body
                        log_message = ""
                        if log_record.body:
                            log_message = extract_string_value(log_record.body)
                        # Convert timestamp from nanoseconds to datetime.
                        # timeUnixNano is a string representation of nanoseconds since Unix epoch.
                        # Fall back to observedTimeUnixNano if timeUnixNano is missing or zero
                        # (e.g. when the emitter omits the timestamp field).
                        timestamp_ns = int(log_record.timeUnixNano)
                        if timestamp_ns == 0 and log_record.observedTimeUnixNano:
                            timestamp_ns = int(log_record.observedTimeUnixNano)
                        timestamp = datetime.fromtimestamp(timestamp_ns / 1_000_000_000)
                        # Create log entry
                        log_entry = LogEntry(
                            workspace=workspace,
                            job=job,
                            job_attempt=job_attempt,
                            job_step=job_step,
                            job_task=job_task,
                            log_message=log_message,
                            timestamp=timestamp,
                        )
                        log_entries.append(log_entry)
                    except Exception as e:
                        logger.error(f"Error processing log record: {str(e)}")
                        rejected_count += 1
                        error_messages.append(str(e))
        # Insert logs into database
        logger.debug("Inserting %d log entries", len(log_entries))
        if log_entries:
            inserted_count = await log_storage.insert_logs(storage, log_entries=log_entries)
            logger.debug(f"Successfully ingested {inserted_count} log entries")
        # Prepare response
        if rejected_count > 0:
            logger.debug(f"Partially ingested logs: {rejected_count} records rejected")
            # Partial success
            return OtelExportLogsServiceResponse(
                partialSuccess=OtelExportLogsPartialSuccess(
                    rejectedLogRecords=rejected_count,
                    errorMessage=f"Rejected {rejected_count} log records. Errors: {'; '.join(set(error_messages[:5]))}",
                )
            )
        else:
            # Full success
            logger.debug("All log records ingested successfully")
            return OtelExportLogsServiceResponse()
    except Exception as e:
        logger.error(f"Error ingesting logs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error ingesting logs: {str(e)}")
