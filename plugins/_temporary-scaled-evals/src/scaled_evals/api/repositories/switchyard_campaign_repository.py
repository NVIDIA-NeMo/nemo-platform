# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Json

from scaled_evals.models.runtime import LaunchHandle, SwitchyardLease

CAMPAIGN_COLUMNS = """
    benchmark_run_id, status, profile_id, config_hash, credential_hash,
    max_concurrent_members, namespace, resource_name, endpoint, metadata,
    cancel_requested_at, claim_owner, claim_expires_at, claim_attempt,
    evidence_status, evidence_object_key, evidence_sha256, evidence_error,
    drain_until, delete_error, deleted_at, created_at, updated_at
"""

QUALIFIED_CAMPAIGN_COLUMNS = """
    c.benchmark_run_id, c.status, c.profile_id, c.config_hash, c.credential_hash,
    c.max_concurrent_members, c.namespace, c.resource_name, c.endpoint, c.metadata,
    c.cancel_requested_at, c.claim_owner, c.claim_expires_at, c.claim_attempt,
    c.evidence_status, c.evidence_object_key, c.evidence_sha256, c.evidence_error,
    c.drain_until, c.delete_error, c.deleted_at, c.created_at, c.updated_at
"""


class SwitchyardCampaignRepository:
    """Durable ownership, permits, and finalization for shared benchmark gateways."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def ensure_and_claim_provisioning(
        self,
        *,
        benchmark_run_id: str,
        profile_id: str,
        config_hash: str,
        credential_hash: str,
        max_concurrent_members: int,
        worker_id: str,
        claim_seconds: float,
    ) -> tuple[dict[str, Any], bool]:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO benchmark_switchyard_campaigns (
                    benchmark_run_id, status, profile_id, config_hash,
                    credential_hash, max_concurrent_members
                )
                VALUES (%s, 'provisioning', %s, %s, %s, %s)
                ON CONFLICT (benchmark_run_id) DO NOTHING
                """,
                (
                    benchmark_run_id,
                    profile_id,
                    config_hash,
                    credential_hash,
                    max_concurrent_members,
                ),
            )
            cur.execute(
                f"""
                SELECT {CAMPAIGN_COLUMNS}
                FROM benchmark_switchyard_campaigns
                WHERE benchmark_run_id = %s
                FOR UPDATE
                """,
                (benchmark_run_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("failed to persist Switchyard campaign")
            expected = (profile_id, config_hash, credential_hash, max_concurrent_members)
            observed = (
                row["profile_id"],
                row["config_hash"],
                row["credential_hash"],
                row["max_concurrent_members"],
            )
            if observed != expected:
                raise RuntimeError("Switchyard campaign execution snapshot does not match")
            now = datetime.now(tz=UTC)
            claimable = (
                row["status"] == "provisioning"
                and row.get("cancel_requested_at") is None
                and (
                    row.get("claim_owner") == worker_id
                    or row.get("claim_expires_at") is None
                    or row["claim_expires_at"] <= now
                )
            )
            if claimable:
                cur.execute(
                    f"""
                    UPDATE benchmark_switchyard_campaigns
                    SET claim_owner = %s,
                        claim_expires_at = NOW() + (%s * INTERVAL '1 second'),
                        claim_attempt = claim_attempt + 1,
                        updated_at = NOW()
                    WHERE benchmark_run_id = %s
                      AND status = 'provisioning'
                      AND cancel_requested_at IS NULL
                    RETURNING {CAMPAIGN_COLUMNS}
                    """,
                    (worker_id, claim_seconds, benchmark_run_id),
                )
                claimed = cur.fetchone()
                if claimed is not None:
                    return claimed, True
            return row, False

    def get(self, benchmark_run_id: str) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT {CAMPAIGN_COLUMNS} FROM benchmark_switchyard_campaigns WHERE benchmark_run_id = %s",
                (benchmark_run_id,),
            )
            return cur.fetchone()

    def renew_provisioning_claim(
        self,
        benchmark_run_id: str,
        *,
        worker_id: str,
        claim_attempt: int,
        claim_seconds: float,
    ) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET claim_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'provisioning'
                  AND claim_owner = %s AND claim_attempt = %s
                  AND cancel_requested_at IS NULL
                """,
                (claim_seconds, benchmark_run_id, worker_id, claim_attempt),
            )
            return cur.rowcount == 1

    def claim_ready_reprovisioning(
        self,
        benchmark_run_id: str,
        *,
        worker_id: str,
        claim_seconds: float,
        detail: str,
    ) -> dict[str, Any] | None:
        """Fence one worker to replace Kubernetes objects missing from a ready campaign."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {CAMPAIGN_COLUMNS}
                FROM benchmark_switchyard_campaigns
                WHERE benchmark_run_id = %s
                FOR UPDATE
                """,
                (benchmark_run_id,),
            )
            row = cur.fetchone()
            if row is None or row["status"] != "ready" or row.get("cancel_requested_at") is not None:
                return None
            cur.execute(
                f"""
                UPDATE benchmark_switchyard_campaigns
                SET status = 'provisioning', claim_owner = %s,
                    claim_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    claim_attempt = claim_attempt + 1, evidence_error = %s,
                    updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'ready'
                  AND cancel_requested_at IS NULL
                RETURNING {CAMPAIGN_COLUMNS}
                """,
                (worker_id, claim_seconds, detail, benchmark_run_id),
            )
            return cur.fetchone()

    def mark_ready(
        self,
        benchmark_run_id: str,
        *,
        worker_id: str,
        claim_attempt: int,
        lease: SwitchyardLease,
    ) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE benchmark_switchyard_campaigns
                SET status = 'ready', namespace = %s, resource_name = %s,
                    endpoint = %s, metadata = %s::jsonb, claim_owner = NULL,
                    claim_expires_at = NULL, evidence_error = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'provisioning'
                  AND claim_owner = %s AND claim_attempt = %s
                  AND cancel_requested_at IS NULL
                RETURNING {CAMPAIGN_COLUMNS}
                """,
                (
                    lease.namespace,
                    lease.name,
                    lease.endpoint,
                    Json(lease.model_dump(mode="json", exclude_none=True)),
                    benchmark_run_id,
                    worker_id,
                    claim_attempt,
                ),
            )
            return cur.fetchone()

    def record_provisioning_lease(
        self,
        benchmark_run_id: str,
        *,
        worker_id: str,
        claim_attempt: int,
        lease: SwitchyardLease,
    ) -> bool:
        """Durably record resource identity before provisioning mutates the cluster."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET namespace = %s, resource_name = %s, endpoint = %s,
                    metadata = %s::jsonb, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'provisioning'
                  AND claim_owner = %s AND claim_attempt = %s
                  AND cancel_requested_at IS NULL
                """,
                (
                    lease.namespace,
                    lease.name,
                    lease.endpoint,
                    Json(lease.model_dump(mode="json", exclude_none=True)),
                    benchmark_run_id,
                    worker_id,
                    claim_attempt,
                ),
            )
            return cur.rowcount == 1

    def mark_provision_failed(
        self,
        benchmark_run_id: str,
        *,
        worker_id: str,
        claim_attempt: int,
        detail: str,
        lease: SwitchyardLease | None = None,
    ) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET status = 'provision_failed', evidence_error = %s,
                    namespace = COALESCE(%s, namespace),
                    resource_name = COALESCE(%s, resource_name),
                    endpoint = COALESCE(%s, endpoint),
                    metadata = COALESCE(%s::jsonb, metadata::jsonb),
                    claim_owner = NULL, claim_expires_at = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'provisioning'
                  AND claim_owner = %s AND claim_attempt = %s
                """,
                (
                    detail,
                    lease.namespace if lease is not None else None,
                    lease.name if lease is not None else None,
                    lease.endpoint if lease is not None else None,
                    Json(lease.model_dump(mode="json", exclude_none=True)) if lease is not None else None,
                    benchmark_run_id,
                    worker_id,
                    claim_attempt,
                ),
            )
            return cur.rowcount == 1

    def mark_ready_unavailable(self, benchmark_run_id: str, *, detail: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET status = 'provision_failed', evidence_error = %s,
                    claim_owner = NULL, claim_expires_at = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'ready'
                """,
                (detail, benchmark_run_id),
            )

    def acquire_launch_permit(
        self,
        *,
        benchmark_run_id: str,
        evaluation_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> str:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, max_concurrent_members, cancel_requested_at
                FROM benchmark_switchyard_campaigns
                WHERE benchmark_run_id = %s
                FOR UPDATE
                """,
                (benchmark_run_id,),
            )
            campaign = cur.fetchone()
            if campaign is None or campaign["status"] != "ready" or campaign.get("cancel_requested_at") is not None:
                return "wait"
            cur.execute(
                """
                SELECT status, permit_owner, permit_expires_at
                FROM benchmark_switchyard_launches
                WHERE evaluation_id = %s
                """,
                (evaluation_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                if existing["status"] == "running":
                    return "resume"
                if existing["status"] == "launching":
                    if existing["permit_owner"] == worker_id:
                        return "launch"
                    if existing["permit_expires_at"] <= datetime.now(tz=UTC):
                        cur.execute(
                            """
                            UPDATE benchmark_switchyard_launches
                            SET permit_owner = %s,
                                permit_expires_at = NOW() + (%s * INTERVAL '1 second'),
                                updated_at = NOW()
                            WHERE evaluation_id = %s AND status = 'launching'
                            """,
                            (worker_id, lease_seconds, evaluation_id),
                        )
                        return "resume"
                return "wait"
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM benchmark_switchyard_launches
                WHERE benchmark_run_id = %s
                  AND status IN ('launching', 'running', 'cleanup_pending')
                """,
                (benchmark_run_id,),
            )
            if int(cur.fetchone()["count"]) >= int(campaign["max_concurrent_members"]):
                return "wait"
            cur.execute(
                """
                INSERT INTO benchmark_switchyard_launches (
                    evaluation_id, benchmark_run_id, status, permit_owner, permit_expires_at
                )
                VALUES (%s, %s, 'launching', %s, NOW() + (%s * INTERVAL '1 second'))
                """,
                (evaluation_id, benchmark_run_id, worker_id, lease_seconds),
            )
            return "launch"

    def mark_launch_running(self, evaluation_id: str, handle: LaunchHandle) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_launches
                SET status = 'running', backend_handle = %s,
                    permit_expires_at = NOW() + INTERVAL '24 hours', updated_at = NOW()
                WHERE evaluation_id = %s AND status = 'launching'
                """,
                (Json(handle.model_dump(mode="json")), evaluation_id),
            )

    def mark_cleanup_pending(self, evaluation_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_launches
                SET status = 'cleanup_pending', permit_expires_at = NOW(), updated_at = NOW()
                WHERE evaluation_id = %s AND status IN ('launching', 'running')
                """,
                (evaluation_id,),
            )

    def acknowledge_cleanup(self, evaluation_id: str, *, not_launched: bool = False) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_launches
                SET status = %s, cleanup_acknowledged_at = NOW(),
                    cleanup_error = NULL, updated_at = NOW()
                WHERE evaluation_id = %s
                """,
                ("not_launched" if not_launched else "cleanup_acknowledged", evaluation_id),
            )

    def claim_cleanup(self, *, worker_id: str, claim_seconds: float) -> dict | None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                WITH candidate AS (
                    SELECT l.evaluation_id
                    FROM benchmark_switchyard_launches l
                    JOIN evaluations e ON e.id = l.evaluation_id
                    WHERE l.status IN ('launching', 'running', 'cleanup_pending')
                      AND e.status IN ('succeeded', 'failed', 'cancelled')
                      AND (l.permit_expires_at IS NULL OR l.permit_expires_at <= NOW())
                    ORDER BY l.updated_at, l.evaluation_id
                    LIMIT 1
                    FOR UPDATE OF l SKIP LOCKED
                )
                UPDATE benchmark_switchyard_launches l
                SET status = 'cleanup_pending', permit_owner = %s,
                    permit_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    cleanup_attempts = cleanup_attempts + 1, updated_at = NOW()
                FROM candidate
                WHERE l.evaluation_id = candidate.evaluation_id
                RETURNING l.evaluation_id, l.benchmark_run_id, l.backend_handle,
                          l.cleanup_attempts
                """,
                (worker_id, claim_seconds),
            )
            return cur.fetchone()

    def mark_cleanup_failed(self, evaluation_id: str, *, detail: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_launches
                SET cleanup_error = %s, permit_expires_at = NOW() + INTERVAL '30 seconds',
                    updated_at = NOW()
                WHERE evaluation_id = %s AND status = 'cleanup_pending'
                """,
                (detail, evaluation_id),
            )

    def abandon_cleanup(self, evaluation_id: str, *, detail: str) -> None:
        """Stop retrying a bounded member cleanup while retaining its failure detail."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_launches
                SET status = 'cleanup_acknowledged', cleanup_acknowledged_at = NOW(),
                    cleanup_error = %s, permit_owner = NULL, permit_expires_at = NULL,
                    updated_at = NOW()
                WHERE evaluation_id = %s AND status = 'cleanup_pending'
                """,
                (detail, evaluation_id),
            )

    def claim_finalizable(self, *, worker_id: str, claim_seconds: float) -> dict[str, Any] | None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                f"""
                WITH candidate AS (
                    SELECT c.benchmark_run_id
                    FROM benchmark_switchyard_campaigns c
                    WHERE c.status IN (
                        'provisioning', 'ready', 'provision_failed',
                        'evidence_failed', 'finalizing'
                    )
                      AND EXISTS (
                          SELECT 1 FROM evaluations e
                          WHERE e.benchmark_run_id = c.benchmark_run_id
                            AND e.deleted_at IS NULL
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM evaluations e
                          WHERE e.benchmark_run_id = c.benchmark_run_id
                            AND e.deleted_at IS NULL
                            AND e.status NOT IN ('succeeded', 'failed', 'cancelled')
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM benchmark_switchyard_launches l
                          WHERE l.benchmark_run_id = c.benchmark_run_id
                            AND l.status IN ('launching', 'running', 'cleanup_pending')
                      )
                      AND (c.claim_expires_at IS NULL OR c.claim_expires_at < NOW())
                    ORDER BY c.updated_at, c.benchmark_run_id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE benchmark_switchyard_campaigns c
                SET status = 'finalizing', claim_owner = %s,
                    claim_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    claim_attempt = claim_attempt + 1, updated_at = NOW()
                FROM candidate
                WHERE c.benchmark_run_id = candidate.benchmark_run_id
                RETURNING {QUALIFIED_CAMPAIGN_COLUMNS}
                """,
                (worker_id, claim_seconds),
            )
            return cur.fetchone()

    def mark_evidence(
        self,
        benchmark_run_id: str,
        *,
        status: str,
        object_key: str | None,
        sha256: str | None,
        error: str | None,
        drain_seconds: float,
        worker_id: str,
    ) -> bool:
        if status not in {"ready", "unavailable"}:
            raise ValueError(status)
        drain_until = datetime.now(tz=UTC) + timedelta(seconds=drain_seconds)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET status = 'draining', evidence_status = %s,
                    evidence_object_key = %s, evidence_sha256 = %s,
                    evidence_error = %s, drain_until = COALESCE(drain_until, %s),
                    claim_owner = NULL, claim_expires_at = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'finalizing'
                  AND claim_owner = %s
                """,
                (
                    status,
                    object_key,
                    sha256,
                    error,
                    drain_until,
                    benchmark_run_id,
                    worker_id,
                ),
            )
            return cur.rowcount == 1

    def mark_finalization_failed(
        self,
        benchmark_run_id: str,
        *,
        worker_id: str,
        detail: str,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET status = 'evidence_failed', evidence_error = %s,
                    claim_owner = NULL, claim_expires_at = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'finalizing' AND claim_owner = %s
                """,
                (detail, benchmark_run_id, worker_id),
            )

    def member_ids(self, benchmark_run_id: str) -> list[str]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM evaluations WHERE benchmark_run_id = %s AND deleted_at IS NULL",
                (benchmark_run_id,),
            )
            return [str(row["id"]) for row in cur.fetchall()]

    def release_member_evidence(self, benchmark_run_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE evaluations
                SET evidence_status = 'building', evidence_requested_at = NOW(),
                    evidence_claimed_at = NULL, evidence_claimed_by = NULL,
                    evidence_error = NULL, archive_status = 'building',
                    archive_requested_at = NOW(), archive_claimed_at = NULL,
                    archive_claimed_by = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND deleted_at IS NULL
                  AND status IN ('succeeded', 'failed', 'cancelled')
                """,
                (benchmark_run_id,),
            )

    def claim_due_deletion(self, *, worker_id: str, claim_seconds: float) -> dict | None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                f"""
                WITH candidate AS (
                    SELECT c.benchmark_run_id
                    FROM benchmark_switchyard_campaigns c
                    WHERE c.status IN ('draining', 'delete_failed', 'deleting')
                      AND c.drain_until <= NOW()
                      AND (c.claim_expires_at IS NULL OR c.claim_expires_at < NOW())
                    ORDER BY c.drain_until, c.benchmark_run_id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE benchmark_switchyard_campaigns c
                SET status = 'deleting', claim_owner = %s,
                    claim_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    claim_attempt = claim_attempt + 1, updated_at = NOW()
                FROM candidate
                WHERE c.benchmark_run_id = candidate.benchmark_run_id
                RETURNING {QUALIFIED_CAMPAIGN_COLUMNS}
                """,
                (worker_id, claim_seconds),
            )
            return cur.fetchone()

    def mark_deleted(self, benchmark_run_id: str, *, worker_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET status = 'deleted', deleted_at = NOW(), delete_error = NULL,
                    claim_owner = NULL, claim_expires_at = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'deleting' AND claim_owner = %s
                  AND resource_name IS NOT NULL
                """,
                (benchmark_run_id, worker_id),
            )

    def mark_delete_unavailable(
        self,
        benchmark_run_id: str,
        *,
        worker_id: str,
        detail: str,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET status = 'deleted', deleted_at = NOW(), delete_error = %s,
                    claim_owner = NULL, claim_expires_at = NULL, updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'deleting' AND claim_owner = %s
                """,
                (detail, benchmark_run_id, worker_id),
            )

    def mark_delete_failed(self, benchmark_run_id: str, *, worker_id: str, detail: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmark_switchyard_campaigns
                SET status = 'delete_failed', delete_error = %s,
                    claim_owner = NULL,
                    claim_expires_at = NOW() + INTERVAL '30 seconds', updated_at = NOW()
                WHERE benchmark_run_id = %s AND status = 'deleting' AND claim_owner = %s
                """,
                (detail, benchmark_run_id, worker_id),
            )
