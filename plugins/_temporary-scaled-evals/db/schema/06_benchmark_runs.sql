-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Benchmark runs: running a benchmark creates one evaluation per member task.
-- A benchmark_run is just the grouping + the run
-- config; its members are ordinary `evaluations` rows carrying
-- `benchmark_run_id`. This mirrors the resource layer (a benchmark groups tasks)
-- at the run layer (a benchmark run groups evaluations). The run launches no
-- sandbox itself: at create time it inserts one member evaluation per member
-- task, which the dispatch worker pool runs independently.
--
-- The run's status / reward / per-task breakdown are NOT stored here — they are
-- derived on read from the member evaluations (see
-- benchmark_run_repository.derive_run_view). The only run-level fact that can't
-- be derived from members is an explicit cancel, so we keep `cancelled_at`.
--
-- Reuses evaluation_visibility from 04_evaluations.sql (loaded earlier).

CREATE TABLE benchmark_runs (
    id                    TEXT PRIMARY KEY,
    owner_id              TEXT REFERENCES users(id),
    name                  TEXT NOT NULL,
    framework             TEXT NOT NULL DEFAULT 'harbor',
    requested_framework_version TEXT,
    framework_version     TEXT,
    runner_image_ref      TEXT,
    runner_image_digest   TEXT,
    framework_adapter_version TEXT,
    sandbox_k8s_version   TEXT,
    runner_metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The benchmark revision that was run. ON DELETE RESTRICT so a benchmark
    -- revision with runs cannot be hard-deleted out from under them.
    benchmark_id          TEXT NOT NULL,
    benchmark_revision    INTEGER NOT NULL,
    -- Run configuration, recorded on the run and inherited by every member
    -- evaluation it spawns (so the run is reproducible and the members are
    -- ordinary task runs).
    framework_profile_id  TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    harbor_profile_id     TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    switchyard_profile_id TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    intake_profile_id     TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    credentials           JSONB NOT NULL DEFAULT '{}'::jsonb,
    runtime               TEXT NOT NULL DEFAULT 'sandbox_k8s',
    network_policy        evaluation_network_policy NOT NULL DEFAULT 'unrestricted',
    network_policy_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Trials within each member task (passed to each member); cross-task
    -- concurrency comes from the dispatch worker pool, not this knob.
    parallelism           INTEGER NOT NULL DEFAULT 1,
    -- Optional exact-parity shared-Switchyard member concurrency. Existing
    -- per-member `parallelism` semantics remain unchanged.
    max_concurrent_members INTEGER CHECK (
        max_concurrent_members IS NULL OR max_concurrent_members >= 1
    ),
    visibility            evaluation_visibility NOT NULL DEFAULT 'private',
    -- Explicit cancel: derived status is 'cancelled' when set. Every other
    -- run state (running/succeeded/failed + reward) derives from members.
    cancelled_at          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at            TIMESTAMPTZ,

    FOREIGN KEY (benchmark_id, benchmark_revision)
        REFERENCES benchmark_revisions (benchmark_id, revision)
        ON DELETE RESTRICT
);

CREATE INDEX benchmark_runs_benchmark_idx
    ON benchmark_runs (benchmark_id);

CREATE INDEX benchmark_runs_created_at_idx
    ON benchmark_runs (created_at DESC);

-- The member-execution link from evaluations (declared in 04_evaluations.sql).
-- ON DELETE CASCADE so deleting a run removes its member evaluations.
ALTER TABLE evaluations
    ADD CONSTRAINT evaluations_benchmark_run_fkey
    FOREIGN KEY (benchmark_run_id)
    REFERENCES benchmark_runs (id) ON DELETE CASCADE;

CREATE TABLE benchmark_switchyard_campaigns (
    benchmark_run_id       TEXT PRIMARY KEY REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    status                 TEXT NOT NULL CHECK (status IN (
        'provisioning', 'ready', 'provision_failed', 'finalizing',
        'evidence_failed', 'draining', 'deleting', 'delete_failed', 'deleted'
    )),
    profile_id             TEXT NOT NULL,
    config_hash            TEXT NOT NULL,
    credential_hash        TEXT NOT NULL,
    max_concurrent_members INTEGER NOT NULL CHECK (max_concurrent_members >= 1),
    namespace              TEXT,
    resource_name          TEXT,
    endpoint               TEXT,
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    cancel_requested_at    TIMESTAMPTZ,
    claim_owner            TEXT,
    claim_expires_at       TIMESTAMPTZ,
    claim_attempt          INTEGER NOT NULL DEFAULT 0,
    evidence_status        TEXT NOT NULL DEFAULT 'pending'
        CHECK (evidence_status IN ('pending', 'capturing', 'ready', 'unavailable')),
    evidence_object_key    TEXT,
    evidence_sha256        TEXT,
    evidence_error         TEXT,
    drain_until            TIMESTAMPTZ,
    delete_error           TEXT,
    deleted_at             TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX benchmark_switchyard_campaigns_work_idx
    ON benchmark_switchyard_campaigns (status, claim_expires_at, drain_until)
    WHERE status <> 'deleted';

CREATE TABLE benchmark_switchyard_launches (
    evaluation_id          TEXT PRIMARY KEY REFERENCES evaluations(id) ON DELETE CASCADE,
    benchmark_run_id       TEXT NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    status                 TEXT NOT NULL CHECK (status IN (
        'launching', 'running', 'cleanup_pending', 'cleanup_acknowledged', 'not_launched'
    )),
    permit_owner           TEXT NOT NULL,
    permit_expires_at      TIMESTAMPTZ NOT NULL,
    backend_handle         JSONB,
    cleanup_attempts       INTEGER NOT NULL DEFAULT 0,
    cleanup_error          TEXT,
    cleanup_acknowledged_at TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX benchmark_switchyard_launches_active_idx
    ON benchmark_switchyard_launches (benchmark_run_id, status, permit_expires_at)
    WHERE status IN ('launching', 'running', 'cleanup_pending');
