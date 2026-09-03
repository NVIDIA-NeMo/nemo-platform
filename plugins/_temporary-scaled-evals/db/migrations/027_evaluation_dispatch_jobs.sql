-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Standalone evaluation Jobs survive control-plane Deployment rollouts.
ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS dispatch_job_name TEXT,
    ADD COLUMN IF NOT EXISTS dispatch_job_uid TEXT;
