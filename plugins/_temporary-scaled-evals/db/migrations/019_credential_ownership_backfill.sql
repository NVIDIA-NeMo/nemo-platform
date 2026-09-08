-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Safely recover ownership for legacy credentials when every live evaluation
-- reference agrees on one non-null owner. Ambiguous and unused rows remain
-- NULL and are accessible only to configured admins (or auth-disabled local
-- development) until an operator explicitly assigns them.
WITH inferred AS (
    SELECT
        refs.value AS credential_id,
        MIN(e.owner_id) AS owner_id
    FROM evaluations e
    CROSS JOIN LATERAL jsonb_each_text(e.credentials) refs
    WHERE e.owner_id IS NOT NULL
      AND e.deleted_at IS NULL
    GROUP BY refs.value
    HAVING COUNT(DISTINCT e.owner_id) = 1
)
UPDATE credentials c
SET owner_id = inferred.owner_id,
    updated_at = NOW()
FROM inferred
WHERE c.id = inferred.credential_id
  AND c.owner_id IS NULL;
