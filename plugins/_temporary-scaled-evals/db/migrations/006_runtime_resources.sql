-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Durable runtime resources, currently used for per-evaluation Switchyard.
-- Idempotent: safe to re-run on existing compose volumes.

CREATE TABLE IF NOT EXISTS evaluation_runtime_resources (
    id                  BIGSERIAL PRIMARY KEY,
    evaluation_id       TEXT NOT NULL REFERENCES evaluations (id) ON DELETE CASCADE,
    kind                TEXT NOT NULL CHECK (kind IN ('switchyard')),
    status              TEXT NOT NULL CHECK (
        status IN ('provisioned', 'draining', 'deleting', 'deleted', 'delete_failed')
    ),
    profile_id          TEXT,
    namespace           TEXT NOT NULL,
    resource_name       TEXT NOT NULL,
    endpoint            TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    drain_until         TIMESTAMPTZ,
    teardown_claimed_at TIMESTAMPTZ,
    teardown_claimed_by TEXT,
    teardown_attempts   INTEGER NOT NULL DEFAULT 0,
    delete_error        TEXT,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (evaluation_id, kind)
);

CREATE INDEX IF NOT EXISTS evaluation_runtime_resources_teardown_idx
    ON evaluation_runtime_resources (kind, status, drain_until)
    WHERE status IN ('draining', 'delete_failed');
