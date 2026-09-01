-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- External Switchyard endpoints authenticate clients with a distinct,
-- evaluation-scoped token rather than forwarding an upstream model key.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'credential_provider') THEN
        ALTER TYPE credential_provider ADD VALUE IF NOT EXISTS 'switchyard';
    END IF;
END
$$;
