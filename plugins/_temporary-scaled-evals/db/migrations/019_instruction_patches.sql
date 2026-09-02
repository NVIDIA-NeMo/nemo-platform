-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Support runtime instruction patching at dispatch time.
ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS instruction_prefix TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS instruction_postfix TEXT DEFAULT NULL;
