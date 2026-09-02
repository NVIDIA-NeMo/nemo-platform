-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

CREATE TABLE IF NOT EXISTS evaluation_events (
    id            BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES evaluations (id) ON DELETE CASCADE,
    type          TEXT NOT NULL DEFAULT 'status',
    status        evaluation_status NOT NULL,
    detail        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS evaluation_events_evaluation_order_idx
    ON evaluation_events (evaluation_id, created_at ASC, id ASC);
