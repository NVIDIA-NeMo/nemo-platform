-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Benchmark runs: running a benchmark is the union of task executions. A
-- benchmark_run is the grouping/aggregate; its member executions are ordinary
-- `evaluations` rows carrying benchmark_run_id. Mirrors db/schema/06_benchmark_runs.sql
-- (and the benchmark_run_id column declared in db/schema/04_evaluations.sql).
--
-- Idempotent and a no-op on a freshly initialized database (db/schema already
-- created these objects). Sorts after 009_benchmarks.sql. On an existing
-- pre-benchmark-run database (at 009), evaluations.task_id/task_revision are
-- already NOT NULL, so this only adds the benchmark_runs table + the
-- benchmark_run_id link.

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    framework             TEXT NOT NULL DEFAULT 'harbor',
    benchmark_id          TEXT NOT NULL,
    benchmark_revision    INTEGER NOT NULL,
    framework_profile_id  TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    harbor_profile_id     TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    switchyard_profile_id TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    intake_profile_id     TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    credentials           JSONB NOT NULL DEFAULT '{}'::jsonb,
    runtime               TEXT NOT NULL DEFAULT 'sandbox_k8s',
    parallelism           INTEGER NOT NULL DEFAULT 1,
    visibility            evaluation_visibility NOT NULL DEFAULT 'private',
    -- status/reward/result are derived on read from member evaluations; only an
    -- explicit cancel is stored (derive_run_view in benchmark_run_repository).
    cancelled_at          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at            TIMESTAMPTZ,
    FOREIGN KEY (benchmark_id, benchmark_revision)
        REFERENCES benchmark_revisions (benchmark_id, revision)
        ON DELETE RESTRICT
);
-- Existing databases that created benchmark_runs with the earlier (materialized)
-- columns: add cancelled_at. The old status/reward/result/... columns are left
-- in place but unused (nothing reads or writes them).
ALTER TABLE benchmark_runs ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS benchmark_runs_benchmark_idx
    ON benchmark_runs (benchmark_id);
CREATE INDEX IF NOT EXISTS benchmark_runs_created_at_idx
    ON benchmark_runs (created_at DESC);

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS benchmark_run_id TEXT;

DO $$ BEGIN
    ALTER TABLE evaluations
        ADD CONSTRAINT evaluations_benchmark_run_fkey
        FOREIGN KEY (benchmark_run_id)
        REFERENCES benchmark_runs (id) ON DELETE CASCADE;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS evaluations_benchmark_run_idx
    ON evaluations (benchmark_run_id)
    WHERE benchmark_run_id IS NOT NULL;
