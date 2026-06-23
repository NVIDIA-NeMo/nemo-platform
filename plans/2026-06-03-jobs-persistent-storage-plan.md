# Jobs Persistent Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Docker-backed platform jobs preserve and share persistent storage correctly across sequential job steps so [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:121) passes reliably against quickstart.

**Architecture:** The failing path spans job-spec validation, Docker volume/init-container setup, and runtime task behavior. The safest fix is to first capture the exact task failure and then add one focused integration or controller-level regression test around the shared persistent-storage mount before changing Docker backend behavior.

**Tech Stack:** `pytest`, NeMo SDK, Docker jobs backend, Jobs dispatcher/controller, quickstart `nmp-api`, Python

---

## File Structure

**Files to inspect or modify:**
- Modify: [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:121)
- Modify: [services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py:426)
- Modify: [services/core/jobs/src/nmp/core/jobs/api/v2/jobs/endpoints.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/api/v2/jobs/endpoints.py:75)
- Modify: [services/core/jobs/src/nmp/core/jobs/app/schemas.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/app/schemas.py:79)
- Test: [services/core/jobs/tests/controllers/test_docker_backend.py](/Users/rsadler/src/nemo-platform/services/core/jobs/tests/controllers/test_docker_backend.py:1211)
- Test: `services/core/jobs/tests/integration/test_jobs_persistent_storage.py`

**Responsibilities:**
- `e2e/test_jobs.py`: external regression proving end-to-end behavior across real Docker quickstart.
- `docker.py`: volume creation, mount wiring, job init container, cleanup, and runtime state transitions for Docker jobs.
- `endpoints.py` and `schemas.py`: job-spec validation and feature gating for persistent storage.
- `test_docker_backend.py`: backend unit coverage for mount/label/config behavior.
- `test_jobs_persistent_storage.py`: a narrower live-service regression that proves the platform contract independently of the broad E2E suite.

### Task 1: Capture the Actual Persistent-Storage Failure

**Files:**
- Modify: [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:121)

- [ ] **Step 1: Tighten the failing E2E assertion to surface task error details**

Update `test_job_passing_data_between_steps` so that when the job status is not `completed`, the assertion includes:
- job `status_details`
- job `error_details`
- task `error_stack`
- job logs

The change should follow the same pattern already used for job diagnostics in the old `Platform-Deploy` suite: fail with actionable details, not just `status == error`.

- [ ] **Step 2: Run the single failing test and capture the concrete backend error**

Run:
```bash
env NMP_BASE_URL=http://localhost:8080 uv run --frozen pytest e2e/test_jobs.py::test_job_passing_data_between_steps -vv --run-e2e -s
```

Expected:
- test fails
- output contains the precise runtime error from the second step or from job init/mount setup

- [ ] **Step 3: Record the failure mode in the test comment**

Add a short comment in `test_job_passing_data_between_steps` explaining the current failure shape, for example:
- missing file in mounted persistent path
- mount path not shared across steps
- init container path mismatch

- [ ] **Step 4: Commit the diagnostics-only change**

```bash
git add e2e/test_jobs.py
git commit -s -m "test: improve jobs persistent storage diagnostics"
```

### Task 2: Add a Narrow Regression Test Below E2E

**Files:**
- Create: `services/core/jobs/tests/integration/test_jobs_persistent_storage.py`
- Test: `services/core/jobs/tests/integration/test_jobs_persistent_storage.py`

- [ ] **Step 1: Write the failing integration test**

Add a live service integration test that:
1. creates a two-step platform job
2. writes `data.txt` in step 1 using `NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH`
3. reads the same file in step 2
4. asserts final job status is `completed`

Use the same job shape as [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:121), but keep the test local to the jobs service so failure analysis is faster than full quickstart E2E.

- [ ] **Step 2: Run the new integration test to verify it fails**

Run:
```bash
uv run --frozen pytest services/core/jobs/tests/integration/test_jobs_persistent_storage.py -vv
```

Expected:
- FAIL with the same storage-sharing symptom seen in E2E

- [ ] **Step 3: Add one Docker backend unit test for mount intent**

In [test_docker_backend.py](/Users/rsadler/src/nemo-platform/services/core/jobs/tests/controllers/test_docker_backend.py:1211), add a failing unit test that asserts:
- both steps targeting the same job get the same shared job volume name
- the persistent mount target uses the explicit `NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH`
- the mount includes the expected subpath `jobs/<workspace>/<job>`

- [ ] **Step 4: Run the focused backend unit tests**

Run:
```bash
uv run --frozen pytest services/core/jobs/tests/controllers/test_docker_backend.py -k persistent_storage -vv
```

Expected:
- new unit test fails before implementation changes

- [ ] **Step 5: Commit the failing test additions**

```bash
git add services/core/jobs/tests/integration/test_jobs_persistent_storage.py services/core/jobs/tests/controllers/test_docker_backend.py
git commit -s -m "test: add jobs persistent storage regression coverage"
```

### Task 3: Fix Docker Persistent-Storage Wiring

**Files:**
- Modify: [services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py:426)
- Modify: [services/core/jobs/src/nmp/core/jobs/app/schemas.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/app/schemas.py:79)

- [ ] **Step 1: Verify whether the persistent storage contract is mount-path based or env-var based**

Inspect:
- `schedule_single_container()`
- `ensure_job_storage()`
- `get_mounts()`

Confirm that the init container prepares `/job-vol/jobs/<workspace>/<job>` while the runtime mount targets the user-requested path (for example `/mnt/persistent_storage`) with Docker `Subpath`.

If that contract is already correct, do not redesign it. Limit the fix to the broken edge.

- [ ] **Step 2: Implement the minimal backend change**

Possible implementation sites, depending on the failure captured in Task 1:
- normalize the persistent mount target before volume creation
- ensure the shared volume subpath is created before the second step runs
- correct `VolumeOptions["Subpath"]` usage
- preserve mount/env consistency when `NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH` is overridden

Do not broaden scope into Kubernetes or subprocess backends.

- [ ] **Step 3: Re-run the focused tests**

Run:
```bash
uv run --frozen pytest services/core/jobs/tests/controllers/test_docker_backend.py -k persistent_storage -vv
uv run --frozen pytest services/core/jobs/tests/integration/test_jobs_persistent_storage.py -vv
env NMP_BASE_URL=http://localhost:8080 uv run --frozen pytest e2e/test_jobs.py::test_job_passing_data_between_steps -vv --run-e2e -s
```

Expected:
- all three pass

- [ ] **Step 4: Check for cleanup regressions**

Run:
```bash
uv run --frozen pytest services/core/jobs/tests/controllers/test_docker_backend.py -k cleanup -vv
```

Expected:
- PASS
- no new failures in persistent-storage cleanup logic

- [ ] **Step 5: Commit the fix**

```bash
git add services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py services/core/jobs/src/nmp/core/jobs/app/schemas.py services/core/jobs/tests/controllers/test_docker_backend.py services/core/jobs/tests/integration/test_jobs_persistent_storage.py e2e/test_jobs.py
git commit -s -m "fix: share persistent storage across docker job steps"
```

### Task 4: Final Validation

**Files:**
- Modify: [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:121) if diagnostics added in Task 1 can now be simplified

- [ ] **Step 1: Re-run the full non-auth jobs E2E suite**

Run:
```bash
env NMP_BASE_URL=http://localhost:8080 uv run --frozen pytest e2e/test_jobs.py -v --run-e2e
```

Expected:
- persistent-storage test passes
- no regressions in the previously passing jobs tests

- [ ] **Step 2: Simplify temporary diagnostics if they are no longer needed**

If Task 1 added very noisy debug-only assertions or comments, keep the useful failure context but remove excess noise.

- [ ] **Step 3: Commit cleanup**

```bash
git add e2e/test_jobs.py
git commit -s -m "test: clean up jobs persistent storage e2e assertions"
```
