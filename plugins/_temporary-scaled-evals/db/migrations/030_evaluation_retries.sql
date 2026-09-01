-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS current_execution INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS max_executions INTEGER NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_failure_code TEXT,
    ADD COLUMN IF NOT EXISTS last_failure_category TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_current_execution_ck'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_current_execution_ck CHECK (current_execution >= 1);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_max_executions_ck'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_max_executions_ck CHECK (max_executions >= 1);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_execution_bounds_ck'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_execution_bounds_ck CHECK (
                current_execution <= max_executions
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'evaluations_last_failure_category_ck'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_last_failure_category_ck CHECK (
                last_failure_category IS NULL
                OR last_failure_category IN ('retryable_task', 'non_retryable')
            );
    END IF;
END $$;

ALTER TABLE evaluation_runtime_resources
    ADD COLUMN IF NOT EXISTS execution_number INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'evaluation_runtime_resources_evaluation_id_kind_key'
          AND conrelid = 'evaluation_runtime_resources'::regclass
    ) THEN
        UPDATE evaluation_runtime_resources AS resource
        SET execution_number = evaluation.current_execution
        FROM evaluations AS evaluation
        WHERE evaluation.id = resource.evaluation_id;

        ALTER TABLE evaluation_runtime_resources
            DROP CONSTRAINT evaluation_runtime_resources_evaluation_id_kind_key;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'evaluation_runtime_resources_execution_number_ck'
          AND conrelid = 'evaluation_runtime_resources'::regclass
    ) THEN
        ALTER TABLE evaluation_runtime_resources
            ADD CONSTRAINT evaluation_runtime_resources_execution_number_ck
            CHECK (execution_number >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'evaluation_runtime_resources_evaluation_execution_kind_key'
          AND conrelid = 'evaluation_runtime_resources'::regclass
    ) THEN
        ALTER TABLE evaluation_runtime_resources
            ADD CONSTRAINT evaluation_runtime_resources_evaluation_execution_kind_key
            UNIQUE (evaluation_id, execution_number, kind);
    END IF;
END $$;
