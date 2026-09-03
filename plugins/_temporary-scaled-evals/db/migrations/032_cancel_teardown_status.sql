-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Expose durable cancellation cleanup progress for evaluations and benchmark members.
-- Idempotent: safe to re-run on existing Compose and hosted databases.

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS cancel_teardown_status TEXT NOT NULL DEFAULT 'not_requested',
    ADD COLUMN IF NOT EXISTS cancel_teardown_error TEXT,
    ADD COLUMN IF NOT EXISTS cancel_teardown_updated_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'evaluations_cancel_teardown_status_check'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_cancel_teardown_status_check CHECK (
                cancel_teardown_status IN ('not_requested', 'pending', 'succeeded', 'failed')
            );
    END IF;
END $$;
