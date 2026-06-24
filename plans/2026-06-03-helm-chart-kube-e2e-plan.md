# Helm Chart And Kubernetes E2E Revival Plan

**Goal:** Bring the archived NeMo Platform Helm chart from `/Users/rsadler/src/Platform-Deploy` into this repo, make it installable in a minimal local Kubernetes setup, and restore a small but real Kubernetes-backed E2E path so we can iterate from a working baseline.

**Current State:**
- The archived deployment repo contains a full chart at `/Users/rsadler/src/Platform-Deploy/helm/platform` plus helper scripts and `e2e/k8s` values.
- This repo still advertises Kubernetes E2E entrypoints in [Makefile](/Users/rsadler/src/nemo-platform/Makefile:438), but the current harness in [e2e/conftest.py](/Users/rsadler/src/nemo-platform/e2e/conftest.py:98) only implements the subprocess backend and explicitly says Docker/Kubernetes selection is not built yet.
- There is no live Helm chart checked into this repo today under `deploy/helm` or `helm/`.
- The current image topology is repo-native and should remain authoritative: `nmp-api`, `nmp-core`, and `nmp-cpu-tasks` are built from [docker-bake.hcl](/Users/rsadler/src/nemo-platform/docker-bake.hcl:34).

**Non-Goals For The First Pass:**
- Do not revive every archived deploy feature up front.
- Do not block the import on GPU, auth, ingress, observability, OpenShift, or cloud-specific policy support.
- Do not treat the old `Platform-Deploy` layout as authoritative where it conflicts with the current monorepo.

---

## File Structure

**Primary files and directories to add or modify:**
- Add: `deploy/helm/platform/**` or `helm/platform/**` after choosing the long-term chart location
- Add: `e2e/k8s/values/minimal-kind.yaml`
- Add: `e2e/k8s/scripts/install_nmp_k8s_minimal.sh`
- Add: `e2e/k8s/scripts/build_and_load_images.sh`
- Add: `e2e/k8s/scripts/wait_for_api.sh`
- Modify: [Makefile](/Users/rsadler/src/nemo-platform/Makefile:438)
- Modify: [e2e/conftest.py](/Users/rsadler/src/nemo-platform/e2e/conftest.py:98)
- Modify: [TESTING.md](/Users/rsadler/src/nemo-platform/TESTING.md:114)
- Modify: `.github/workflows/ci.yaml` or the relevant kube E2E workflow only after the local path is proven

**Supporting sources to port selectively from the archive:**
- `/Users/rsadler/src/Platform-Deploy/helm/platform/**`
- `/Users/rsadler/src/Platform-Deploy/e2e/k8s/scripts/install_nmp_e2e.sh`
- `/Users/rsadler/src/Platform-Deploy/e2e/k8s/scripts/wait_for_api.sh`
- `/Users/rsadler/src/Platform-Deploy/e2e/k8s/values/default.yaml`
- `/Users/rsadler/src/Platform-Deploy/e2e/k8s/values/minikube.yaml`

---

## Task 1: Decide The Import Boundary And Target Layout

- [ ] **Step 1: Pick the chart home in this repo**

Choose one canonical destination before copying files:
- `deploy/helm/platform/` if we want a deploy-artifacts home that matches the older docs language
- `helm/platform/` if we want the shortest path from the archived repo and the existing helper scripts

Recommendation:
- Prefer `deploy/helm/platform/` if the team wants clear separation between product source and deploy packaging.
- Prefer `helm/platform/` if the priority is fastest low-risk import with minimal path rewriting.

Whichever path is chosen, update all future scripts and docs to use only that path.

- [ ] **Step 2: Inventory what is essential for a minimal chart install**

Split the archive into:
- required now: chart templates, values, helper templates, chart README, dependency metadata
- defer: observability stack, CI-only values, OpenShift route tuning, NCCL test hooks, cloud-specific Kyverno examples, release publishing scripts

The first import should preserve enough to install:
- API service
- core/controller service
- embedded Postgres
- shared storage PVC
- platform config map and seed job if still required for a healthy API

- [ ] **Step 3: Reconcile archived names with the current repo**

Before copying, identify mismatches in:
- image names
- chart value names
- service names
- config rendering expectations
- required secrets

Known item to resolve early:
- the archived install scripts set both `api.image.repository` and `core.image.repository` to `.../nmp-api`, but the current repo also builds `nmp-core` in [docker-bake.hcl](/Users/rsadler/src/nemo-platform/docker-bake.hcl:45). Decide whether the chart should run a separate `nmp-core` image now or intentionally keep using `nmp-api` for both components in the minimal phase.

- [ ] **Step 4: Commit the import decision document**

Create a short design note in this plan or a sibling doc that records:
- chosen chart location
- import scope
- intentional deferrals
- image topology decision for minimal Kubernetes bring-up

---

## Task 2: Port The Chart Into This Repo Without Broad Refactoring

- [ ] **Step 1: Copy the chart skeleton and keep it mechanically close to the archive**

Bring in:
- `Chart.yaml`
- `values.yaml`
- `templates/**`
- `files/**`
- `README.md`
- any helm-docs template if we intend to keep generated docs current

Avoid mixing cleanup with the initial copy. The first commit should make the provenance obvious.

- [ ] **Step 2: Remove or disable obviously non-minimal features in values, not templates, where possible**

The minimal import should default off for:
- `k8s-nim-operator`
- ingress
- auth
- ServiceMonitor / observability extras
- cloud-specific networking policies
- GPU-only hooks and chart tests

Prefer values-based disablement first. Template deletion should happen only if a feature is clearly dead and blocking comprehension.

- [ ] **Step 3: Validate the chart renders against minimal local values**

Run:
```bash
helm dependency build <chart-dir>
helm template nemo-platform <chart-dir> -f e2e/k8s/values/minimal-kind.yaml
```

Expected:
- render succeeds
- no unresolved template functions
- only the minimal resources appear

- [ ] **Step 4: Add a chart-focused smoke check**

Add a repeatable render/lint target, for example:
- `make helm-lint`
- `make helm-template-minimal`

The goal is to make chart iteration cheap before any cluster install.

---

## Task 3: Create A Minimal Local Kubernetes Install Path

- [ ] **Step 1: Standardize on one local cluster target**

Use `kind` first unless there is a hard blocker in storage or ingress behavior.

Reason:
- the repo already references a kind helper in older docs
- kind is easier to automate than minikube
- the first milestone is CPU-only smoke coverage, not GPU or ingress fidelity

If storage semantics force minikube for the first pass, record that explicitly and keep kind as the follow-up target.

- [ ] **Step 2: Add a minimal values file just for local smoke**

Create `e2e/k8s/values/minimal-kind.yaml` with only the overrides needed for a local cluster:
- disable `k8s-nim-operator`
- disable ingress
- disable auth
- use embedded Postgres
- use the cluster default storage class or a known kind-friendly class
- set `platformConfig.platform.runtime: kubernetes` if the chart does not already do that
- point platform image registry and tag overrides at locally built images

Do not start from the archived `default.yaml` unchanged; it assumes NVIDIA internal registries and storage classes.

- [ ] **Step 3: Add a build-and-load script for local images**

Create a thin script that:
1. builds `nmp-api`, `nmp-core`, and `nmp-cpu-tasks`
2. tags them consistently for the cluster run
3. loads them into kind

Keep the contract simple:
- `NMP_E2E_REGISTRY`
- `NMP_E2E_TAG`
- maybe `KIND_CLUSTER_NAME`

The script should use the repo’s current bake targets rather than reproducing the archived repo’s image logic.

- [ ] **Step 4: Add a minimal install script**

Create `e2e/k8s/scripts/install_nmp_k8s_minimal.sh` that:
1. verifies `kubectl`, `helm`, and cluster access
2. runs `helm dependency build`
3. installs or upgrades the chart with the minimal values file
4. waits for readiness
5. prints targeted diagnostics on failure

Keep it local-first:
- no NGC auth unless a remaining dependency truly requires it
- no cloud-provider assumptions
- no internal registry defaults

- [ ] **Step 5: Verify the API really comes up**

Add a readiness check that proves more than pod existence:
- `kubectl wait` for deployments/statefulsets
- then poll `/health/ready` or `/cluster-info` through port-forward or a local service URL

This should become the contract the E2E harness relies on.

---

## Task 4: Reintroduce A Kubernetes Backend To The E2E Harness

- [ ] **Step 1: Replace the placeholder backend comment with real backend selection**

Extend [e2e/conftest.py](/Users/rsadler/src/nemo-platform/e2e/conftest.py:98) so the session fixture can choose among:
- subprocess
- docker
- kubernetes

The returned interface should stay the same:
- a base URL for the SDK

- [ ] **Step 2: Implement the smallest useful Kubernetes mode**

The first Kubernetes mode does not need full lifecycle automation inside pytest.

A practical first cut:
- require `NMP_BASE_URL` or `NMP_E2E_CLUSTER_URL`
- assume the chart is already installed by the helper script
- connect the SDK to that external URL

This gets kube E2E running again without hiding cluster setup inside pytest.

- [ ] **Step 3: Make the CLI flags and docs match reality**

Today `Makefile` calls `pytest e2e --kubernetes`, but [e2e/conftest.py](/Users/rsadler/src/nemo-platform/e2e/conftest.py:114) does not register that option.

Add:
- `pytest_addoption` support for `--kubernetes`
- optional `--cluster-url`
- clear skip or error messages when required env vars are missing

- [ ] **Step 4: Keep the first kube test set intentionally small**

Do not aim for the whole suite immediately.

Start by running only:
- [e2e/test_smoke.py](/Users/rsadler/src/nemo-platform/e2e/test_smoke.py:1)
- one low-risk jobs test if job execution works in the minimal cluster

If jobs are not ready on the first pass, restore kube smoke coverage first and add jobs in the next milestone.

---

## Task 5: Make Kubernetes E2E Runnable Via Repo Commands

- [ ] **Step 1: Fix `Makefile` targets so they map to implemented behavior**

Bring `test-e2e-kubernetes` into alignment with the real harness.

For the first working version, the flow should be explicit:
1. build and load images
2. install chart
3. run selected tests against `NMP_E2E_CLUSTER_URL`

If needed, add separate helpers instead of pretending `pytest --kubernetes` does everything by itself.

- [ ] **Step 2: Add a narrow make target for the first milestone**

Add one minimal target, for example:
```bash
make test-e2e-kubernetes-smoke
```

It should run only the subset we know how to support reliably.

Defer `auth`, `gpu`, `kai-scheduler`, and `customizer` variants until the base path is real again.

- [ ] **Step 3: Update `TESTING.md`**

Document the exact local Kubernetes flow, including:
- prerequisites
- cluster choice
- image build and load step
- Helm install step
- smoke test command
- known unsupported variants

This is important because [TESTING.md](/Users/rsadler/src/nemo-platform/TESTING.md:114) currently describes root-level E2E as subprocess-based and does not explain the Kubernetes mode at all.

---

## Task 6: Expand From Smoke To Minimal Jobs Coverage

- [ ] **Step 1: Prove one real SDK workflow on Kubernetes**

After smoke passes, choose one representative operation:
- create a workspace
- run a trivial CPU job using `nmp-cpu-tasks`
- fetch logs or completion state

This is the first meaningful kube E2E milestone because it validates:
- API reachability
- controller wiring
- image resolution
- shared config for launched tasks

- [ ] **Step 2: Add or adapt one kube-safe jobs test**

Prefer a very small test rather than turning on all of [e2e/test_jobs.py](/Users/rsadler/src/nemo-platform/e2e/test_jobs.py:1).

If the existing suite assumes subprocess or Docker specifics, add a separate minimal kube smoke test instead of forcing conditionals through every test immediately.

- [ ] **Step 3: Capture the next blockers explicitly**

Once one jobs path works, classify remaining failures into:
- chart gaps
- runtime config gaps
- storage or PVC semantics
- image distribution issues
- auth or ingress dependencies

That list should drive the next iteration rather than broad speculative porting.

---

## Task 7: Only Then Wire It Back Into CI

- [ ] **Step 1: Keep CI out of the critical path until the local flow is stable**

Do not add CI before a contributor can run the local smoke path twice in a row successfully.

- [ ] **Step 2: Add a single CPU-only Kubernetes smoke job**

Once local is stable, add one CI job that:
- provisions the cluster
- builds or pulls the required images
- installs the chart
- runs the Kubernetes smoke subset
- uploads pod logs and Helm values on failure

- [ ] **Step 3: Gate broader kube suites behind follow-up work**

Keep these out of the first CI restoration:
- auth
- gpu
- kai-scheduler
- customizer
- cloud storage scenarios

---

## Recommended Execution Order

1. Choose chart location and import boundary.
2. Copy the chart with minimal changes.
3. Create `minimal-kind.yaml` and get `helm template` green.
4. Build and load local images.
5. Install the chart into a local cluster and verify `/health/ready`.
6. Implement `pytest --kubernetes` as an external-base-URL backend.
7. Restore one smoke target in `Makefile`.
8. Add one jobs-based kube E2E only after smoke is stable.
9. Reintroduce CI coverage last.

---

## Exit Criteria For The First Milestone

- [ ] The chart lives in this repo in one canonical location.
- [ ] `helm template` succeeds with a repo-owned minimal local values file.
- [ ] A local kind or minikube cluster can install the chart from this repo using repo-owned scripts.
- [ ] The platform API becomes healthy after install.
- [ ] `make test-e2e-kubernetes-smoke` passes against that cluster.
- [ ] At least one Kubernetes-backed E2E test is running again from this repo.

## Follow-Up Milestones

- [ ] Add a minimal jobs-on-kubernetes E2E.
- [ ] Re-enable broader Kubernetes variants in `Makefile`.
- [ ] Add CI smoke coverage.
- [ ] Evaluate which archived chart features should be deleted instead of maintained.
