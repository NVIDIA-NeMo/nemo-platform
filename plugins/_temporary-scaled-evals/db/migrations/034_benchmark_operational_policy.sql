-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Metadata-only benchmark variants: lineage + allowlisted operational policy on
-- an immutable revision. Idempotent: safe to re-run on existing databases.

ALTER TABLE benchmark_revisions
    ADD COLUMN IF NOT EXISTS derived_from_benchmark_id TEXT,
    ADD COLUMN IF NOT EXISTS derived_from_revision INTEGER,
    ADD COLUMN IF NOT EXISTS operational_policy JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'benchmark_revisions_derived_pair_ck'
          AND conrelid = 'benchmark_revisions'::regclass
    ) THEN
        ALTER TABLE benchmark_revisions
            ADD CONSTRAINT benchmark_revisions_derived_pair_ck CHECK (
                (derived_from_benchmark_id IS NULL AND derived_from_revision IS NULL)
                OR (derived_from_benchmark_id IS NOT NULL AND derived_from_revision IS NOT NULL)
            );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'benchmark_revisions_derived_from_fk'
          AND conrelid = 'benchmark_revisions'::regclass
    ) THEN
        ALTER TABLE benchmark_revisions
            ADD CONSTRAINT benchmark_revisions_derived_from_fk
            FOREIGN KEY (derived_from_benchmark_id, derived_from_revision)
            REFERENCES benchmark_revisions (benchmark_id, revision)
            ON DELETE RESTRICT;
    END IF;
END $$;
