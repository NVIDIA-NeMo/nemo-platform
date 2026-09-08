-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Normalize shared Switchyard campaign lease metadata to the current schema type.
-- Some early deployments created the column as JSON, which breaks COALESCE
-- updates when psycopg sends JSONB parameters.

ALTER TABLE benchmark_switchyard_campaigns
    ALTER COLUMN metadata TYPE JSONB
    USING COALESCE(metadata::jsonb, '{}'::jsonb),
    ALTER COLUMN metadata SET DEFAULT '{}'::jsonb,
    ALTER COLUMN metadata SET NOT NULL;
