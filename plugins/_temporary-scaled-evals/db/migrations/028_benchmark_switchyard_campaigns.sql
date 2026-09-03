-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Durable shared Switchyard lifecycle for exact-parity benchmark campaigns.
ALTER TABLE benchmark_runs
    ADD COLUMN IF NOT EXISTS max_concurrent_members INTEGER
        CHECK (max_concurrent_members IS NULL OR max_concurrent_members >= 1);

CREATE TABLE IF NOT EXISTS benchmark_switchyard_campaigns (
    benchmark_run_id       TEXT PRIMARY KEY REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    status                 TEXT NOT NULL CHECK (status IN (
        'provisioning', 'ready', 'provision_failed', 'finalizing',
        'evidence_failed', 'draining', 'deleting', 'delete_failed', 'deleted'
    )),
    profile_id             TEXT NOT NULL,
    config_hash            TEXT NOT NULL,
    credential_hash        TEXT NOT NULL,
    max_concurrent_members INTEGER NOT NULL CHECK (max_concurrent_members >= 1),
    namespace              TEXT,
    resource_name          TEXT,
    endpoint               TEXT,
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    cancel_requested_at    TIMESTAMPTZ,
    claim_owner            TEXT,
    claim_expires_at       TIMESTAMPTZ,
    claim_attempt          INTEGER NOT NULL DEFAULT 0,
    evidence_status        TEXT NOT NULL DEFAULT 'pending'
        CHECK (evidence_status IN ('pending', 'capturing', 'ready', 'unavailable')),
    evidence_object_key    TEXT,
    evidence_sha256        TEXT,
    evidence_error         TEXT,
    drain_until            TIMESTAMPTZ,
    delete_error           TEXT,
    deleted_at             TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS benchmark_switchyard_campaigns_work_idx
    ON benchmark_switchyard_campaigns (status, claim_expires_at, drain_until)
    WHERE status <> 'deleted';

CREATE TABLE IF NOT EXISTS benchmark_switchyard_launches (
    evaluation_id          TEXT PRIMARY KEY REFERENCES evaluations(id) ON DELETE CASCADE,
    benchmark_run_id       TEXT NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    status                 TEXT NOT NULL CHECK (status IN (
        'launching', 'running', 'cleanup_pending', 'cleanup_acknowledged', 'not_launched'
    )),
    permit_owner           TEXT NOT NULL,
    permit_expires_at      TIMESTAMPTZ NOT NULL,
    backend_handle         JSONB,
    cleanup_attempts       INTEGER NOT NULL DEFAULT 0,
    cleanup_error          TEXT,
    cleanup_acknowledged_at TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS benchmark_switchyard_launches_active_idx
    ON benchmark_switchyard_launches (benchmark_run_id, status, permit_expires_at)
    WHERE status IN ('launching', 'running', 'cleanup_pending');
