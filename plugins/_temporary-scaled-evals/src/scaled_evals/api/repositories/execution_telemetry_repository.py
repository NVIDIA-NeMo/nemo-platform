# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import psycopg

from scaled_evals.api.redaction import redact_secret_text


class ExecutionTelemetryRepository:
    """Persist bounded portable facts for each evaluation execution."""

    _PHASE_COLUMNS = {
        "provisioning": "provisioning_started_at",
        "running": "running_started_at",
    }

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def record_phase(
        self,
        evaluation_id: str,
        *,
        execution_number: int,
        phase: str,
        terminal_status: str | None = None,
    ) -> None:
        if phase == "terminal":
            if terminal_status not in {"succeeded", "failed", "cancelled"}:
                raise ValueError("terminal phase requires a terminal status")
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evaluation_execution_telemetry (
                        evaluation_id, execution_number, terminal_at, terminal_status,
                        failure_phase
                    ) VALUES (
                        %s, %s, NOW(), %s,
                        CASE WHEN %s = 'failed' THEN 'provisioning' END
                    )
                    ON CONFLICT (evaluation_id, execution_number) DO UPDATE SET
                        terminal_at = COALESCE(
                            evaluation_execution_telemetry.terminal_at,
                            EXCLUDED.terminal_at
                        ),
                        terminal_status = EXCLUDED.terminal_status,
                        failure_phase = CASE
                            WHEN EXCLUDED.terminal_status != 'failed' THEN
                                evaluation_execution_telemetry.failure_phase
                            WHEN evaluation_execution_telemetry.running_started_at IS NULL THEN
                                'provisioning'
                            ELSE 'runtime'
                        END,
                        updated_at = NOW()
                    """,
                    (evaluation_id, execution_number, terminal_status, terminal_status),
                )
            return

        column = self._PHASE_COLUMNS.get(phase)
        if column is None:
            raise ValueError(f"unsupported execution phase: {phase}")
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO evaluation_execution_telemetry (
                    evaluation_id, execution_number, {column}
                ) VALUES (%s, %s, NOW())
                ON CONFLICT (evaluation_id, execution_number) DO UPDATE SET
                    {column} = COALESCE(
                        evaluation_execution_telemetry.{column},
                        EXCLUDED.{column}
                    ),
                    updated_at = NOW()
                """,
                (evaluation_id, execution_number),
            )

    def record_summary(
        self,
        evaluation_id: str,
        *,
        execution_number: int,
        summary: Mapping[str, Any],
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_execution_telemetry (
                    evaluation_id, execution_number,
                    input_tokens, output_tokens, cached_tokens, cache_creation_tokens,
                    usage_source, turn_count, tool_call_count, cost_usd, cost_source,
                    raw_artifact_refs
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (evaluation_id, execution_number) DO UPDATE SET
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    cached_tokens = EXCLUDED.cached_tokens,
                    cache_creation_tokens = EXCLUDED.cache_creation_tokens,
                    usage_source = EXCLUDED.usage_source,
                    turn_count = EXCLUDED.turn_count,
                    tool_call_count = EXCLUDED.tool_call_count,
                    cost_usd = EXCLUDED.cost_usd,
                    cost_source = EXCLUDED.cost_source,
                    raw_artifact_refs = EXCLUDED.raw_artifact_refs,
                    updated_at = NOW()
                """,
                (
                    evaluation_id,
                    execution_number,
                    summary.get("input_tokens"),
                    summary.get("output_tokens"),
                    summary.get("cached_tokens"),
                    summary.get("cache_creation_tokens"),
                    summary.get("usage_source") or "unknown",
                    summary.get("turn_count"),
                    summary.get("tool_call_count"),
                    summary.get("cost_usd"),
                    summary.get("cost_source") or "unknown",
                    json.dumps(summary.get("raw_artifact_refs") or []),
                ),
            )

    def record_intake(
        self,
        evaluation_id: str,
        *,
        execution_number: int,
        experiment_ref: str | None,
        run_refs: list[str],
        status: str,
        expected_records: int | None,
        uploaded_records: int | None,
        error: str | None,
    ) -> None:
        safe_error = redact_secret_text(error)[:2000] if error else None
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_execution_telemetry (
                    evaluation_id, execution_number, intake_experiment_ref,
                    intake_run_refs, intake_status, intake_expected_records,
                    intake_uploaded_records, intake_error
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT (evaluation_id, execution_number) DO UPDATE SET
                    intake_experiment_ref = EXCLUDED.intake_experiment_ref,
                    intake_run_refs = EXCLUDED.intake_run_refs,
                    intake_status = EXCLUDED.intake_status,
                    intake_expected_records = EXCLUDED.intake_expected_records,
                    intake_uploaded_records = EXCLUDED.intake_uploaded_records,
                    intake_error = EXCLUDED.intake_error,
                    updated_at = NOW()
                """,
                (
                    evaluation_id,
                    execution_number,
                    experiment_ref,
                    json.dumps(run_refs),
                    status,
                    expected_records,
                    uploaded_records,
                    safe_error,
                ),
            )

    def record_artifact_sync(
        self,
        evaluation_id: str,
        *,
        execution_number: int,
        status: str,
        file_count: int | None = None,
        error: str | None = None,
    ) -> None:
        safe_error = redact_secret_text(error)[:2000] if error else None
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_execution_telemetry (
                    evaluation_id, execution_number, artifact_sync_status,
                    artifact_sync_file_count, artifact_sync_error
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (evaluation_id, execution_number) DO UPDATE SET
                    artifact_sync_status = EXCLUDED.artifact_sync_status,
                    artifact_sync_file_count = EXCLUDED.artifact_sync_file_count,
                    artifact_sync_error = EXCLUDED.artifact_sync_error,
                    updated_at = NOW()
                """,
                (evaluation_id, execution_number, status, file_count, safe_error),
            )

    def list_for_evaluation(self, evaluation_id: str) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM evaluation_execution_telemetry
                WHERE evaluation_id = %s
                ORDER BY execution_number ASC
                """,
                (evaluation_id,),
            )
            return cur.fetchall()
