-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Generic framework profile support for Harbor and NeMo Gym.
-- Idempotent: safe to re-run on every postgres start.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_type
        WHERE typname = 'config_profile_type'
    ) THEN
        ALTER TYPE config_profile_type ADD VALUE IF NOT EXISTS 'gym';
    END IF;
END $$;

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
          AND column_name = 'framework'
    ) THEN
        ALTER TABLE evaluations
            ADD COLUMN framework TEXT NOT NULL DEFAULT 'harbor';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'evaluations'
          AND column_name = 'framework_profile_id'
    ) THEN
        ALTER TABLE evaluations
            ADD COLUMN framework_profile_id TEXT;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = 'config_profiles'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'evaluations_framework_profile_id_fkey'
          AND conrelid = 'evaluations'::regclass
    ) THEN
        ALTER TABLE evaluations
            ADD CONSTRAINT evaluations_framework_profile_id_fkey
            FOREIGN KEY (framework_profile_id)
            REFERENCES config_profiles (id)
            ON DELETE RESTRICT;
    END IF;
END $$;
