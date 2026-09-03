# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# The repository below defines a ``list`` method, which shadows the builtin for
# annotations in the same class body, so those spell the type ``builtins.list``.
import builtins
from datetime import datetime
from typing import Any

import psycopg

from scaled_evals.api.redaction import redact_secret_text
from scaled_evals.api.repositories.base_repository import (
    created_at_cursor_clause,
    join_where,
)

_ADMIN_FAILURE_CATEGORY_SQL = """
CASE
    WHEN failure_text ~ '(http[^0-9]*)?504|gateway timeout'
        THEN 'inference_http_504'
    WHEN failure_text ~ 'ratelimiterror|rate[ -]?limit|(^|[^0-9])429([^0-9]|$)'
        THEN 'inference_rate_limit'
    WHEN failure_text ~ 'apitimeouterror|provider_timeout'
        OR (failure_text ~ 'inference|provider|model|openai|anthropic|litellm'
            AND failure_text ~ 'timed out|timeout')
        THEN 'inference_timeout'
    WHEN failure_text ~ 'sandboxcreationerror|environmentstarttimeouterror|imagepull|rhacs'
        OR failure_text ~ 'admission'
        OR (failure_text ~ 'sandbox|environment' AND failure_text ~ 'start|create|provision')
        THEN 'sandbox_startup'
    WHEN failure_text ~ 'cleanup failed|cleanup command failed|cleanup left|cleanup unavailable'
        THEN 'runtime_cleanup'
    WHEN failure_text ~ 'poll_timeout|deadline exceeded|timed out waiting|execution timeout'
        OR failure_text ~ 'agenttimeouterror|verifiertimeouterror'
        THEN 'evaluation_timeout'
    WHEN failure_text ~ 'cancellederror|cancelled trial'
        THEN 'trial_cancelled'
    WHEN failure_text ~ 'object_store_unavailable|object store|rustfs|(^|[^a-z])s3([^a-z]|$)'
        THEN 'object_storage'
    WHEN failure_text ~ 'nonzeroagentexitcodeerror|agent exited|agent process'
        THEN 'agent_exit'
    WHEN failure_text ~ 'runner_disappeared|kubernetesjoberror|sandboxexecutionerror'
        OR failure_text ~ 'connectionerror'
        OR failure_category = 'infrastructure'
        THEN 'runtime_infrastructure'
    WHEN failure_text ~ 'task_object_missing|task object|task pack|invalidreference|validationerror'
        OR failure_text ~ 'addtestsdirerror|registry.+not approved|allowed registries'
        OR failure_category = 'task'
        THEN 'task_configuration'
    WHEN failure_text ~ 'evaluation already terminal'
        THEN 'control_plane_state'
    ELSE 'other'
END
"""

_ADMIN_FAILURE_OCCURRED_AT_SQL = """
COALESCE(
    e.finished_at,
    CASE
        WHEN e.result->>'finished_at'
            ~ '[zZ]$|[+-][0-9]{2}:[0-9]{2}$'
            THEN (e.result->>'finished_at')::timestamptz
        WHEN e.result->>'finished_at'
            ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}'
            THEN (e.result->>'finished_at')::timestamp AT TIME ZONE 'UTC'
        ELSE NULL
    END,
    e.updated_at
)
"""


class UserRepository:
    """Persist normalized identities and provide ownership-backed views."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def upsert(
        self,
        owner_id: str,
        *,
        email: str | None,
        username: str | None,
        display_name: str | None,
    ) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, email, username, display_name, last_seen_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    email = COALESCE(EXCLUDED.email, users.email),
                    username = COALESCE(EXCLUDED.username, users.username),
                    display_name = COALESCE(EXCLUDED.display_name, users.display_name),
                    last_seen_at = NOW(),
                    updated_at = NOW()
                RETURNING id, email, username, display_name, created_at, last_seen_at
                """,
                (owner_id, email, username, display_name),
            )
            return cur.fetchone()

    def list(self, *, q: str, limit: int, cursor: str | None) -> builtins.list[dict]:
        filters = [
            "(%s = '' OR id ILIKE %s OR COALESCE(email, '') ILIKE %s "
            "OR COALESCE(username, '') ILIKE %s OR COALESCE(display_name, '') ILIKE %s)"
        ]
        pattern = f"%{q}%"
        params: list[Any] = [q, pattern, pattern, pattern, pattern]
        cursor_filter, cursor_params = created_at_cursor_clause(cursor, "desc")
        if cursor_filter:
            filters.append(cursor_filter)
            params.extend(cursor_params)
        params.append(limit + 1)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, email, username, display_name, created_at, last_seen_at
                FROM users
                WHERE {join_where(filters)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()

    def summary(self, owner_id: str) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('blocked', 'provisioning', 'running'))
                        AS active,
                    COUNT(*) FILTER (WHERE status = 'queued') AS queued,
                    COUNT(*) FILTER (
                        WHERE status = 'failed' AND updated_at >= NOW() - INTERVAL '24 hours'
                    ) AS failed_24h,
                    COUNT(*) FILTER (
                        WHERE status = 'succeeded' AND updated_at >= NOW() - INTERVAL '24 hours'
                    ) AS succeeded_24h
                FROM evaluations
                WHERE owner_id = %s AND deleted_at IS NULL
                """,
                (owner_id,),
            )
            evaluations = dict(cur.fetchone())
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE r.status = 'ready') AS ready,
                    COUNT(*) FILTER (WHERE r.status IN ('pending', 'uploading', 'building'))
                        AS building
                FROM tasks t
                LEFT JOIN LATERAL (
                    SELECT status FROM task_revisions
                    WHERE task_id = t.id ORDER BY revision DESC LIMIT 1
                ) r ON TRUE
                WHERE t.owner_id = %s AND t.deleted_at IS NULL
                """,
                (owner_id,),
            )
            tasks = dict(cur.fetchone())
        return {
            "evaluations": {key: int(value or 0) for key, value in evaluations.items()},
            "tasks": {key: int(value or 0) for key, value in tasks.items()},
        }

    def capacity(self) -> dict[str, int]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('blocked', 'provisioning', 'running'))
                        AS active_runs,
                    COUNT(*) FILTER (WHERE status = 'queued') AS queued_runs,
                    COALESCE(SUM(parallelism) FILTER (
                        WHERE status IN ('provisioning', 'running')
                    ), 0) AS active_slots
                FROM evaluations WHERE deleted_at IS NULL
                """
            )
            row = cur.fetchone()
        return {key: int(value or 0) for key, value in row.items()}

    def usage_by_actor(self, *, limit: int) -> dict:
        runtime_expr = "EXTRACT(EPOCH FROM (COALESCE(e.finished_at, e.updated_at) - e.created_at))"
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_runs,
                    (SELECT COUNT(*) FROM tasks) AS total_tasks,
                    (SELECT COUNT(DISTINCT task_id) FROM evaluations) AS total_tasks_run,
                    (SELECT COUNT(*) FROM evaluations) AS total_evaluation_jobs,
                    (SELECT COALESCE(SUM(current_execution), 0) FROM evaluations)
                        AS total_executions,
                    (SELECT COALESCE(SUM(n_trials), 0) FROM evaluations) AS total_trials,
                    (SELECT COUNT(*) FROM benchmark_runs) AS total_benchmark_runs,
                    COUNT(*) FILTER (WHERE status = 'queued') AS queued_runs,
                    COUNT(*) FILTER (WHERE status IN ('blocked', 'provisioning', 'running'))
                        AS active_runs,
                    COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded_runs,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed_runs,
                    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_runs,
                    COALESCE(SUM(parallelism), 0) AS total_parallelism,
                    AVG({runtime_expr}) FILTER (WHERE finished_at IS NOT NULL)
                        AS avg_runtime_seconds,
                    MAX({runtime_expr}) FILTER (WHERE finished_at IS NOT NULL)
                        AS max_runtime_seconds
                FROM evaluations e
                WHERE e.deleted_at IS NULL
                """
            )
            summary = dict(cur.fetchone())
            cur.execute(
                f"""
                SELECT
                    e.owner_id,
                    u.email,
                    u.username,
                    u.display_name,
                    COUNT(*) AS total_runs,
                    COUNT(*) FILTER (WHERE e.status = 'queued') AS queued_runs,
                    COUNT(*) FILTER (WHERE e.status IN ('blocked', 'provisioning', 'running'))
                        AS active_runs,
                    COUNT(*) FILTER (WHERE e.status = 'succeeded') AS succeeded_runs,
                    COUNT(*) FILTER (WHERE e.status = 'failed') AS failed_runs,
                    COUNT(*) FILTER (WHERE e.status = 'cancelled') AS cancelled_runs,
                    COALESCE(SUM(e.parallelism), 0) AS total_parallelism,
                    AVG({runtime_expr}) FILTER (WHERE e.finished_at IS NOT NULL)
                        AS avg_runtime_seconds,
                    MAX({runtime_expr}) FILTER (WHERE e.finished_at IS NOT NULL)
                        AS max_runtime_seconds,
                    MAX(e.created_at) AS last_run_at
                FROM evaluations e
                LEFT JOIN users u ON u.id = e.owner_id
                WHERE e.deleted_at IS NULL
                GROUP BY e.owner_id, u.email, u.username, u.display_name
                ORDER BY total_runs DESC, last_run_at DESC NULLS LAST, e.owner_id DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
            actors = cur.fetchall()

        count_keys = {
            "total_runs",
            "total_tasks",
            "total_tasks_run",
            "total_evaluation_jobs",
            "total_executions",
            "total_trials",
            "total_benchmark_runs",
            "queued_runs",
            "active_runs",
            "succeeded_runs",
            "failed_runs",
            "cancelled_runs",
            "total_parallelism",
        }
        normalized_summary = {}
        for key, value in summary.items():
            normalized_summary[key] = (
                int(value or 0) if key in count_keys else (float(value) if value is not None else None)
            )
        normalized_actors = []
        for row in actors:
            normalized_actors.append(
                {
                    key: int(value or 0)
                    if key in count_keys
                    else (float(value) if key.endswith("_seconds") and value is not None else value)
                    for key, value in row.items()
                }
            )
        return {**normalized_summary, "actors": normalized_actors}

    def compute_summary(
        self,
        *,
        window_days: int,
        window_start: datetime,
        window_end: datetime,
    ) -> dict:
        """Aggregate optional runtime samples for evaluations in a time window."""

        usage_cte = """
            selected AS (
                SELECT id, runtime, COALESCE(finished_at, updated_at) AS occurred_at
                FROM evaluations
                WHERE deleted_at IS NULL
                  AND COALESCE(finished_at, updated_at) >= %s
                  AND COALESCE(finished_at, updated_at) < %s
            ), usage_by_evaluation AS (
                SELECT
                    selected.id,
                    selected.runtime,
                    selected.occurred_at,
                    COALESCE(SUM(usage.sample_count), 0) AS samples,
                    COALESCE(SUM(usage.cpu_sample_count), 0) AS cpu_samples,
                    COALESCE(SUM(usage.cpu_usage_cores_sum), 0) AS cpu_sum,
                    MAX(usage.cpu_usage_cores_max)
                        FILTER (WHERE usage.cpu_sample_count > 0) AS peak_cpu_cores,
                    MAX(usage.cpu_request_cores) AS cpu_request_cores,
                    MAX(usage.cpu_limit_cores) AS cpu_limit_cores,
                    COALESCE(SUM(usage.memory_sample_count), 0) AS memory_samples,
                    COALESCE(SUM(usage.memory_usage_bytes_sum), 0) AS memory_sum,
                    MAX(usage.memory_usage_bytes_max)
                        FILTER (WHERE usage.memory_sample_count > 0) AS peak_memory_bytes,
                    MAX(usage.memory_request_bytes) AS memory_request_bytes,
                    MAX(usage.memory_limit_bytes) AS memory_limit_bytes,
                    MAX(usage.gpu_request) AS gpu_request,
                    COALESCE(SUM(usage.gpu_sample_count), 0) AS gpu_samples
                FROM selected
                LEFT JOIN evaluation_resource_usage usage
                  ON usage.evaluation_id = selected.id
                GROUP BY selected.id, selected.runtime, selected.occurred_at
            )
        """
        aggregate_columns = """
            COUNT(*) AS evaluations,
            COUNT(*) FILTER (
                WHERE cpu_samples > 0 OR memory_samples > 0 OR gpu_samples > 0
            ) AS sampled_evaluations,
            COALESCE(SUM(GREATEST(cpu_samples, memory_samples, gpu_samples)), 0) AS samples,
            SUM(cpu_sum) / NULLIF(SUM(cpu_samples), 0) AS avg_cpu_cores,
            MAX(peak_cpu_cores) AS peak_cpu_cores,
            AVG(cpu_request_cores) FILTER (WHERE cpu_request_cores IS NOT NULL)
                AS avg_cpu_request_cores,
            AVG(cpu_limit_cores) FILTER (WHERE cpu_limit_cores IS NOT NULL)
                AS avg_cpu_limit_cores,
            100 * SUM(cpu_sum) FILTER (WHERE cpu_request_cores > 0)
                / NULLIF(SUM(cpu_samples * cpu_request_cores)
                    FILTER (WHERE cpu_request_cores > 0), 0)
                AS avg_cpu_request_utilization_percent,
            SUM(memory_sum) / NULLIF(SUM(memory_samples), 0) AS avg_memory_bytes,
            MAX(peak_memory_bytes) AS peak_memory_bytes,
            AVG(memory_request_bytes) FILTER (WHERE memory_request_bytes IS NOT NULL)
                AS avg_memory_request_bytes,
            AVG(memory_limit_bytes) FILTER (WHERE memory_limit_bytes IS NOT NULL)
                AS avg_memory_limit_bytes,
            100 * SUM(memory_sum) FILTER (WHERE memory_request_bytes > 0)
                / NULLIF(SUM(memory_samples * memory_request_bytes)
                    FILTER (WHERE memory_request_bytes > 0), 0)
                AS avg_memory_request_utilization_percent,
            SUM(gpu_request) AS requested_gpus,
            COALESCE(SUM(gpu_samples), 0) > 0 AS gpu_utilization_available
        """
        with self.conn.cursor() as cur:
            cur.execute(
                f"WITH {usage_cte} SELECT {aggregate_columns} FROM usage_by_evaluation",
                (window_start, window_end),
            )
            summary = dict(cur.fetchone())
            cur.execute(
                f"""
                WITH {usage_cte}
                SELECT runtime, {aggregate_columns}
                FROM usage_by_evaluation
                GROUP BY runtime
                ORDER BY sampled_evaluations DESC, evaluations DESC, runtime
                """,
                (window_start, window_end),
            )
            runtime_rows = cur.fetchall()
            cur.execute(
                f"""
                WITH {usage_cte}, days AS (
                    SELECT generate_series(
                        %s::timestamptz::date, %s::timestamptz::date, INTERVAL '1 day'
                    )::date AS day
                ), daily AS (
                    SELECT occurred_at::date AS day, {aggregate_columns}
                    FROM usage_by_evaluation
                    GROUP BY occurred_at::date
                )
                SELECT
                    days.day,
                    COALESCE(daily.evaluations, 0) AS evaluations,
                    COALESCE(daily.sampled_evaluations, 0) AS sampled_evaluations,
                    COALESCE(daily.samples, 0) AS samples,
                    daily.avg_cpu_cores,
                    daily.peak_cpu_cores,
                    daily.avg_cpu_request_cores,
                    daily.avg_memory_bytes,
                    daily.peak_memory_bytes,
                    daily.avg_memory_request_bytes,
                    daily.requested_gpus
                FROM days
                LEFT JOIN daily ON daily.day = days.day
                ORDER BY days.day
                """,
                (window_start, window_end, window_start, window_end),
            )
            timeline_rows = cur.fetchall()

        integer_keys = {"evaluations", "sampled_evaluations", "samples", "peak_memory_bytes"}
        numeric_keys = {
            "avg_cpu_cores",
            "peak_cpu_cores",
            "avg_cpu_request_cores",
            "avg_cpu_limit_cores",
            "avg_cpu_request_utilization_percent",
            "avg_memory_bytes",
            "avg_memory_request_bytes",
            "avg_memory_limit_bytes",
            "avg_memory_request_utilization_percent",
            "requested_gpus",
        }

        def normalize(row: dict) -> dict:
            return {
                key: (
                    int(value)
                    if key in integer_keys and value is not None
                    else float(value)
                    if key in numeric_keys and value is not None
                    else value
                )
                for key, value in row.items()
            }

        normalized_summary = normalize(summary)
        normalized_summary.pop("gpu_utilization_available", None)
        return {
            "window_days": window_days,
            "window_start": window_start,
            "window_end": window_end,
            "runtime": "all",
            **normalized_summary,
            "runtimes": [
                {key: value for key, value in normalize(dict(row)).items() if key != "gpu_utilization_available"}
                for row in runtime_rows
            ],
            "timeline": [
                {"date": row["day"], **normalize({k: v for k, v in row.items() if k != "day"})} for row in timeline_rows
            ],
            "gpu_utilization_available": bool(summary.get("gpu_utilization_available")),
        }

    def failure_summary(
        self,
        *,
        window_days: int,
        window_start: datetime,
        window_end: datetime,
        examples_per_category: int,
    ) -> dict:
        """Categorize recent terminal failures and retain representative examples."""

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                WITH failures AS (
                    SELECT
                        e.id AS evaluation_id,
                        e.name AS evaluation_name,
                        e.task_id,
                        e.owner_id,
                        COALESCE(u.display_name, u.email, u.username, e.owner_id)
                            AS owner_label,
                        e.runtime,
                        e.last_failure_code AS failure_code,
                        e.last_failure_category AS failure_category,
                        e.status_detail AS detail,
                        {_ADMIN_FAILURE_OCCURRED_AT_SQL} AS occurred_at,
                        LOWER(CONCAT_WS(
                            ' ', e.last_failure_code, e.last_failure_category,
                            e.status_detail, e.exception_counts::text
                        )) AS failure_text
                    FROM evaluations e
                    LEFT JOIN users u ON u.id = e.owner_id
                    WHERE e.deleted_at IS NULL
                      AND e.status = 'failed'
                      AND {_ADMIN_FAILURE_OCCURRED_AT_SQL}
                          >= %s
                      AND {_ADMIN_FAILURE_OCCURRED_AT_SQL} < %s
                ), categorized AS (
                    SELECT failures.*, {_ADMIN_FAILURE_CATEGORY_SQL} AS category
                    FROM failures
                ), ranked AS (
                    SELECT categorized.*,
                        COUNT(*) OVER (PARTITION BY category) AS category_count,
                        ROW_NUMBER() OVER (
                            PARTITION BY category ORDER BY occurred_at DESC, evaluation_id DESC
                        ) AS category_rank
                    FROM categorized
                )
                SELECT category, category_count,
                    evaluation_id, evaluation_name, task_id, owner_id, owner_label, runtime,
                    failure_code, detail, occurred_at
                FROM ranked
                WHERE category_rank <= %s
                ORDER BY category_count DESC, category, occurred_at DESC, evaluation_id DESC
                """,
                (window_start, window_end, examples_per_category),
            )
            rows = cur.fetchall()
            cur.execute(
                f"""
                WITH days AS (
                    SELECT generate_series(
                        %s::timestamptz::date, %s::timestamptz::date, INTERVAL '1 day'
                    )::date AS day
                ), failures AS (
                    SELECT
                        {_ADMIN_FAILURE_OCCURRED_AT_SQL} AS occurred_at,
                        e.last_failure_code AS failure_code,
                        e.last_failure_category AS failure_category,
                        LOWER(CONCAT_WS(
                            ' ', e.last_failure_code, e.last_failure_category,
                            e.status_detail, e.exception_counts::text
                        )) AS failure_text
                    FROM evaluations e
                    WHERE e.deleted_at IS NULL
                      AND e.status = 'failed'
                      AND {_ADMIN_FAILURE_OCCURRED_AT_SQL}
                          >= %s
                      AND {_ADMIN_FAILURE_OCCURRED_AT_SQL} < %s
                ), categorized AS (
                    SELECT occurred_at::date AS day,
                        {_ADMIN_FAILURE_CATEGORY_SQL} AS category,
                        COALESCE(NULLIF(failure_code, ''), 'unknown') AS failure_code
                    FROM failures
                ), daily_codes AS (
                    SELECT day, category, failure_code, COUNT(*) AS count
                    FROM categorized
                    GROUP BY day, category, failure_code
                ), daily AS (
                    SELECT day, category, SUM(count) AS count,
                        JSONB_OBJECT_AGG(failure_code, count) AS codes
                    FROM daily_codes
                    GROUP BY day, category
                )
                SELECT days.day,
                    COALESCE(SUM(daily.count), 0) AS total,
                    COALESCE(
                        JSONB_OBJECT_AGG(daily.category, daily.count)
                            FILTER (WHERE daily.category IS NOT NULL),
                        '{{}}'::jsonb
                    ) AS counts,
                    COALESCE(
                        JSONB_OBJECT_AGG(daily.category, daily.codes)
                            FILTER (WHERE daily.category IS NOT NULL),
                        '{{}}'::jsonb
                    ) AS codes
                FROM days
                LEFT JOIN daily ON daily.day = days.day
                GROUP BY days.day
                ORDER BY days.day
                """,
                (window_start, window_end, window_start, window_end),
            )
            timeline_rows = cur.fetchall()

        categories: dict[str, dict] = {}
        for row in rows:
            category = str(row["category"])
            entry = categories.setdefault(
                category,
                {"key": category, "count": int(row["category_count"]), "examples": []},
            )
            entry["examples"].append(
                {
                    key: (redact_secret_text(str(row[key])) if key == "detail" and row[key] is not None else row[key])
                    for key in (
                        "evaluation_id",
                        "evaluation_name",
                        "task_id",
                        "owner_id",
                        "owner_label",
                        "runtime",
                        "failure_code",
                        "detail",
                        "occurred_at",
                    )
                }
            )
        category_rows = list(categories.values())
        return {
            "window_days": window_days,
            "window_start": window_start,
            "window_end": window_end,
            "total_failures": sum(row["count"] for row in category_rows),
            "categories": category_rows,
            "timeline": [
                {
                    "date": row["day"],
                    "total": int(row["total"]),
                    "counts": {key: int(value) for key, value in row["counts"].items()},
                    "codes": {
                        category: {code: int(count) for code, count in codes.items()}
                        for category, codes in row["codes"].items()
                    },
                }
                for row in timeline_rows
            ],
        }

    def quota_usage(self, owner_id: str) -> dict[str, int]:
        """Return real owner-backed counts for ``GET /users/me``."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status IN ('queued', 'provisioning', 'running')
                    ) AS evaluations_active,
                    COALESCE(SUM(parallelism) FILTER (
                        WHERE status IN ('provisioning', 'running')
                    ), 0) AS sandbox_slots_active
                FROM evaluations
                WHERE owner_id = %s AND deleted_at IS NULL
                """,
                (owner_id,),
            )
            usage = dict(cur.fetchone())
            cur.execute(
                """
                SELECT COUNT(*) AS tasks_owned
                FROM tasks
                WHERE owner_id = %s AND deleted_at IS NULL
                """,
                (owner_id,),
            )
            usage.update(cur.fetchone())
        return {key: int(value or 0) for key, value in usage.items()}

    def recent_activity(self, owner_id: str, *, limit: int) -> builtins.list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, kind, name, status, created_at FROM (
                    SELECT id, 'evaluation' AS kind, name, status::text AS status, created_at
                    FROM evaluations WHERE owner_id = %s AND deleted_at IS NULL
                    UNION ALL
                    SELECT t.id, 'task' AS kind, t.name, r.status::text, t.created_at
                    FROM tasks t
                    LEFT JOIN LATERAL (
                        SELECT status FROM task_revisions
                        WHERE task_id = t.id ORDER BY revision DESC LIMIT 1
                    ) r ON TRUE
                    WHERE t.owner_id = %s AND t.deleted_at IS NULL
                ) activity
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (owner_id, owner_id, limit),
            )
            return cur.fetchall()
