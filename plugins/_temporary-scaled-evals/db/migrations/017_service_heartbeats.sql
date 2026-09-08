-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Presence heartbeats let readiness distinguish an enabled asynchronous
-- service from an API-only deployment, including while the worker is idle.
CREATE TABLE IF NOT EXISTS service_heartbeats (
    service      TEXT NOT NULL,
    instance_id  TEXT NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (service, instance_id)
);

CREATE INDEX IF NOT EXISTS service_heartbeats_freshness_idx
    ON service_heartbeats (service, heartbeat_at DESC);
