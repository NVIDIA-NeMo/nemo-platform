-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Allow evaluations to carry extra skills injected at runtime by easy-eval.
-- The dispatch worker downloads each S3 object key and places the file into
-- environment/skills/ before Harbor uploads skills to the sandbox pod.
ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS extra_skill_object_keys TEXT[] DEFAULT NULL;
