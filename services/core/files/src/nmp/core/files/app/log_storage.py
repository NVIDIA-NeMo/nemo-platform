# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Log storage operations using DuckDB and StorageImpl.

This module provides local DuckDB-based query and insert operations for job logs,
avoiding the cross-service HTTP overhead of the previous FilesetFileSystem approach.

NOTE: pandas and S3StorageImpl are intentionally imported inside methods
for startup performance. Do not hoist them to module level.

TODO: Right now, this is very Jobs logs specific; in a future MR we should try to make it more generic
"""

import logging
import os
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

import duckdb
from anyio import to_thread
from nmp.common.files.storage_config import S3StorageConfig
from nmp.common.jobs.schemas import (
    InvalidPageCursorError,
    PageCursor,
    PaginationDirection,
    PlatformJobLog,
    PlatformJobLogPage,
)
from nmp.core.files.app.backends.base import StorageImpl
from nmp.core.files.exceptions import InvalidFilterError, InvalidPathError
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_PATH_SEGMENT_RE = re.compile(r"^[\w\-.]+$")


def logs_base_path(storage: StorageImpl, artifact_base_path: str | None = None) -> str:
    """Hive root for job logs, optionally nested under a per-job ``artifact_base_path``.

    ``artifact_base_path`` is caller-supplied, and ``get_duckdb_path`` is a plain join with no
    traversal check of its own, so validate the segments here.
    """
    if not artifact_base_path:
        return storage.get_duckdb_path("logs")
    segments = artifact_base_path.split("/")
    if any(segment in {".", ".."} or not _PATH_SEGMENT_RE.match(segment) for segment in segments):
        raise InvalidPathError(
            f"Artifact base path '{artifact_base_path}' is not a relative path within the fileset. "
            "Ensure that paths such as ../.. are not used in the path."
        )
    return storage.get_duckdb_path(f"{artifact_base_path}/logs")


class LogEntry(BaseModel):
    """Internal representation of a log entry for storage."""

    workspace: str
    job: str
    job_attempt: str
    job_step: str
    job_task: str
    log_message: str
    timestamp: datetime


class LogStorage:
    """Handles log storage operations using DuckDB and StorageImpl.

    This class is stateless - each operation creates its own DuckDB connection.
    This ensures thread safety when operations run concurrently in the thread pool.

    For local storage: Uses direct path access with DuckDB
    For S3 storage: Uses s3:// URIs with DuckDB's httpfs extension
    """

    # Partition columns in Hive directory order
    PARTITION_COLUMNS = ("job", "job_attempt", "job_step", "job_task")
    SAFE_PARTITION_VALUE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

    @staticmethod
    def _load_s3_extensions(conn: duckdb.DuckDBPyConnection) -> None:
        """Load DuckDB extensions required for S3 (aws, httpfs).

        Load explicitly so DuckDB does not try to auto-install at runtime, which
        can fail in environments without outbound network. Extensions should be
        pre-installed at image build time (see Dockerfile.nmp-core).
        """
        conn.execute("LOAD aws")
        conn.execute("LOAD httpfs")

    @staticmethod
    def _configure_s3_secret(conn: duckdb.DuckDBPyConnection, config: S3StorageConfig) -> None:
        """Configure DuckDB S3 secret for accessing the storage backend.

        Only supports credential_chain provider (use_sdk_auth=True) since log storage
        is only used with the platform's default_storage_config.
        """
        # Build secret parameters - always use credential_chain
        params = ["TYPE s3", "PROVIDER credential_chain"]

        if config.region:
            # Escape single quotes to prevent SQL syntax issues
            region = config.region.replace("'", "''")
            params.append(f"REGION '{region}'")

        if config.endpoint_url:
            # Extract just the host for DuckDB ENDPOINT
            parsed = urlparse(config.endpoint_url)
            endpoint = parsed.netloc.replace("'", "''")
            params.append(f"ENDPOINT '{endpoint}'")
            # OCI and some S3-compatible services need path-style URLs
            params.append("URL_STYLE 'path'")
            # Disable SSL for HTTP endpoints
            if parsed.scheme == "http":
                params.append("USE_SSL 'false'")

        secret_sql = f"CREATE OR REPLACE SECRET nmp_s3 ({', '.join(params)})"
        conn.execute(secret_sql)

    @classmethod
    def _build_query_path(cls, base_path: str, filters: dict[str, str]) -> str:
        """Build an optimized parquet path pattern using partition filters.

        Hive partitioning uses directory structure: job=X/job_attempt=Y/job_step=Z/job_task=W/
        By pushing filters into the path, we avoid scanning unrelated partitions.

        Args:
            base_path: Base logs directory path
            filters: Query filters (may include partition and non-partition keys)

        Returns:
            Optimized glob pattern for read_parquet
        """
        path_parts = [base_path]

        # Add partition filters to path in order (must be contiguous from root)
        for col in cls.PARTITION_COLUMNS:
            if col in filters:
                path_parts.append(f"{col}={filters[col]}")
            else:
                # Can't skip partition levels in Hive, stop here
                break

        # Add glob for remaining levels
        path_parts.append("**/*.parquet")
        return "/".join(path_parts)

    async def query_logs(
        self,
        storage: StorageImpl,
        filters: dict[str, str] | None = None,
        page_size: int = 100,
        page_cursor: str | None = None,
        artifact_base_path: str | None = None,
    ) -> PlatformJobLogPage:
        """Query logs from parquet files using direct storage access.

        Runs DuckDB queries in a thread pool to avoid blocking the event loop.
        When ``artifact_base_path`` is set, logs are read from ``<artifact_base_path>/logs``
        (must match the value used at insert time).
        """
        direction = PaginationDirection.FORWARD
        current_page = 1
        if page_cursor:
            try:
                cursor_obj = PageCursor.decode(page_cursor)
                current_page = cursor_obj.start_id
                direction = cursor_obj.direction
            except ValueError:
                raise InvalidPageCursorError("Invalid page cursor")

        base_path = logs_base_path(storage, artifact_base_path)

        return await to_thread.run_sync(
            self._query_logs_sync,
            base_path,
            filters or {},
            page_size,
            current_page,
            direction,
            storage,
        )

    @classmethod
    def _query_logs_sync(
        cls,
        base_path: str,
        filters: dict[str, str],
        page_size: int,
        current_page: int,
        direction: PaginationDirection,
        storage: StorageImpl,
    ) -> PlatformJobLogPage:
        """Synchronous log query implementation (runs in thread pool).

        Uses a window function (COUNT(*) OVER()) to get total count in a single
        query pass, avoiding the overhead of a separate COUNT query.

        Optimizes glob pattern by pushing partition filters into the path,
        reducing filesystem scanning when filtering by job/attempt/step/task.
        """
        conn = duckdb.connect(
            ":memory:",
            config={
                "autoload_known_extensions": "false",
                "autoinstall_known_extensions": "false",
            },
        )
        try:
            from nmp.core.files.app.backends.s3 import S3StorageImpl

            if isinstance(storage, S3StorageImpl):
                cls._load_s3_extensions(conn)
                cls._configure_s3_secret(conn, storage.config)

            if filters:
                for key, value in filters.items():
                    if key in cls.PARTITION_COLUMNS and not cls.SAFE_PARTITION_VALUE.fullmatch(value):
                        raise InvalidFilterError(f"Invalid partition value: {value} for key: {key}.")
            query_path = cls._build_query_path(base_path, filters)
            base_table = f"read_parquet('{query_path}', hive_partitioning=1)"

            # Determine which filters were pushed into path vs need WHERE clause
            # Filters are pushed contiguously from the start of PARTITION_COLUMNS
            path_filters: set[str] = set()
            for col in cls.PARTITION_COLUMNS:
                if col in filters:
                    path_filters.add(col)
                else:
                    break

            # Build WHERE clause for remaining filters not in path
            where_clauses = []
            params = []
            for key, value in filters.items():
                if key not in path_filters:
                    # Only allow filters that are in the LogEntry model and nothing else
                    if key not in LogEntry.model_fields.keys():
                        raise InvalidFilterError(
                            f"Invalid filter key: {key}. Allowed keys are: {LogEntry.model_fields.keys()}"
                        )
                    where_clauses.append(f"{key} = ?")
                    params.append(value)
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query_direction = "ASC" if direction == PaginationDirection.FORWARD else "DESC"
            offset = (current_page - 1) * page_size

            # Single query with window function for total count
            # Fetch page_size + 1 to check if there are more results
            query = f"""
                SELECT
                    workspace, job, job_attempt, job_step, job_task,
                    log_message, timestamp,
                    COUNT(*) OVER() as _total_count
                FROM {base_table}
                WHERE {where_clause}
                ORDER BY timestamp {query_direction}
                LIMIT ? OFFSET ?
            """
            sql = query.strip()
            if ";" in sql.rstrip(" ;\n\t"):
                logger.error(f"Multiple SQL statements detected in query: {sql}")
                raise ValueError("Multiple SQL statements detected in query")
            result = conn.execute(query, params + [page_size + 1, offset])
            if result.description is None:
                raise RuntimeError("Cannot read description from DuckDB result")

            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            logs = [dict(zip(columns, row)) for row in rows]

            # Extract total count from first row (all rows have same _total_count)
            total_count = logs[0]["_total_count"] if logs else 0

            has_more = len(logs) > page_size
            if has_more:
                logs = logs[:page_size]

            log_lines = [
                PlatformJobLog(
                    timestamp=entry["timestamp"],
                    job=entry["job"],
                    job_step=entry["job_step"],
                    job_task=entry["job_task"],
                    message=entry["log_message"],
                )
                for entry in logs
            ]

            # Calculate pagination cursors
            next_page: str | None = None
            prev_page: str | None = None

            if direction == PaginationDirection.FORWARD:
                if has_more:
                    next_page = PageCursor(start_id=current_page + 1, direction=PaginationDirection.FORWARD).encode()
                if current_page > 1:
                    prev_page = PageCursor(start_id=current_page - 1, direction=PaginationDirection.FORWARD).encode()
            else:
                if has_more:
                    prev_page = PageCursor(
                        start_id=current_page + 1,
                        direction=PaginationDirection.BACKWARD,
                    ).encode()
                if current_page > 1:
                    next_page = PageCursor(
                        start_id=current_page - 1,
                        direction=PaginationDirection.BACKWARD,
                    ).encode()

            return PlatformJobLogPage(
                data=log_lines,
                total=total_count,
                next_page=next_page,
                prev_page=prev_page,
            )

        except duckdb.IOException as e:
            if "No files found that match the pattern" in str(e):
                return PlatformJobLogPage(data=[], total=0, next_page=None, prev_page=None)
            logger.exception("IO error when querying logs")
            raise
        finally:
            conn.close()

    async def insert_logs(
        self, storage: StorageImpl, log_entries: list[LogEntry], artifact_base_path: str | None = None
    ) -> int:
        """Insert log entries into the Parquet storage.

        Uses DuckDB to write Hive-partitioned parquet files directly to the
        storage path. When ``artifact_base_path`` is set, logs nest under ``<artifact_base_path>/logs``.
        """
        if not log_entries:
            return 0

        base_path = logs_base_path(storage, artifact_base_path)

        return await to_thread.run_sync(
            self._insert_logs_sync,
            log_entries,
            base_path,
            storage,
        )

    @classmethod
    def _insert_logs_sync(cls, log_entries: list[LogEntry], base_path: str, storage: StorageImpl) -> int:
        """Synchronous log insert implementation (runs in thread pool)."""
        conn = duckdb.connect(":memory:")
        table_name = f"temp_logs_{uuid.uuid4().hex[:8]}"

        try:
            from nmp.core.files.app.backends.local import LocalStorageImpl
            from nmp.core.files.app.backends.s3 import S3StorageImpl

            # DuckDB COPY creates the leaf + partition dirs but not intermediate parents, so a
            # nested base path (e.g. <root>/jobs/<job>/logs) needs its parents created first.
            if isinstance(storage, LocalStorageImpl):
                os.makedirs(base_path, exist_ok=True)

            if isinstance(storage, S3StorageImpl):
                cls._load_s3_extensions(conn)
                cls._configure_s3_secret(conn, storage.config)

            import pandas as pd

            df = pd.DataFrame([entry.model_dump() for entry in log_entries])
            conn.register(table_name, df)

            insert_query = f"""
                COPY (
                    SELECT workspace, job, job_attempt, job_step, job_task, log_message, timestamp
                    FROM {table_name}
                    ORDER BY timestamp
                ) TO '{base_path}' (
                    FORMAT PARQUET,
                    PARTITION_BY (job, job_attempt, job_step, job_task),
                    APPEND
                )
            """
            conn.execute(insert_query)
            logger.debug(f"Successfully inserted {len(log_entries)} log entries")
            return len(log_entries)

        except Exception:
            logger.exception("Failed to insert log entries")
            raise
        finally:
            conn.close()


def dep_log_storage() -> LogStorage:
    """FastAPI dependency for LogStorage."""
    return LogStorage()
