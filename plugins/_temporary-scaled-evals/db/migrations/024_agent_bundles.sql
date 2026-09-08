-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

DO $$ BEGIN
    CREATE TYPE agent_bundle_visibility AS ENUM ('private', 'public');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE agent_bundle_qualification AS ENUM ('registered', 'qualified', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS agent_bundles (
    id                       TEXT PRIMARY KEY,
    owner_id                 TEXT REFERENCES users(id),
    bundle_name              TEXT NOT NULL,
    agent_name               TEXT NOT NULL,
    agent_version            TEXT NOT NULL,
    image_ref                TEXT NOT NULL,
    image_digest             TEXT NOT NULL,
    entrypoint               TEXT NOT NULL,
    platform                 TEXT NOT NULL DEFAULT 'linux/amd64',
    runtime_abi              TEXT NOT NULL DEFAULT 'glibc',
    bundle_layout_version    INTEGER NOT NULL DEFAULT 1,
    builder_profile          TEXT NOT NULL DEFAULT 'node22-npm-v1',
    source_lock_digest       TEXT NOT NULL,
    fingerprint              TEXT NOT NULL,
    metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility               agent_bundle_visibility NOT NULL DEFAULT 'private',
    qualification_status     agent_bundle_qualification NOT NULL DEFAULT 'registered',
    qualification_evidence   JSONB NOT NULL DEFAULT '{}'::jsonb,
    qualified_at             TIMESTAMPTZ,
    qualified_by             TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at               TIMESTAMPTZ,
    CONSTRAINT agent_bundles_immutable_image_ck CHECK (
        image_digest ~ '^[^[:space:]@]+@sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_bundles_runtime_tag_ck CHECK (
        image_ref ~ '^[^[:space:]@]+:[^/[:space:]@]+$'
    ),
    CONSTRAINT agent_bundles_source_lock_ck CHECK (
        source_lock_digest ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_bundles_fingerprint_ck CHECK (
        fingerprint ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_bundles_public_qualified_ck CHECK (
        visibility <> 'public' OR qualification_status = 'qualified'
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_bundles_owner_name_live_uq
    ON agent_bundles (COALESCE(owner_id, ''), bundle_name)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS agent_bundles_public_idx
    ON agent_bundles (agent_name, agent_version)
    WHERE deleted_at IS NULL AND visibility = 'public';

CREATE INDEX IF NOT EXISTS agent_bundles_owner_idx
    ON agent_bundles (owner_id, created_at DESC)
    WHERE deleted_at IS NULL;
