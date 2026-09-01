-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Preserve the complete framework qualification and signed artifact attestation
-- selected at submission. This is intentionally a snapshot: later catalog or
-- deployment changes must not rewrite the provenance of historical runs.
ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS runner_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE benchmark_runs
    ADD COLUMN IF NOT EXISTS runner_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
