-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Preserve the first worker claim so queue time remains observable after a
-- task image build completes. Existing active builds acquire an approximate
-- first claim on their next heartbeat; new builds record it exactly.
ALTER TABLE task_revisions
    ADD COLUMN IF NOT EXISTS build_first_claimed_at TIMESTAMPTZ;
