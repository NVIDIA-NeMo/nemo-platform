-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Ordered user messages sent before the task instruction.
ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS initial_user_turns TEXT[] NOT NULL DEFAULT '{}';
