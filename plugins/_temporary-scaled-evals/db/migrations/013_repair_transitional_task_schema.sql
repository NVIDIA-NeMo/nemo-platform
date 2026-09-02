-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Repair databases caught between the benchmark->task rename (008) and the
-- benchmark-collection addition (009). In that narrow state `tasks` already
-- existed, so 008 returned early while evaluations still referenced the old
-- buildable `benchmarks` table. Clean/fresh databases are a no-op.
DO $$
DECLARE
    needs_repair BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'evaluations'
          AND column_name = 'benchmark_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'benchmark_revisions'
          AND column_name = 'status'
    ) INTO needs_repair;

    IF NOT needs_repair THEN
        RETURN;
    END IF;

    IF EXISTS (SELECT 1 FROM benchmark_runs LIMIT 1)
       OR EXISTS (SELECT 1 FROM benchmark_revision_tasks LIMIT 1) THEN
        RAISE EXCEPTION
            'cannot automatically repair transitional task schema with benchmark runs/memberships';
    END IF;

    INSERT INTO tasks (
        id, owner_id, name, slug, description, visibility, current_revision,
        created_at, updated_at, deleted_at
    )
    SELECT
        b.id, b.owner_id, b.name,
        CASE WHEN EXISTS (
            SELECT 1 FROM tasks t WHERE t.slug = b.slug AND t.deleted_at IS NULL
        ) THEN LEFT(b.slug, 42) || '-legacy-' || LEFT(md5(b.id), 12)
        ELSE b.slug END,
        b.description, b.visibility::text::task_visibility, b.current_revision,
        b.created_at, b.updated_at, b.deleted_at
    FROM benchmarks b
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO task_revisions (
        task_id, revision, status, tarball_object_key, tarball_size_bytes,
        tarball_sha256, image_ref, image_digest, task_yaml, tasks,
        build_started_at, build_completed_at, build_error, created_at
    )
    SELECT
        r.benchmark_id, r.revision, r.status::text::task_revision_status,
        r.tarball_object_key, r.tarball_size_bytes, r.tarball_sha256,
        r.image_ref, r.image_digest, r.benchmark_yaml, r.tasks,
        r.build_started_at, r.build_completed_at, r.build_error, r.created_at
    FROM benchmark_revisions r
    ON CONFLICT (task_id, revision) DO NOTHING;

    ALTER TABLE evaluations
        DROP CONSTRAINT IF EXISTS evaluations_benchmark_id_benchmark_revision_fkey;
    ALTER TABLE evaluations RENAME COLUMN benchmark_id TO task_id;
    ALTER TABLE evaluations RENAME COLUMN benchmark_revision TO task_revision;
    ALTER TABLE evaluations
        ADD CONSTRAINT evaluations_task_id_task_revision_fkey
        FOREIGN KEY (task_id, task_revision)
        REFERENCES task_revisions(task_id, revision) ON DELETE RESTRICT;

    DROP TABLE benchmark_revision_tasks;
    DROP TABLE benchmark_revisions CASCADE;
    DROP TABLE benchmarks CASCADE;

    CREATE TABLE benchmarks (
        id TEXT PRIMARY KEY,
        owner_id TEXT REFERENCES users(id),
        name TEXT NOT NULL,
        slug TEXT NOT NULL,
        description TEXT,
        visibility benchmark_visibility NOT NULL DEFAULT 'private',
        current_revision INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deleted_at TIMESTAMPTZ
    );
    CREATE UNIQUE INDEX benchmarks_slug_live_uq
        ON benchmarks (slug) WHERE deleted_at IS NULL;
    CREATE INDEX benchmarks_created_at_idx ON benchmarks (created_at DESC);
    CREATE INDEX benchmarks_owner_created_idx
        ON benchmarks (owner_id, created_at DESC) WHERE deleted_at IS NULL;

    CREATE TABLE benchmark_revisions (
        benchmark_id TEXT NOT NULL REFERENCES benchmarks(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL,
        description TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (benchmark_id, revision)
    );
    CREATE TABLE benchmark_revision_tasks (
        benchmark_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        task_revision INTEGER,
        position INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (benchmark_id, revision, task_id),
        FOREIGN KEY (benchmark_id, revision)
            REFERENCES benchmark_revisions(benchmark_id, revision) ON DELETE CASCADE,
        FOREIGN KEY (task_id, task_revision)
            REFERENCES task_revisions(task_id, revision) ON DELETE RESTRICT
    );
    CREATE INDEX benchmark_revision_tasks_task_idx
        ON benchmark_revision_tasks (task_id);

    ALTER TABLE benchmark_runs
        ADD CONSTRAINT benchmark_runs_benchmark_id_benchmark_revision_fkey
        FOREIGN KEY (benchmark_id, benchmark_revision)
        REFERENCES benchmark_revisions(benchmark_id, revision) ON DELETE RESTRICT;
END $$;
