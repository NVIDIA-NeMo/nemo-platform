-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Replace the book-mode-shaped sandbox field with a generic direct-egress
-- policy. Keep this migration safe for databases that already applied the
-- short-lived 013/014 network_mode migrations.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'evaluation_network_policy') THEN
        CREATE TYPE evaluation_network_policy AS ENUM (
            'unrestricted', 'default_deny', 'scoped_egress'
        );
    END IF;
END $$;

DO $$
DECLARE
    evaluations_need_migration BOOLEAN;
    benchmark_runs_need_migration BOOLEAN;
BEGIN
    evaluations_need_migration := NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'evaluations' AND column_name = 'network_policy'
    );
    benchmark_runs_need_migration := NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'benchmark_runs' AND column_name = 'network_policy'
    );

    ALTER TABLE evaluations
        ADD COLUMN IF NOT EXISTS network_policy evaluation_network_policy
            NOT NULL DEFAULT 'unrestricted',
        ADD COLUMN IF NOT EXISTS network_policy_config JSONB
            NOT NULL DEFAULT '{}'::jsonb;

    ALTER TABLE benchmark_runs
        ADD COLUMN IF NOT EXISTS network_policy evaluation_network_policy
            NOT NULL DEFAULT 'unrestricted',
        ADD COLUMN IF NOT EXISTS network_policy_config JSONB
            NOT NULL DEFAULT '{}'::jsonb;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'evaluations' AND column_name = 'network_mode'
    ) THEN
        IF evaluations_need_migration THEN
            UPDATE evaluations
            SET network_policy = CASE network_mode::text
                WHEN 'closed_book' THEN 'default_deny'::evaluation_network_policy
                ELSE 'unrestricted'::evaluation_network_policy
            END;
        END IF;
        ALTER TABLE evaluations DROP COLUMN network_mode;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'benchmark_runs' AND column_name = 'network_mode'
    ) THEN
        IF benchmark_runs_need_migration THEN
            UPDATE benchmark_runs
            SET network_policy = CASE network_mode::text
                WHEN 'closed_book' THEN 'default_deny'::evaluation_network_policy
                ELSE 'unrestricted'::evaluation_network_policy
            END;
        END IF;
        ALTER TABLE benchmark_runs DROP COLUMN network_mode;
    END IF;
END $$;

DROP TYPE IF EXISTS evaluation_network_mode;
