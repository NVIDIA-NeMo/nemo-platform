-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Durable cleanup and independent infrastructure retry accounting for failed
-- Kubernetes evaluation runners. 035 is intentionally unused.

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS infrastructure_retries INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_infrastructure_retries INTEGER NOT NULL DEFAULT 2,
    ADD COLUMN IF NOT EXISTS dispatch_reconcile_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dispatch_reconcile_claimed_by TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_infrastructure_retries_ck'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_infrastructure_retries_ck
            CHECK (infrastructure_retries >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_max_infrastructure_retries_ck'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_max_infrastructure_retries_ck
            CHECK (max_infrastructure_retries >= 0);
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_execution_bounds_ck'
          AND conrelid = 'evaluations'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%infrastructure_retries%'
    ) THEN
        ALTER TABLE evaluations DROP CONSTRAINT evaluations_execution_bounds_ck;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_execution_bounds_ck'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_execution_bounds_ck CHECK (
                infrastructure_retries <= max_infrastructure_retries
                AND current_execution <= max_executions + infrastructure_retries
            );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS evaluation_execution_cleanups (
    id                  BIGSERIAL PRIMARY KEY,
    evaluation_id       TEXT NOT NULL REFERENCES evaluations (id) ON DELETE CASCADE,
    execution_number    INTEGER NOT NULL CHECK (execution_number >= 1),
    runtime             TEXT NOT NULL,
    backend_handle      TEXT NOT NULL,
    dispatch_job_name   TEXT NOT NULL,
    failure_code        TEXT NOT NULL,
    failure_detail      TEXT NOT NULL,
    retry_after_cleanup BOOLEAN NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'deleting', 'delete_failed', 'deleted')
    ),
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    teardown_claimed_at TIMESTAMPTZ,
    teardown_claimed_by TEXT,
    teardown_attempts   INTEGER NOT NULL DEFAULT 0,
    delete_error        TEXT,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evaluation_execution_cleanups_execution_key
        UNIQUE (evaluation_id, execution_number)
);

CREATE INDEX IF NOT EXISTS evaluation_execution_cleanups_pending_idx
    ON evaluation_execution_cleanups (status, next_attempt_at, id)
    WHERE status IN ('pending', 'delete_failed');
