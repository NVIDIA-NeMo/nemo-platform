-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

CREATE TABLE IF NOT EXISTS evaluation_resource_usage (
    evaluation_id              TEXT NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    execution_number           INTEGER NOT NULL CHECK (execution_number >= 1),
    component                  TEXT NOT NULL,
    source                     TEXT NOT NULL,
    sample_count               BIGINT NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
    first_observed_at           TIMESTAMPTZ NOT NULL,
    last_observed_at            TIMESTAMPTZ NOT NULL,
    cpu_sample_count           BIGINT NOT NULL DEFAULT 0 CHECK (cpu_sample_count >= 0),
    cpu_usage_cores_sum        DOUBLE PRECISION NOT NULL DEFAULT 0,
    cpu_usage_cores_max        DOUBLE PRECISION NOT NULL DEFAULT 0,
    memory_sample_count        BIGINT NOT NULL DEFAULT 0 CHECK (memory_sample_count >= 0),
    memory_usage_bytes_sum     DOUBLE PRECISION NOT NULL DEFAULT 0,
    memory_usage_bytes_max     BIGINT NOT NULL DEFAULT 0,
    cpu_request_cores          DOUBLE PRECISION,
    cpu_limit_cores            DOUBLE PRECISION,
    memory_request_bytes       BIGINT,
    memory_limit_bytes         BIGINT,
    gpu_request                DOUBLE PRECISION,
    gpu_sample_count           BIGINT NOT NULL DEFAULT 0 CHECK (gpu_sample_count >= 0),
    gpu_usage_percent_sum      DOUBLE PRECISION NOT NULL DEFAULT 0,
    gpu_usage_percent_max      DOUBLE PRECISION NOT NULL DEFAULT 0,
    gpu_memory_sample_count    BIGINT NOT NULL DEFAULT 0 CHECK (gpu_memory_sample_count >= 0),
    gpu_memory_usage_bytes_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
    gpu_memory_usage_bytes_max BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (evaluation_id, execution_number, component)
);

CREATE INDEX IF NOT EXISTS evaluation_resource_usage_observed_idx
    ON evaluation_resource_usage (last_observed_at DESC);

-- Admin history windows use the terminal activity timestamp. Keep those reads
-- index-backed as the evaluations table grows instead of scanning every run.
CREATE INDEX IF NOT EXISTS evaluations_terminal_activity_idx
    ON evaluations ((COALESCE(finished_at, updated_at)))
    WHERE deleted_at IS NULL;
