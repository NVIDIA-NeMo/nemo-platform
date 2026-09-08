-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Benchmark runs fan out network_mode to member evaluations. The enum is
-- defined in 013_evaluation_network_mode.sql for upgraded databases and in
-- db/schema/04_evaluations.sql for fresh installs.
ALTER TABLE benchmark_runs
    ADD COLUMN IF NOT EXISTS network_mode evaluation_network_mode NOT NULL DEFAULT 'open_book';
