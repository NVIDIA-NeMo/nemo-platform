-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Backend-neutral outcome projections. Keep reward/n_trials/n_errored intact
-- for existing clients; these columns add the detail needed to distinguish a
-- dispatch failure, a scored zero, failed solves, and errored trials.
ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS n_completed INTEGER;
ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS n_failed_solve INTEGER;
ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS exception_counts JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE evaluations
SET n_completed = GREATEST(n_trials - COALESCE(n_errored, 0), 0)
WHERE n_completed IS NULL AND n_trials IS NOT NULL;
