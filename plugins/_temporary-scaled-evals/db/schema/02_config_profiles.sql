-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Config profiles: reusable non-secret config keyed by type, with an
-- opaque-per-type JSON config blob. See docs/API.md section "Config profiles".

CREATE TYPE config_profile_type AS ENUM ('harbor', 'gym', 'switchyard', 'intake');

CREATE TABLE config_profiles (
    id         TEXT PRIMARY KEY,
    owner_id   TEXT REFERENCES users(id),
    name       TEXT NOT NULL,
    type       config_profile_type NOT NULL,
    config     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
    -- TODO(owner): add owner_user_id to back the `?mine` filter (API.md:67)
    --      once auth lands. Omitted for now — there is no way to enforce
    --      ownership without the users table / auth integration.
);

CREATE INDEX config_profiles_type_live_idx
    ON config_profiles (type)
    WHERE deleted_at IS NULL;

CREATE INDEX config_profiles_created_at_idx
    ON config_profiles (created_at DESC);
