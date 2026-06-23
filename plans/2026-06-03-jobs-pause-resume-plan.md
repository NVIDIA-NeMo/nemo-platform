# Jobs Pause Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Docker-backed platform jobs pause and resume correctly so [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:264) reaches `paused` and then returns to `active` or `completed`.

**Architecture:** The API and dispatcher already model `pausing`, `paused`, and `resuming`, and there is unit/API coverage for the abstract lifecycle. The failing path is specific to the live Docker backend, so the plan is to reproduce the runtime error, add a Docker backend regression around stop/resume behavior, and then make the minimum state-machine or container-handling fix needed.

**Tech Stack:** `pytest`, NeMo SDK, Docker jobs backend, Jobs dispatcher, quickstart `nmp-api`, Python

---

## File Structure

**Files to inspect or modify:**
- Modify: [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:264)
- Modify: [services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py:960)
- Modify: [services/core/jobs/src/nmp/core/jobs/app/dispatcher.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/app/dispatcher.py:1105)
- Test: [services/core/jobs/tests/api/test_pause_resume.py](/Users/rsadler/src/nemo-platform/services/core/jobs/tests/api/test_pause_resume.py:1)
- Test: [services/core/jobs/tests/controllers/test_docker_backend.py](/Users/rsadler/src/nemo-platform/services/core/jobs/tests/controllers/test_docker_backend.py:1318)
- Test: `services/core/jobs/tests/integration/test_jobs_pause_resume_docker.py`

**Responsibilities:**
- `e2e/test_jobs.py`: external regression against quickstart.
- `dispatcher.py`: high-level job-step transition rules for pause/resume.
- `docker.py`: concrete pause/stop/container-state mapping behavior.
- `test_pause_resume.py`: API-level lifecycle expectations.
- `test_docker_backend.py`: backend-specific stop, paused, and resumed behavior.
- `test_jobs_pause_resume_docker.py`: narrower runtime regression for Docker-backed execution.

### Task 1: Capture the Exact Pause/Resume Runtime Failure

**Files:**
- Modify: [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:264)

- [ ] **Step 1: Improve the E2E failure output**

Update `test_job_pause_resume` so failures include:
- job `status_details`
- step `status_details`
- task `error_stack`
- current logs for the step task

Keep the assertions the same; only improve diagnostics.

- [ ] **Step 2: Run the single failing test**

Run:
```bash
env NMP_BASE_URL=http://localhost:8080 uv run --frozen pytest e2e/test_jobs.py::test_job_pause_resume -vv --run-e2e -s
```

Expected:
- FAIL
- output shows whether pause produced:
  - non-zero container exit
  - container missing during sync
  - dispatcher never seeing `paused`
  - resume returning to an invalid container state

- [ ] **Step 3: Note the concrete failure mode in the test**

Add a short inline comment documenting the current runtime symptom so future readers know what regression this test protects against.

- [ ] **Step 4: Commit diagnostics-only changes**

```bash
git add e2e/test_jobs.py
git commit -s -m "test: improve jobs pause resume diagnostics"
```

### Task 2: Add a Focused Docker Regression Test

**Files:**
- Create: `services/core/jobs/tests/integration/test_jobs_pause_resume_docker.py`
- Modify: [services/core/jobs/tests/controllers/test_docker_backend.py](/Users/rsadler/src/nemo-platform/services/core/jobs/tests/controllers/test_docker_backend.py:1318)

- [ ] **Step 1: Write a failing integration test for a real Docker-backed pause**

Create a jobs integration test that:
1. creates a long-running Docker-backed CPU job
2. waits for `active`
3. calls `pause`
4. waits for `paused`
5. calls `resume`
6. waits for `active` or `completed`

Use a long-running command that is pause-safe and deterministic. Avoid using a fast task that can complete before the state transition is observed.

- [ ] **Step 2: Run the integration test to verify it fails**

Run:
```bash
uv run --frozen pytest services/core/jobs/tests/integration/test_jobs_pause_resume_docker.py -vv
```

Expected:
- FAIL with the same state transition error as the E2E test

- [ ] **Step 3: Add one Docker backend unit test for the failing edge**

Extend [test_docker_backend.py](/Users/rsadler/src/nemo-platform/services/core/jobs/tests/controllers/test_docker_backend.py:1318) to cover the concrete failure from Task 1, for example:
- `container.stop()` during pausing yields `PAUSED` rather than `ERROR`
- a stopped container with pause intent maps to `PAUSED`
- resumed scheduling creates or reuses the right container state

- [ ] **Step 4: Run the focused backend/API tests**

Run:
```bash
uv run --frozen pytest services/core/jobs/tests/controllers/test_docker_backend.py -k paused -vv
uv run --frozen pytest services/core/jobs/tests/api/test_pause_resume.py -vv
```

Expected:
- the new unit test fails first
- API tests continue to pass unless the bug is higher up in dispatcher logic

- [ ] **Step 5: Commit the failing regression coverage**

```bash
git add services/core/jobs/tests/integration/test_jobs_pause_resume_docker.py services/core/jobs/tests/controllers/test_docker_backend.py
git commit -s -m "test: add docker pause resume regression coverage"
```

### Task 3: Fix Docker Pause/Resume State Handling

**Files:**
- Modify: [services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py:960)
- Modify: [services/core/jobs/src/nmp/core/jobs/app/dispatcher.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/app/dispatcher.py:1105) if needed

- [ ] **Step 1: Verify the intended Docker behavior**

Inspect:
- `sync_stop_container()`
- `map_docker_container_status_to_platform_status()`
- dispatcher `pause_job()` and `resume_job()`

Confirm whether Docker pause is implemented as:
- graceful container stop plus `PAUSED` state
- later resume by re-entering scheduling with `RESUMING`

Do not change API semantics unless the current Docker implementation truly contradicts the existing API tests.

- [ ] **Step 2: Implement the smallest correct fix**

Likely implementation areas:
- preserve pause intent across the stop/exited transition
- avoid mapping a paused container stop to generic `ERROR`
- ensure resume_job can find a paused step and move it back into schedulable state
- ensure the backend handles “container already gone because pause succeeded” as `PAUSED`, not `ERROR`

- [ ] **Step 3: Re-run focused tests**

Run:
```bash
uv run --frozen pytest services/core/jobs/tests/controllers/test_docker_backend.py -k paused -vv
uv run --frozen pytest services/core/jobs/tests/api/test_pause_resume.py -vv
uv run --frozen pytest services/core/jobs/tests/integration/test_jobs_pause_resume_docker.py -vv
env NMP_BASE_URL=http://localhost:8080 uv run --frozen pytest e2e/test_jobs.py::test_job_pause_resume -vv --run-e2e -s
```

Expected:
- all four pass

- [ ] **Step 4: Check cancel-vs-pause regressions**

Run:
```bash
env NMP_BASE_URL=http://localhost:8080 uv run --frozen pytest e2e/test_jobs.py::test_job_cancel_immediately e2e/test_jobs.py::test_job_cancel_once_active -vv --run-e2e -s
```

Expected:
- PASS
- no regression in cancellation behavior while fixing pause

- [ ] **Step 5: Commit the fix**

```bash
git add services/core/jobs/src/nmp/core/jobs/controllers/backends/docker.py services/core/jobs/src/nmp/core/jobs/app/dispatcher.py services/core/jobs/tests/controllers/test_docker_backend.py services/core/jobs/tests/integration/test_jobs_pause_resume_docker.py e2e/test_jobs.py
git commit -s -m "fix: support docker job pause and resume"
```

### Task 4: Final Validation

**Files:**
- Modify: [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:264) only if temporary diagnostics need cleanup

- [ ] **Step 1: Re-run the full non-auth jobs E2E suite**

Run:
```bash
env NMP_BASE_URL=http://localhost:8080 uv run --frozen pytest e2e/test_jobs.py -v --run-e2e
```

Expected:
- pause/resume passes
- cancel tests still pass

- [ ] **Step 2: Remove or trim any temporary debug-only assertions**

Retain useful failure context, but remove any excessive noise added solely for diagnosis.

- [ ] **Step 3: Commit cleanup**

```bash
git add e2e/test_jobs.py
git commit -s -m "test: clean up jobs pause resume e2e assertions"
```
