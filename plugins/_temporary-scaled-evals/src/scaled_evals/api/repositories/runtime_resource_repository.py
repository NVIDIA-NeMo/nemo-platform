# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Json

from scaled_evals.models.runtime import SwitchyardLease

RUNTIME_RESOURCE_COLUMNS = """
    id, evaluation_id, execution_number, kind, status, profile_id, namespace,
    resource_name, endpoint, metadata, drain_until, teardown_claimed_at,
    teardown_claimed_by, teardown_attempts, delete_error, deleted_at, created_at,
    updated_at
"""

RUNTIME_RESOURCE_RETURNING_R_COLUMNS = """
    r.id, r.evaluation_id, r.execution_number, r.kind, r.status, r.profile_id,
    r.namespace, r.resource_name, r.endpoint, r.metadata, r.drain_until,
    r.teardown_claimed_at, r.teardown_claimed_by, r.teardown_attempts, r.delete_error,
    r.deleted_at, r.created_at, r.updated_at
"""

_CLAIM_SWITCHYARD_TEARDOWN_SQL = (
    """
    WITH candidate AS (
        SELECT r.id
        FROM evaluation_runtime_resources r
        JOIN evaluations e ON e.id = r.evaluation_id
        WHERE r.kind = 'switchyard'
          AND (
              (
                  r.status IN ('draining', 'deleting', 'delete_failed')
                  AND (
                      (r.drain_until IS NOT NULL AND r.drain_until <= NOW())
                      OR (
                          r.status = 'deleting'
                          AND r.drain_until IS NULL
                          AND r.updated_at <= NOW() - (%s * INTERVAL '1 second')
                      )
                  )
              )
              OR (
                  r.status = 'provisioned'
                  AND e.status IN ('succeeded', 'failed', 'cancelled')
                  AND r.updated_at <= NOW() - INTERVAL '5 minutes'
              )
          )
          AND (
              r.teardown_claimed_at IS NULL
              OR r.teardown_claimed_at < NOW() - (%s * INTERVAL '1 second')
          )
        ORDER BY COALESCE(r.drain_until, r.updated_at) ASC, r.id ASC
        LIMIT 1
        FOR UPDATE OF r SKIP LOCKED
    )
    UPDATE evaluation_runtime_resources r
    SET status = 'deleting',
        teardown_claimed_at = NOW(),
        teardown_claimed_by = %s,
        teardown_attempts = teardown_attempts + 1,
        updated_at = NOW()
    FROM candidate
    WHERE r.id = candidate.id
    RETURNING """
    + RUNTIME_RESOURCE_RETURNING_R_COLUMNS
)


class RuntimeResourceRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def upsert_switchyard_provisioned(
        self,
        *,
        evaluation_id: str,
        execution_number: int,
        lease: SwitchyardLease,
    ) -> dict:
        metadata = lease.model_dump(mode="json", exclude_none=True)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO evaluation_runtime_resources (
                    evaluation_id, execution_number, kind, status, profile_id, namespace,
                    resource_name, endpoint, metadata
                )
                VALUES (%s, %s, 'switchyard', 'provisioned', %s, %s, %s, %s, %s)
                ON CONFLICT (evaluation_id, execution_number, kind) DO UPDATE
                SET status = 'provisioned',
                    profile_id = EXCLUDED.profile_id,
                    namespace = EXCLUDED.namespace,
                    resource_name = EXCLUDED.resource_name,
                    endpoint = EXCLUDED.endpoint,
                    metadata = EXCLUDED.metadata,
                    drain_until = NULL,
                    teardown_claimed_at = NULL,
                    teardown_claimed_by = NULL,
                    delete_error = NULL,
                    deleted_at = NULL,
                    updated_at = NOW()
                RETURNING {RUNTIME_RESOURCE_COLUMNS}
                """,
                (
                    evaluation_id,
                    execution_number,
                    lease.profile_id,
                    lease.namespace,
                    lease.name,
                    lease.endpoint,
                    Json(metadata),
                ),
            )
            return cur.fetchone()

    def get_switchyard(self, evaluation_id: str, execution_number: int) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {RUNTIME_RESOURCE_COLUMNS}
                FROM evaluation_runtime_resources
                WHERE evaluation_id = %s
                  AND execution_number = %s
                  AND kind = 'switchyard'
                """,
                (evaluation_id, execution_number),
            )
            return cur.fetchone()

    def mark_switchyard_draining(
        self,
        evaluation_id: str,
        execution_number: int,
        *,
        drain_seconds: float,
    ) -> dict | None:
        drain_until = datetime.now(tz=UTC) + timedelta(seconds=drain_seconds)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE evaluation_runtime_resources
                SET status = 'draining',
                    drain_until = COALESCE(drain_until, %s),
                    teardown_claimed_at = NULL,
                    teardown_claimed_by = NULL,
                    updated_at = NOW()
                WHERE evaluation_id = %s
                  AND execution_number = %s
                  AND kind = 'switchyard'
                  AND status IN ('provisioned', 'draining', 'delete_failed')
                RETURNING {RUNTIME_RESOURCE_COLUMNS}
                """,
                (drain_until, evaluation_id, execution_number),
            )
            return cur.fetchone()

    def claim_due_switchyard_teardown(
        self,
        *,
        claim_timeout: float,
        worker_id: str,
    ) -> dict | None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                _CLAIM_SWITCHYARD_TEARDOWN_SQL,
                (claim_timeout, claim_timeout, worker_id),
            )
            return cur.fetchone()

    def mark_deleted(self, resource_id: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE evaluation_runtime_resources
                SET status = 'deleted',
                    deleted_at = NOW(),
                    teardown_claimed_at = NULL,
                    teardown_claimed_by = NULL,
                    delete_error = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (resource_id,),
            )

    def mark_delete_failed(self, resource_id: int, detail: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE evaluation_runtime_resources
                SET status = 'delete_failed',
                    delete_error = %s,
                    teardown_claimed_at = NULL,
                    teardown_claimed_by = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (detail, resource_id),
            )


def switchyard_lease_from_row(row: dict[str, Any] | None) -> SwitchyardLease | None:
    if row is None:
        return None
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return None
    if not isinstance(metadata, dict):
        return None
    try:
        return SwitchyardLease.model_validate(metadata)
    except Exception:  # noqa: BLE001 — caller records malformed persisted metadata
        return None
