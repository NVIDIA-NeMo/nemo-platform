-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS dispatch_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dispatch_claimed_by TEXT,
    ADD COLUMN IF NOT EXISTS dispatch_attempts INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS evaluations_dispatch_claim_idx
    ON evaluations (dispatch_claimed_at)
    WHERE status IN ('queued', 'provisioning', 'running');
