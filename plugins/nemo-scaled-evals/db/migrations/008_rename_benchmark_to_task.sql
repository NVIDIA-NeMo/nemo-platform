-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Rename the `benchmark` primitive to `task` (MR !102) on databases created
-- before the rename. Fresh databases are already created as `tasks` by
-- db/schema/01_tasks.sql, so this migration is a clean no-op on them.
-- Idempotent: safe to re-run on every postgres start.
--
-- IMPORTANT: the step-2 benchmark *collection* feature (db/schema/05_benchmarks
-- + migration 009) legitimately reintroduces `benchmark_*` object names
-- (benchmark_visibility, benchmarks, benchmarks_pkey, ...). On a fresh DB those
-- coexist with the renamed `task_*` objects, so a blind "rename benchmark_* ->
-- task_*" would collide. We therefore gate the entire migration on a single
-- one-shot check: only a genuine PRE-rename database (one that has no `tasks`
-- table yet) is rewritten. Once `tasks` exists (fresh init, or this migration
-- already ran), the whole block returns early.
--
-- Renames tables, columns, enum types, indexes, and PK/FK constraints so a
-- migrated database is structurally identical to a freshly initialized one.
-- The JSONB `tasks` column on (benchmark_)revisions is intentionally unchanged.

DO $$
BEGIN
    -- Pre-rename databases have the old `benchmarks` primitive but no `tasks`
    -- table. A fresh or already-migrated DB has `tasks` -> nothing to do.
    IF to_regclass('tasks') IS NOT NULL THEN
        RETURN;
    END IF;

    -- 1. Enum types (columns using them follow automatically).
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'benchmark_visibility') THEN
        ALTER TYPE benchmark_visibility RENAME TO task_visibility;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'benchmark_revision_status') THEN
        ALTER TYPE benchmark_revision_status RENAME TO task_revision_status;
    END IF;

    -- 2. Tables (also renames each table's implicit rowtype + array type).
    IF to_regclass('benchmarks') IS NOT NULL THEN
        ALTER TABLE benchmarks RENAME TO tasks;
    END IF;
    IF to_regclass('benchmark_revisions') IS NOT NULL THEN
        ALTER TABLE benchmark_revisions RENAME TO task_revisions;
    END IF;

    -- 3. Columns.
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'task_revisions'
                 AND column_name = 'benchmark_id') THEN
        ALTER TABLE task_revisions RENAME COLUMN benchmark_id TO task_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'task_revisions'
                 AND column_name = 'benchmark_yaml') THEN
        ALTER TABLE task_revisions RENAME COLUMN benchmark_yaml TO task_yaml;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'evaluations'
                 AND column_name = 'benchmark_id') THEN
        ALTER TABLE evaluations RENAME COLUMN benchmark_id TO task_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'evaluations'
                 AND column_name = 'benchmark_revision') THEN
        ALTER TABLE evaluations RENAME COLUMN benchmark_revision TO task_revision;
    END IF;

    -- 4. PK / FK constraint names (so they match a fresh init; future migrations
    --    may reference these names).
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'benchmarks_pkey') THEN
        ALTER TABLE tasks RENAME CONSTRAINT benchmarks_pkey TO tasks_pkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'benchmark_revisions_pkey') THEN
        ALTER TABLE task_revisions RENAME CONSTRAINT benchmark_revisions_pkey TO task_revisions_pkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'benchmark_revisions_benchmark_id_fkey') THEN
        ALTER TABLE task_revisions
            RENAME CONSTRAINT benchmark_revisions_benchmark_id_fkey TO task_revisions_task_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'evaluations_benchmark_id_benchmark_revision_fkey') THEN
        ALTER TABLE evaluations
            RENAME CONSTRAINT evaluations_benchmark_id_benchmark_revision_fkey
            TO evaluations_task_id_task_revision_fkey;
    END IF;

    -- 5. Indexes. Renaming a PK/unique constraint (step 4) renames its backing
    --    index too, so those guards simply skip if already done; the explicit
    --    secondary indexes are renamed here.
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'benchmarks_slug_live_uq') THEN
        ALTER INDEX benchmarks_slug_live_uq RENAME TO tasks_slug_live_uq;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'benchmarks_created_at_idx') THEN
        ALTER INDEX benchmarks_created_at_idx RENAME TO tasks_created_at_idx;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'benchmark_revisions_active_idx') THEN
        ALTER INDEX benchmark_revisions_active_idx RENAME TO task_revisions_active_idx;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'evaluations_benchmark_idx') THEN
        ALTER INDEX evaluations_benchmark_idx RENAME TO evaluations_task_idx;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'benchmarks_pkey') THEN
        ALTER INDEX benchmarks_pkey RENAME TO tasks_pkey;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'benchmark_revisions_pkey') THEN
        ALTER INDEX benchmark_revisions_pkey RENAME TO task_revisions_pkey;
    END IF;
END $$;
