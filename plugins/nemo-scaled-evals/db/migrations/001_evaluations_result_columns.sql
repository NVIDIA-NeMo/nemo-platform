-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Result envelope columns for evaluations (added after initial compose volumes).
-- Idempotent: safe to re-run on every postgres start.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = 'evaluations'
    ) THEN
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'evaluations'
          AND column_name = 'result'
    ) THEN
        ALTER TABLE evaluations ADD COLUMN result JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'evaluations'
          AND column_name = 'reward'
    ) THEN
        ALTER TABLE evaluations ADD COLUMN reward DOUBLE PRECISION;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'evaluations'
          AND column_name = 'n_trials'
    ) THEN
        ALTER TABLE evaluations ADD COLUMN n_trials INTEGER;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'evaluations'
          AND column_name = 'n_errored'
    ) THEN
        ALTER TABLE evaluations ADD COLUMN n_errored INTEGER;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'evaluations'
          AND column_name = 'finished_at'
    ) THEN
        ALTER TABLE evaluations ADD COLUMN finished_at TIMESTAMPTZ;
    END IF;
END $$;
