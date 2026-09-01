-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS execution_snapshot JSONB,
    ADD COLUMN IF NOT EXISTS evidence_status TEXT NOT NULL DEFAULT 'missing',
    ADD COLUMN IF NOT EXISTS evidence_requested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS evidence_built_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS evidence_error TEXT,
    ADD COLUMN IF NOT EXISTS evidence_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS evidence_claimed_by TEXT,
    ADD COLUMN IF NOT EXISTS evidence_build_attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE evaluations
    DROP CONSTRAINT IF EXISTS evaluations_execution_snapshot_object_ck,
    ADD CONSTRAINT evaluations_execution_snapshot_object_ck CHECK (
        execution_snapshot IS NULL OR jsonb_typeof(execution_snapshot) = 'object'
    ),
    DROP CONSTRAINT IF EXISTS evaluations_evidence_status_ck,
    ADD CONSTRAINT evaluations_evidence_status_ck CHECK (
        evidence_status IN ('missing', 'building', 'ready')
    );

CREATE INDEX IF NOT EXISTS evaluations_evidence_queue_idx
    ON evaluations (evidence_status, evidence_requested_at)
    WHERE evidence_status = 'building' AND evidence_build_attempts < 5;
