-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS archive_status TEXT NOT NULL DEFAULT 'missing',
    ADD COLUMN IF NOT EXISTS archive_object_key TEXT,
    ADD COLUMN IF NOT EXISTS archive_size_bytes BIGINT,
    ADD COLUMN IF NOT EXISTS archive_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS archive_built_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS archive_error TEXT,
    ADD COLUMN IF NOT EXISTS archive_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS archive_claimed_by TEXT,
    ADD COLUMN IF NOT EXISTS archive_build_attempts INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'evaluations_archive_status_check'
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_archive_status_check
            CHECK (archive_status IN ('missing', 'building', 'ready'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS evaluations_archive_queue_idx
    ON evaluations (archive_status, archive_requested_at)
    WHERE archive_status = 'building';
