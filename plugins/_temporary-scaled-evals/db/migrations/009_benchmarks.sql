-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Benchmarks: a named, revisioned COLLECTION of tasks (mirrors the fresh-install
-- DDL in db/schema/05_benchmarks.sql). This migration creates the benchmark
-- tables/enum/indexes on databases that predate the benchmark feature.
--
-- Idempotent and a no-op on a freshly initialized database (db/schema already
-- created these objects): the enum create is guarded against duplicate_object
-- and every table/index uses IF NOT EXISTS. Sorts after
-- 008_rename_benchmark_to_task.sql, so the tasks/task_revisions tables it
-- references already carry their renamed names.

DO $$ BEGIN
    CREATE TYPE benchmark_visibility AS ENUM ('private', 'team', 'org', 'public');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS benchmarks (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    slug             TEXT NOT NULL,
    description      TEXT,
    visibility       benchmark_visibility NOT NULL DEFAULT 'private',
    current_revision INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at       TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS benchmarks_slug_live_uq
    ON benchmarks (slug)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS benchmarks_created_at_idx
    ON benchmarks (created_at DESC);

CREATE TABLE IF NOT EXISTS benchmark_revisions (
    benchmark_id TEXT NOT NULL
        REFERENCES benchmarks(id) ON DELETE RESTRICT,
    revision     INTEGER NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (benchmark_id, revision)
);

CREATE TABLE IF NOT EXISTS benchmark_revision_tasks (
    benchmark_id  TEXT NOT NULL,
    revision      INTEGER NOT NULL,
    task_id       TEXT NOT NULL
        REFERENCES tasks(id) ON DELETE RESTRICT,
    task_revision INTEGER,
    position      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (benchmark_id, revision, task_id),
    FOREIGN KEY (benchmark_id, revision)
        REFERENCES benchmark_revisions (benchmark_id, revision) ON DELETE CASCADE,
    FOREIGN KEY (task_id, task_revision)
        REFERENCES task_revisions (task_id, revision) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS benchmark_revision_tasks_task_idx
    ON benchmark_revision_tasks (task_id);
