-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

ALTER TABLE evaluation_resource_usage
    ADD COLUMN IF NOT EXISTS collection_status TEXT NOT NULL DEFAULT 'sampled',
    ADD COLUMN IF NOT EXISTS collection_error TEXT;

CREATE TABLE IF NOT EXISTS evaluation_execution_telemetry (
    evaluation_id              TEXT NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    execution_number           INTEGER NOT NULL CHECK (execution_number >= 1),
    provisioning_started_at    TIMESTAMPTZ,
    running_started_at         TIMESTAMPTZ,
    terminal_at                TIMESTAMPTZ,
    terminal_status            TEXT CHECK (
        terminal_status IS NULL OR terminal_status IN ('succeeded', 'failed', 'cancelled')
    ),
    failure_phase              TEXT,
    input_tokens               BIGINT CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens              BIGINT CHECK (output_tokens IS NULL OR output_tokens >= 0),
    cached_tokens              BIGINT CHECK (cached_tokens IS NULL OR cached_tokens >= 0),
    cache_creation_tokens      BIGINT CHECK (
        cache_creation_tokens IS NULL OR cache_creation_tokens >= 0
    ),
    usage_source               TEXT NOT NULL DEFAULT 'unknown',
    turn_count                 BIGINT CHECK (turn_count IS NULL OR turn_count >= 0),
    tool_call_count            BIGINT CHECK (tool_call_count IS NULL OR tool_call_count >= 0),
    cost_usd                   DOUBLE PRECISION CHECK (cost_usd IS NULL OR cost_usd >= 0),
    cost_source                TEXT NOT NULL DEFAULT 'unknown' CHECK (
        cost_source IN ('provider', 'estimated', 'unknown')
    ),
    raw_artifact_refs          JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(raw_artifact_refs) = 'array'
    ),
    intake_experiment_ref      TEXT,
    intake_run_refs            JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(intake_run_refs) = 'array'
    ),
    intake_status              TEXT NOT NULL DEFAULT 'disabled' CHECK (
        intake_status IN ('disabled', 'pending', 'succeeded', 'failed', 'no_records')
    ),
    intake_expected_records    INTEGER CHECK (
        intake_expected_records IS NULL OR intake_expected_records >= 0
    ),
    intake_uploaded_records    INTEGER CHECK (
        intake_uploaded_records IS NULL OR intake_uploaded_records >= 0
    ),
    intake_error               TEXT,
    artifact_sync_status       TEXT NOT NULL DEFAULT 'pending' CHECK (
        artifact_sync_status IN ('pending', 'succeeded', 'failed')
    ),
    artifact_sync_file_count   INTEGER CHECK (
        artifact_sync_file_count IS NULL OR artifact_sync_file_count >= 0
    ),
    artifact_sync_error        TEXT,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluation_id, execution_number)
);

CREATE INDEX IF NOT EXISTS evaluation_execution_telemetry_terminal_idx
    ON evaluation_execution_telemetry (terminal_at DESC)
    WHERE terminal_at IS NOT NULL;
