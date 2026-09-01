-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Resolve user-selected framework versions to immutable runner metadata before
-- queue insertion. Existing runs remain nullable because their exact, formerly
-- unpinned Harbor dependency cannot be reconstructed safely.

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS requested_framework_version TEXT,
    ADD COLUMN IF NOT EXISTS framework_version TEXT,
    ADD COLUMN IF NOT EXISTS runner_image_ref TEXT,
    ADD COLUMN IF NOT EXISTS runner_image_digest TEXT,
    ADD COLUMN IF NOT EXISTS framework_adapter_version TEXT,
    ADD COLUMN IF NOT EXISTS sandbox_k8s_version TEXT;

ALTER TABLE benchmark_runs
    ADD COLUMN IF NOT EXISTS requested_framework_version TEXT,
    ADD COLUMN IF NOT EXISTS framework_version TEXT,
    ADD COLUMN IF NOT EXISTS runner_image_ref TEXT,
    ADD COLUMN IF NOT EXISTS runner_image_digest TEXT,
    ADD COLUMN IF NOT EXISTS framework_adapter_version TEXT,
    ADD COLUMN IF NOT EXISTS sandbox_k8s_version TEXT;
