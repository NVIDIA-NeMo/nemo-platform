-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Existing databases predate the OpenShift BYOK path even though the current
-- bootstrap schema already includes it. Keep upgraded control planes aligned
-- so image builds and sandbox dispatch can store a caller's short-lived oc token.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'credential_provider') THEN
        ALTER TYPE credential_provider ADD VALUE IF NOT EXISTS 'openshift';
    END IF;
END $$;
