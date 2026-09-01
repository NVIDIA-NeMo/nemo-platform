-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Add per-evaluation network isolation mode. Existing rows keep open-book
-- semantics; closed-book requests are validated in the API/dispatch layer.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'evaluation_network_mode') THEN
        CREATE TYPE evaluation_network_mode AS ENUM ('open_book', 'closed_book');
    END IF;
END $$;

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS network_mode evaluation_network_mode NOT NULL DEFAULT 'open_book';
