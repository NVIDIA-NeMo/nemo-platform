-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Durable task-image build queue. The task revision remains the user-facing
-- source of truth; these columns persist enough worker state to resume after a
-- process or deployment restart without storing decrypted credentials.
ALTER TABLE task_revisions
    ADD COLUMN IF NOT EXISTS build_backend TEXT,
    ADD COLUMN IF NOT EXISTS build_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS build_credentials JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS build_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS build_claimed_by TEXT,
    ADD COLUMN IF NOT EXISTS build_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS build_next_attempt_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS task_revisions_build_queue_idx
    ON task_revisions (build_next_attempt_at, build_started_at)
    WHERE status = 'building' AND build_backend IS NOT NULL;

-- Older BackgroundTask builds have no persisted request to replay. Fail only
-- rows already stale at migration time; a recently active legacy task may still
-- complete normally during a rolling deploy.
UPDATE task_revisions
SET status = 'failed',
    build_error = 'build interrupted before durable queue migration; finalize a new revision',
    build_completed_at = NOW()
WHERE status = 'building'
  AND build_backend IS NULL
  AND build_started_at < NOW() - INTERVAL '2 hours';
