-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Preserve non-numeric scalar rewards without changing the legacy numeric
-- reward column used by existing Harbor/Gym consumers and query paths.

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS reward_value JSONB;

UPDATE evaluations
SET reward_value = to_jsonb(reward)
WHERE reward_value IS NULL
  AND reward IS NOT NULL;
