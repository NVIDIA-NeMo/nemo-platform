# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import psycopg


class ExecutionCleanupRepository:
    """Durable teardown queue for runtime handles orphaned by runner loss."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def list_for_evaluation(self, evaluation_id: str) -> list[dict]:
        """Return attempt-aware cleanup state without exposing backend handles."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT execution_number, runtime, failure_code,
                       retry_after_cleanup, status, teardown_attempts,
                       delete_error, created_at, updated_at, deleted_at
                FROM evaluation_execution_cleanups
                WHERE evaluation_id = %s
                ORDER BY execution_number ASC
                """,
                (evaluation_id,),
            )
            return cur.fetchall()

    def claim_one(self, *, worker_id: str, claim_timeout: float) -> dict | None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                WITH candidate AS (
                    SELECT id
                    FROM evaluation_execution_cleanups
                    WHERE status IN ('pending', 'delete_failed')
                      AND next_attempt_at <= NOW()
                      AND (
                          teardown_claimed_at IS NULL
                          OR teardown_claimed_at < NOW() - (%s * INTERVAL '1 second')
                      )
                    ORDER BY next_attempt_at, id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE evaluation_execution_cleanups cleanup
                SET status = 'deleting',
                    teardown_claimed_at = NOW(),
                    teardown_claimed_by = %s,
                    teardown_attempts = teardown_attempts + 1,
                    updated_at = NOW()
                FROM candidate
                WHERE cleanup.id = candidate.id
                RETURNING cleanup.*
                """,
                (claim_timeout, worker_id),
            )
            return cur.fetchone()

    def mark_failed(self, cleanup_id: int, *, worker_id: str, detail: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE evaluation_execution_cleanups
                SET status = 'delete_failed',
                    delete_error = %s,
                    next_attempt_at = NOW() + (
                        LEAST(300, POWER(2, LEAST(teardown_attempts, 8)))
                        * INTERVAL '1 second'
                    ),
                    teardown_claimed_at = NULL,
                    teardown_claimed_by = NULL,
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'deleting'
                  AND teardown_claimed_by = %s
                """,
                (detail, cleanup_id, worker_id),
            )
