-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

DO $$ BEGIN
    CREATE TYPE benchmark_qualification AS ENUM ('registered', 'qualified', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE benchmarks
    ADD COLUMN IF NOT EXISTS qualification_status benchmark_qualification NOT NULL DEFAULT 'registered',
    ADD COLUMN IF NOT EXISTS qualification_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS qualified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS qualified_by TEXT;

UPDATE benchmarks
SET qualification_status = 'qualified',
    qualification_evidence = CASE
        WHEN qualification_evidence = '{}'::jsonb THEN '{"source":"legacy-public-visibility"}'::jsonb
        ELSE qualification_evidence
    END,
    qualified_at = COALESCE(qualified_at, updated_at)
WHERE visibility = 'public' AND qualification_status <> 'qualified';

ALTER TABLE benchmarks
    DROP CONSTRAINT IF EXISTS benchmarks_public_requires_qualification_ck;

ALTER TABLE benchmarks
    ADD CONSTRAINT benchmarks_public_requires_qualification_ck
    CHECK (visibility <> 'public' OR qualification_status = 'qualified');
