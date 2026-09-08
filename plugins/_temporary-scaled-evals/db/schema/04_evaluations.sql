-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: Apache-2.0

-- Evaluations: one framework run of a task revision through the dispatch
-- pipeline. See docs/API.md sections "Evaluations", "Run composition".
--
-- Status lifecycle (evaluation_status):
--   blocked -> queued -> provisioning -> running -> succeeded | failed | cancelled
-- A row is inserted at 'queued'; the dispatch worker advances it to
-- 'provisioning' (backend launching the sandbox) then 'running'. Terminal
-- states are 'succeeded' / 'failed' / 'cancelled'. 'blocked' is reserved for
-- runs held behind quota/dependencies (not produced by this MR).

CREATE TYPE evaluation_status AS ENUM (
    'blocked',
    'queued',
    'provisioning',
    'running',
    'succeeded',
    'failed',
    'cancelled'
);

-- Same value set as task_visibility, kept as its own type so this
-- resource's schema file is self-contained (no cross-file load ordering).
CREATE TYPE evaluation_visibility AS ENUM ('private', 'team', 'org', 'public');

-- Direct sandbox egress policy. Switchyard routing/book mode is configured
-- independently by its config profile.
CREATE TYPE evaluation_network_policy AS ENUM (
    'unrestricted', 'default_deny', 'scoped_egress'
);

CREATE TABLE evaluations (
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
    -- Every evaluation is the execution of one task revision (it is "a thing
    -- that ran"). A benchmark run does NOT live here; it is a separate
    -- `benchmark_runs` row (the grouping/aggregate) whose member evaluations are
    -- ordinary evaluations carrying `benchmark_run_id` below.
    task_id          TEXT NOT NULL,
    task_revision    INTEGER NOT NULL,
    -- Set when this evaluation is one member of a benchmark run; NULL
    -- for a standalone single-task run. The benchmark_runs row aggregates its
    -- members by fan-in (a benchmark is an unordered set of tasks run
    -- concurrently, so no per-member ordering is stored). ON DELETE CASCADE so
    -- deleting the run removes its member evaluations. The FK is added in
    -- 06_benchmark_runs.sql (benchmark_runs is defined after this file in load
    -- order).
    benchmark_run_id      TEXT,
    -- Profile ids (config-profiles resource). The FK guarantees the profile
    -- row exists; the router additionally checks it is live (not soft-deleted)
    -- and of the matching type (harbor/gym/switchyard/intake), which a column FK
    -- can't express. ON DELETE RESTRICT so a profile referenced by an
    -- evaluation can't be hard-deleted out from under it. Ownership is NOT
    -- enforced — config_profiles has no owner column yet (pending auth, same
    -- blocker as tasks.owner_user_id).
    framework_profile_id  TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    harbor_profile_id     TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    switchyard_profile_id TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    intake_profile_id     TEXT REFERENCES config_profiles (id) ON DELETE RESTRICT,
    -- Map of role -> credential id, e.g. {"anthropic": "cred_…", "intake": "cred_…"}.
    -- A JSONB map can't carry a column FK, so credential existence is validated
    -- in the router (live rows in `credentials`). Decrypted only at dispatch.
    credentials           JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Names the dispatch RuntimeBackend that launches this run (e.g.
    -- 'sandbox_k8s'). See scaled_evals.dispatch.runtime_backend.
    runtime               TEXT NOT NULL DEFAULT 'sandbox_k8s',
    network_policy        evaluation_network_policy NOT NULL DEFAULT 'unrestricted',
    network_policy_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    n_attempts            INTEGER NOT NULL DEFAULT 1,
    parallelism           INTEGER NOT NULL DEFAULT 1,
    visibility            evaluation_visibility NOT NULL DEFAULT 'private',
    status                evaluation_status NOT NULL DEFAULT 'queued',
    -- Human-readable note on the latest transition (e.g. backend handle,
    -- failure reason). Full transition history is append-only in
    -- evaluation_events.
    status_detail         TEXT,
    -- Durable cancellation cleanup outcome. A cancelled row stays pending
    -- while its evaluation Job owns runtime teardown; API-owned cleanup and
    -- workers transition it to succeeded or failed idempotently.
    cancel_teardown_status TEXT NOT NULL DEFAULT 'not_requested' CHECK (
        cancel_teardown_status IN ('not_requested', 'pending', 'succeeded', 'failed')
    ),
    cancel_teardown_error  TEXT,
    cancel_teardown_updated_at TIMESTAMPTZ,
    -- Opaque handle the backend returns from launch() (e.g. the Sandbox CR
    -- name); used by status()/teardown(). NULL until dispatched.
    backend_handle        TEXT,
    -- Durable dispatch worker lease. Workers claim active rows with
    -- SELECT ... FOR UPDATE SKIP LOCKED and refresh dispatch_claimed_at while
    -- polling. If a worker dies, another worker may recover the row after the
    -- lease timeout.
    dispatch_claimed_at   TIMESTAMPTZ,
    dispatch_claimed_by   TEXT,
    dispatch_job_name     TEXT,
    dispatch_job_uid      TEXT,
    dispatch_reconcile_claimed_at TIMESTAMPTZ,
    dispatch_reconcile_claimed_by TEXT,
    dispatch_attempts     INTEGER NOT NULL DEFAULT 0,
    -- One evaluation remains the logical task/member across retries. The
    -- execution number gives each launched runtime a distinct identity without
    -- adding duplicate evaluation rows to a benchmark run.
    current_execution     INTEGER NOT NULL DEFAULT 1 CHECK (current_execution >= 1),
    max_executions        INTEGER NOT NULL DEFAULT 3 CHECK (max_executions >= 1),
    infrastructure_retries INTEGER NOT NULL DEFAULT 0 CHECK (infrastructure_retries >= 0),
    max_infrastructure_retries INTEGER NOT NULL DEFAULT 2
        CHECK (max_infrastructure_retries >= 0),
    next_retry_at         TIMESTAMPTZ,
    last_failure_code     TEXT,
    last_failure_category TEXT CHECK (
        last_failure_category IS NULL
        OR last_failure_category IN (
            'infrastructure',
            'provider',
            'task',
            'unknown',
            'retryable_task',
            'non_retryable'
        )
    ),
    -- Private, exact inputs captured at submission. This never contains
    -- decrypted credential payloads and is not selected by public API reads.
    -- NULL identifies evaluations created before execution snapshots existed.
    execution_snapshot    JSONB,
    CONSTRAINT evaluations_execution_snapshot_object_ck CHECK (
        execution_snapshot IS NULL OR jsonb_typeof(execution_snapshot) = 'object'
    ),
    -- Durable generation state for public provenance + run-composition SBOM.
    -- Terminal transitions enqueue evidence; dispatch workers retry failures.
    evidence_status       TEXT NOT NULL DEFAULT 'missing'
        CHECK (evidence_status IN ('missing', 'building', 'ready')),
    evidence_requested_at TIMESTAMPTZ,
    evidence_built_at     TIMESTAMPTZ,
    evidence_error        TEXT,
    evidence_claimed_at   TIMESTAMPTZ,
    evidence_claimed_by   TEXT,
    evidence_build_attempts INTEGER NOT NULL DEFAULT 0,
    -- Results archive bundle (`evaluations/<id>/results.tar.gz`) is built by
    -- the dispatch worker, never by the API request thread. `building` means
    -- requested/queued or actively claimed by a worker.
    archive_status        TEXT NOT NULL DEFAULT 'missing'
        CHECK (archive_status IN ('missing', 'building', 'ready')),
    archive_object_key    TEXT,
    archive_size_bytes    BIGINT,
    archive_requested_at  TIMESTAMPTZ,
    archive_built_at      TIMESTAMPTZ,
    archive_error         TEXT,
    archive_claimed_at    TIMESTAMPTZ,
    archive_claimed_by    TEXT,
    archive_build_attempts INTEGER NOT NULL DEFAULT 0,
    -- Result envelope, written back by the dispatch worker once the run
    -- reaches a terminal state (docs/internals/ARCHITECTURE.md: "Results: Postgres
    -- envelope + framework-typed JSON; artifacts in object store"). `result`
    -- is the FULL framework-typed result. `reward_value` preserves the
    -- backend's typed scalar reward (bool/int/float/string). `reward` remains
    -- the legacy numeric projection used by Harbor/Gym query paths. The count
    -- columns are also queryable projections so list/filter paths need not
    -- crack open JSONB. All NULL until terminal. The object-store artifact half
    -- (jobs_dir tarball) is a separate, deferred slice — not these columns.
    result                JSONB,
    reward_value          JSONB,
    reward                DOUBLE PRECISION,
    n_trials              INTEGER,
    n_completed           INTEGER,
    n_errored             INTEGER,
    n_failed_solve        INTEGER,
    exception_counts      JSONB NOT NULL DEFAULT '{}'::jsonb,
    finished_at           TIMESTAMPTZ,
    -- S3 object keys for extra skill files to inject at runtime. The dispatch
    -- worker downloads each key into environment/skills/ before Harbor uploads
    -- skills to the sandbox pod. Set by easy-eval; NULL for plain evaluations.
    extra_skill_object_keys TEXT[],
    instruction_prefix TEXT,
    instruction_postfix TEXT,
    initial_user_turns TEXT[] NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at            TIMESTAMPTZ,
    -- TBD: owner_user_id / team_id — pending auth integration, mirroring the
    -- tasks TBDs. The `mine` list filter needs the authenticated caller
    -- and is inert until then; `shared` is implemented via visibility.

    -- Every evaluation targets a real task revision. ON DELETE RESTRICT so a
    -- task with evaluations cannot be hard-deleted out from under them.
    CONSTRAINT evaluations_execution_bounds_ck CHECK (
        infrastructure_retries <= max_infrastructure_retries
        AND current_execution <= max_executions + infrastructure_retries
    ),
    FOREIGN KEY (task_id, task_revision)
        REFERENCES task_revisions (task_id, revision)
        ON DELETE RESTRICT
    -- The benchmark_run_id FK is added in 06_benchmark_runs.sql (ALTER TABLE)
    -- because benchmark_runs is created after this file in load order.
);

CREATE INDEX evaluations_task_idx
    ON evaluations (task_id);

-- Fan-in / drill-down: an evaluation's benchmark run (member evaluations).
CREATE INDEX evaluations_benchmark_run_idx
    ON evaluations (benchmark_run_id)
    WHERE benchmark_run_id IS NOT NULL;

CREATE INDEX evaluations_created_at_idx
    ON evaluations (created_at DESC);

CREATE INDEX evaluations_terminal_activity_idx
    ON evaluations ((COALESCE(finished_at, updated_at)))
    WHERE deleted_at IS NULL;

-- Worker poll path: rows still in flight.
CREATE INDEX evaluations_active_idx
    ON evaluations (status)
    WHERE status IN ('queued', 'provisioning', 'running');

-- Archive worker queue: rows waiting for server-side tarball creation.
CREATE INDEX evaluations_archive_queue_idx
    ON evaluations (archive_status, archive_requested_at)
    WHERE archive_status = 'building';

CREATE INDEX evaluations_evidence_queue_idx
    ON evaluations (evidence_status, evidence_requested_at)
    WHERE evidence_status = 'building' AND evidence_build_attempts < 5;

CREATE INDEX evaluations_dispatch_claim_idx
    ON evaluations (dispatch_claimed_at)
    WHERE status IN ('queued', 'provisioning', 'running');

-- Append-only status transition history. Consumers read in stable chronological
-- order by (created_at ASC, id ASC); the id tiebreaker makes same-timestamp
-- transitions deterministic.
CREATE TABLE evaluation_events (
    id            BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES evaluations (id) ON DELETE CASCADE,
    type          TEXT NOT NULL DEFAULT 'status',
    status        evaluation_status NOT NULL,
    detail        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX evaluation_events_evaluation_order_idx
    ON evaluation_events (evaluation_id, created_at ASC, id ASC);

-- Bounded aggregates from optional runtime resource samplers. One row per
-- execution/component avoids retaining an unbounded raw time series while
-- preserving sampled averages, peaks, requests, and limits for admin views.
CREATE TABLE evaluation_resource_usage (
    evaluation_id              TEXT NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    execution_number           INTEGER NOT NULL CHECK (execution_number >= 1),
    component                  TEXT NOT NULL,
    source                     TEXT NOT NULL,
    collection_status          TEXT NOT NULL DEFAULT 'sampled',
    collection_error           TEXT,
    sample_count               BIGINT NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
    first_observed_at           TIMESTAMPTZ NOT NULL,
    last_observed_at            TIMESTAMPTZ NOT NULL,
    cpu_sample_count           BIGINT NOT NULL DEFAULT 0 CHECK (cpu_sample_count >= 0),
    cpu_usage_cores_sum        DOUBLE PRECISION NOT NULL DEFAULT 0,
    cpu_usage_cores_max        DOUBLE PRECISION NOT NULL DEFAULT 0,
    memory_sample_count        BIGINT NOT NULL DEFAULT 0 CHECK (memory_sample_count >= 0),
    memory_usage_bytes_sum     DOUBLE PRECISION NOT NULL DEFAULT 0,
    memory_usage_bytes_max     BIGINT NOT NULL DEFAULT 0,
    cpu_request_cores          DOUBLE PRECISION,
    cpu_limit_cores            DOUBLE PRECISION,
    memory_request_bytes       BIGINT,
    memory_limit_bytes         BIGINT,
    gpu_request                DOUBLE PRECISION,
    gpu_sample_count           BIGINT NOT NULL DEFAULT 0 CHECK (gpu_sample_count >= 0),
    gpu_usage_percent_sum      DOUBLE PRECISION NOT NULL DEFAULT 0,
    gpu_usage_percent_max      DOUBLE PRECISION NOT NULL DEFAULT 0,
    gpu_memory_sample_count    BIGINT NOT NULL DEFAULT 0 CHECK (gpu_memory_sample_count >= 0),
    gpu_memory_usage_bytes_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
    gpu_memory_usage_bytes_max BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (evaluation_id, execution_number, component)
);

CREATE INDEX evaluation_resource_usage_observed_idx
    ON evaluation_resource_usage (last_observed_at DESC);

-- Portable, bounded telemetry derived from one execution's runtime and raw
-- artifacts. Raw files remain in object storage; this row makes factual totals
-- and handoff/completeness state queryable without reparsing those files.
CREATE TABLE evaluation_execution_telemetry (
    evaluation_id              TEXT NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    execution_number           INTEGER NOT NULL CHECK (execution_number >= 1),
    provisioning_started_at    TIMESTAMPTZ,
    running_started_at         TIMESTAMPTZ,
    terminal_at                TIMESTAMPTZ,
    terminal_status            TEXT CHECK (
        terminal_status IS NULL OR terminal_status IN ('succeeded', 'failed', 'cancelled')
    ),
    failure_phase              TEXT,
    input_tokens               BIGINT CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens              BIGINT CHECK (output_tokens IS NULL OR output_tokens >= 0),
    cached_tokens              BIGINT CHECK (cached_tokens IS NULL OR cached_tokens >= 0),
    cache_creation_tokens      BIGINT CHECK (
        cache_creation_tokens IS NULL OR cache_creation_tokens >= 0
    ),
    usage_source               TEXT NOT NULL DEFAULT 'unknown',
    turn_count                 BIGINT CHECK (turn_count IS NULL OR turn_count >= 0),
    tool_call_count            BIGINT CHECK (tool_call_count IS NULL OR tool_call_count >= 0),
    cost_usd                   DOUBLE PRECISION CHECK (cost_usd IS NULL OR cost_usd >= 0),
    cost_source                TEXT NOT NULL DEFAULT 'unknown' CHECK (
        cost_source IN ('provider', 'estimated', 'unknown')
    ),
    raw_artifact_refs          JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(raw_artifact_refs) = 'array'
    ),
    intake_experiment_ref      TEXT,
    intake_run_refs            JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
        jsonb_typeof(intake_run_refs) = 'array'
    ),
    intake_status              TEXT NOT NULL DEFAULT 'disabled' CHECK (
        intake_status IN ('disabled', 'pending', 'succeeded', 'failed', 'no_records')
    ),
    intake_expected_records    INTEGER CHECK (
        intake_expected_records IS NULL OR intake_expected_records >= 0
    ),
    intake_uploaded_records    INTEGER CHECK (
        intake_uploaded_records IS NULL OR intake_uploaded_records >= 0
    ),
    intake_error               TEXT,
    artifact_sync_status       TEXT NOT NULL DEFAULT 'pending' CHECK (
        artifact_sync_status IN ('pending', 'succeeded', 'failed')
    ),
    artifact_sync_file_count   INTEGER CHECK (
        artifact_sync_file_count IS NULL OR artifact_sync_file_count >= 0
    ),
    artifact_sync_error        TEXT,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluation_id, execution_number)
);

CREATE INDEX evaluation_execution_telemetry_terminal_idx
    ON evaluation_execution_telemetry (terminal_at DESC)
    WHERE terminal_at IS NOT NULL;

-- Durable per-evaluation runtime resources created by dispatch. Switchyard is
-- the first resource kind. Terminal evaluations leave resources in `draining`
-- until `drain_until`; workers later claim due rows and delete the external
-- Kubernetes resources. This avoids in-memory timers and survives worker
-- restarts.
CREATE TABLE evaluation_runtime_resources (
    id                  BIGSERIAL PRIMARY KEY,
    evaluation_id       TEXT NOT NULL REFERENCES evaluations (id) ON DELETE CASCADE,
    execution_number    INTEGER NOT NULL DEFAULT 1 CHECK (execution_number >= 1),
    kind                TEXT NOT NULL CHECK (kind IN ('switchyard')),
    status              TEXT NOT NULL CHECK (
        status IN ('provisioned', 'draining', 'deleting', 'deleted', 'delete_failed')
    ),
    profile_id          TEXT,
    namespace           TEXT NOT NULL,
    resource_name       TEXT NOT NULL,
    endpoint            TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    drain_until         TIMESTAMPTZ,
    teardown_claimed_at TIMESTAMPTZ,
    teardown_claimed_by TEXT,
    teardown_attempts   INTEGER NOT NULL DEFAULT 0,
    delete_error        TEXT,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evaluation_runtime_resources_evaluation_execution_kind_key
        UNIQUE (evaluation_id, execution_number, kind)
);

CREATE INDEX evaluation_runtime_resources_teardown_idx
    ON evaluation_runtime_resources (kind, status, drain_until)
    WHERE status IN ('draining', 'delete_failed');

-- A failed evaluation-runner pod may have already launched an external
-- sandbox. Preserve that execution's backend handle until a worker has
-- durably torn it down; only then may the next execution be queued.
CREATE TABLE evaluation_execution_cleanups (
    id                  BIGSERIAL PRIMARY KEY,
    evaluation_id       TEXT NOT NULL REFERENCES evaluations (id) ON DELETE CASCADE,
    execution_number    INTEGER NOT NULL CHECK (execution_number >= 1),
    runtime             TEXT NOT NULL,
    backend_handle      TEXT NOT NULL,
    dispatch_job_name   TEXT NOT NULL,
    failure_code        TEXT NOT NULL,
    failure_detail      TEXT NOT NULL,
    retry_after_cleanup BOOLEAN NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'deleting', 'delete_failed', 'deleted')
    ),
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    teardown_claimed_at TIMESTAMPTZ,
    teardown_claimed_by TEXT,
    teardown_attempts   INTEGER NOT NULL DEFAULT 0,
    delete_error        TEXT,
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT evaluation_execution_cleanups_execution_key
        UNIQUE (evaluation_id, execution_number)
);

CREATE INDEX evaluation_execution_cleanups_pending_idx
    ON evaluation_execution_cleanups (status, next_attempt_at, id)
    WHERE status IN ('pending', 'delete_failed');
