-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Number of independent Harbor attempts per task execution.
ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS n_attempts INTEGER NOT NULL DEFAULT 1;
