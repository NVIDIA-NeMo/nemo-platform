# Kubernetes Developer Guide

How to test, debug, and reproduce issues against NeMo Platform's Kubernetes environments.

**Linear ticket:** [AIRCORE-765](https://linear.app/nvidia/issue/AIRCORE-765/k8s-dev-testing-and-release-readiness-for-nmpdev)

## Environments

| Environment | URL | Deploys on |
| -- | -- | -- |
| Merge-to-main | https://nmp.dev.aire.nvidia.com/ | Every merge to `main` |
| Nightly snapshot | https://nemo-platform-nightly.dev.aire.nvidia.com | Nightly release build |

Both environments serve Studio at `/studio/` and expose the API at the root URL. The `/cluster-info` endpoint requires authentication:

```bash
curl -s -H "Authorization: Bearer $(nemo auth token)" \
  https://nmp.dev.aire.nvidia.com/cluster-info | jq .
# {"platform_version":"0.0.1","revision":"a3e68a67..."}
```

## One-time CLI setup

The NeMo CLI uses **contexts** (similar to `kubectl` contexts) to manage multiple environments. Set up all your contexts once and switch between them as needed. Config lives at `~/.config/nmp/config.yaml`.

### Create your contexts

Use `nemo config set --context <name> --base-url <url>` to create a new context. This creates the context, a dedicated cluster entry, and a user entry all at once. Creating a new context automatically makes it the active context.

```bash
# nmp.dev — merge-to-main K8s environment (OIDC auth required)
nemo config set --context tot --base-url https://nmp.dev.aire.nvidia.com

# nmp.dev nightly — nightly snapshot release (OIDC auth required)
nemo config set --context nightly --base-url https://nemo-platform-nightly.dev.aire.nvidia.com

# Local development — subprocess mode via `nemo services run`
nemo config set --context localdev --base-url http://localhost:8080

# Minikube — local K8s cluster
nemo config set --context minikube --base-url http://localhost:30080

# Dev-blue — GPU development box
nemo config set --context dev-blue --base-url https://<your-hostname>.dev.aire.nvidia.com
```

After running these, switch back to whichever context you want to use:

```bash
nemo config use-context localdev
```

### Switch between contexts

```bash
nemo config use-context tot        # nmp.dev merge-to-main
nemo config use-context nightly    # nmp.dev nightly snapshot
nemo config use-context localdev   # local subprocess
nemo config use-context minikube   # local K8s
nemo config use-context dev-blue   # GPU dev box
```

Check which context you're on:

```bash
nemo config current-context
```

View all contexts:

```bash
nemo config view --all-contexts
```

### Authenticate to nmp.dev

The `tot` and `nightly` contexts require OIDC authentication via NVIDIA SSO (Microsoft). The local contexts (`localdev`, `minikube`) don't require auth.

```bash
nemo config use-context tot
nemo auth login
```

This will:

1. Discover the OIDC configuration from the cluster
2. Give you a device code and URL (`https://login.microsoft.com/device`)
3. Open your browser — enter the code and sign in with your NVIDIA account
4. Save credentials including a refresh token for automatic renewal

Verify it worked:

```bash
nemo auth status
nemo workspaces list
```

You should see at least `default` and `system` workspaces.

### Workspaces

* **default** — general-purpose workspace, all users have write access. Use this for testing.
* **system** — platform-provided resources, read-only for users.

## Validated CLI commands

The following commands have been tested against nmp.dev (with auth) and minikube (without auth):

```bash
nemo workspaces list              # list workspaces
nemo workspaces get default       # get a specific workspace
nemo workspaces create <name>     # create a workspace
nemo plugins list                 # list loaded plugins
nemo inference models list        # list available models
nemo auth status                  # check auth state
nemo auth token                   # print bearer token (for SDK/curl use)
```

## Using the SDK against nmp.dev

If you need to use the Python SDK directly (e.g., in scripts or tests), you can construct a client using a CLI context or explicit token:

```python
from nemo_platform import NeMoPlatform

# Option 1: use a CLI context (recommended — handles token refresh)
client = NeMoPlatform(context_name="tot")

# Option 2: explicit base URL + token
import os
client = NeMoPlatform(
    base_url="https://nmp.dev.aire.nvidia.com",
    access_token=os.environ["NMP_ACCESS_TOKEN"],
)
```

To get a token for curl or other tools:

```bash
export NMP_ACCESS_TOKEN=$(nemo auth token)

# Note: on K8s, API routes use the /apis/ prefix (e.g., /apis/entities/v2/...)
# The SDK handles this automatically, but for raw curl you need the right paths.
curl -s -H "Authorization: Bearer $NMP_ACCESS_TOKEN" \
  https://nmp.dev.aire.nvidia.com/cluster-info | jq .
```

## Running e2e tests

### Against nmp.dev

The e2e test harness supports pointing at an already-running instance via `NMP_BASE_URL`. This skips local service startup and runs tests directly against the cluster.

Authentication can be provided via `NMP_ACCESS_TOKEN` (explicit token) or `NMP_CONTEXT_NAME` (reads credentials from CLI config):

```bash
# Option 1: explicit token
NMP_BASE_URL=https://nmp.dev.aire.nvidia.com \
  NMP_ACCESS_TOKEN=$(nemo auth token) \
  uv run --frozen pytest e2e --run-e2e -v

# Option 2: use a CLI context (reads token + refresh from config)
NMP_BASE_URL=https://nmp.dev.aire.nvidia.com \
  NMP_CONTEXT_NAME=tot \
  uv run --frozen pytest e2e --run-e2e -v
```

Note: you need to be in the appropriate context (or have recently run `nemo auth login`) for `nemo auth token` to return a valid token.

### Against minikube

No auth needed — just point at the local cluster:

```bash
NMP_BASE_URL=http://localhost:30080 uv run --frozen pytest e2e --run-e2e -v
```

### Known issues

**On nmp.dev (as of 2026-06-10):** 2 passed, 5 skipped, 52 failed.

* **RBAC blocks entity operations (403 Forbidden)** ([AIRCORE-771](https://linear.app/nvidia/issue/AIRCORE-771)): Entity create/update/delete returns 403 for authenticated users, in all workspaces including `default`. This blocks entity, inference, files, and most other tests. **Confirmed not a code bug** — entity CRUD works on minikube without auth. The 403 is specific to nmp.dev's RBAC configuration.
* **Health/Studio/cluster-info tests use** `sdk._client.get()`: These tests access the internal httpx client directly, which has an empty base URL when auth bootstrap is active.
* **Mock inference provider unavailable**: Tests relying on `mock.local` fail because the mock provider is subprocess-only.

**On minikube with locally built image (as of 2026-06-12):** 7 passed, 1 failed, 5 skipped.

* All entity, workspace, secret, and job execution tests pass
* `test_job_passing_data_between_steps` fails — persistent storage env var not set (pre-existing)
* Health endpoint tests fail (not routed through ingress — known routing gap)

**On minikube with stale GHCR image:** 9 passed, 9 failed — secrets tests fail due to API version skew, entity search filter has a minor mismatch. Use a locally built image to avoid this.

## Observability and debugging

Phil's team has observability flowing for both environments with more dashboards in progress.

**Dashboards:** TBD — need Grafana URL and access instructions from Phil's team.

**Logs:** TBD — need to confirm how devs access pod logs (Grafana/Loki? direct kubectl? dashboard only?).

**Deployment notifications:** Deployment status is included in the nightly release Slack update. Deployment failure messages currently go to ops channels — may be surfaced to devs in the future.

**Useful kubectl commands for debugging:**

```bash
# Check pod status
kubectl get pods

# Check logs for a crashing pod
kubectl logs <pod-name> --tail=50

# Attach a debug container to a running pod
POD=$(kubectl get pod | awk '/nemo-platform-api/{print $1; exit}') && \
  kubectl debug -it $POD --image=ghcr.io/astral-sh/uv:debian --target=nmp-api --profile=sysadmin -- bash

# Profile with py-spy
POD=$(kubectl get pod | awk '/nemo-platform-api/{print $1; exit}') && \
  kubectl debug -i $POD --image=ghcr.io/astral-sh/uv:debian --target=nmp-api --profile=sysadmin -- \
  sh -c 'uvx py-spy record --pid 1 --format speedscope --duration 5 -o /tmp/profile.json >/dev/null 2>&1 && cat /tmp/profile.json' | tee profile.json
```

## Reproducing failures locally

When you find a failure on nmp.dev, use the lightest environment that can reproduce it:

### 1. Subprocess mode

Fastest option. No containers. Good for API logic and plugin behavior issues. Won't catch container or networking issues.

```bash
nemo config use-context localdev
nemo services run
```

### 2. Docker backend

*TODO: document Docker backend setup*

### 3. Minikube / kind

Local single-node K8s cluster. Deploy using the same Helm chart used in production. Catches K8s-specific issues: ingress, service discovery, persistent volumes, RBAC.

The Dockerfiles and `docker-bake.hcl` live in the nemo-platform repo. The Helm chart and minikube setup scripts live in the **Platform-Deploy** repo ([NVIDIA-NeMo/Platform-Deploy](https://github.com/NVIDIA-NeMo/Platform-Deploy)).

#### Prerequisites

* Docker Desktop running with at least 6GB memory allocated (Settings > Resources > Memory)
* `minikube`, `kubectl`, `helm` installed
* Platform-Deploy repo cloned (e.g., `~/dev/Platform-Deploy`)
* `NGC_API_KEY` env var set (needed for Helm chart dependencies from NGC)
* GitHub CLI (`gh`) authenticated with `read:packages` scope (needed to pull base-of-base images from GHCR)

#### Setup

First, choose your image configuration:

```bash
# Option A: Build locally (for testing code changes)
NMP_REGISTRY=my-registry
NMP_TAG=local
NMP_PULL_POLICY=Never

# Option B: Pre-built from GHCR (faster, no local build)
# NMP_REGISTRY=ghcr.io/nvidia-nemo/platform
# NMP_TAG=latest
# NMP_PULL_POLICY=IfNotPresent

NMP_IMAGE=${NMP_REGISTRY}/nmp-api
```

Then run the setup:

```bash
# 1. Start minikube cluster
bash ~/dev/Platform-Deploy/e2e/k8s/scripts/setup_local_minikube_cpu.sh

# 2. Point Docker at minikube's daemon
eval $(minikube -p minikube-auth docker-env)

# 3. One-time GHCR auth (needed for pulling base images during build, or for Option B)
gh auth refresh -h github.com -s read:packages
gh auth token | docker login ghcr.io -u $(gh api user --jq .login) --password-stdin

# 4. Build images locally (skip this step if using Option B)
#    BUILD_ARCH: set to linux/arm64 on Apple Silicon, linux/amd64 on Intel
BUILD_ARCH=linux/arm64 \
  BAKE_REGISTRY_IMAGE=${NMP_REGISTRY} BAKE_TAG=${NMP_TAG} \
  docker buildx bake --progress=plain --load docker-cpu

# 5. Add the NGC Helm repo (needed for chart dependencies)
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia \
  --username='$oauthtoken' --password="${NGC_API_KEY}"

# 6. Build chart dependencies and install via Helm
(cd ~/dev/Platform-Deploy && \
  helm dependency build helm/platform && \
  helm upgrade -i nemo-platform helm/platform \
    -f e2e/k8s/values/minikube.yaml \
    --set "api.image.repository=${NMP_IMAGE}" \
    --set "api.image.tag=${NMP_TAG}" \
    --set "api.image.pullPolicy=${NMP_PULL_POLICY}" \
    --set "core.image.repository=${NMP_IMAGE}" \
    --set "core.image.tag=${NMP_TAG}" \
    --set "core.image.pullPolicy=${NMP_PULL_POLICY}" \
    --set "platformConfig.platform.image_registry=${NMP_REGISTRY}" \
    --set "platformConfig.platform.image_tag=${NMP_TAG}" \
    --timeout 10m \
    --wait)
```

Step 4 builds `nmp-api`, `nmp-core`, and `nmp-cpu-tasks` directly into minikube's Docker daemon. The Python base is built automatically as a dependency. Skip this step if using pre-built GHCR images (Option B).

The `platformConfig.platform.image_registry` and `image_tag` tell the platform which container images to use when launching job task pods. Without these, the platform defaults to `nvcr.io/nvidia/nemo-microservices` which won't match your local images.

Note: the GHCR `latest` image may be behind current source — the core controller may crash, secrets API may have version skew, and entity search filters may differ. Building locally avoids this.

#### Connect nemo CLI to minikube

```bash
nemo config use-context minikube
# minikube context points at http://localhost:30080 (no auth needed)
nemo workspaces list
```

#### Values files

Platform-Deploy provides several values files for different scenarios:

| File | Use case |
| -- | -- |
| `e2e/k8s/values/minikube.yaml` | Basic minikube (NIM operator, local storage, mock inference) |
| `e2e/k8s/values/minikube-auth.yaml` | Auth enabled, embedded policy decision point |
| `e2e/k8s/values/default.yaml` | E2E test defaults (NIM disabled, local-path storage) |
| `e2e/k8s/values/s3-rustfs.yaml` | S3-compatible storage via RustFS |

Important: use `minikube.yaml` (not `default.yaml`) for minikube — the default values reference `oci-nfs` storage class which doesn't exist on minikube and will cause PVC creation to fail.

#### Teardown

```bash
helm uninstall nemo-platform
kubectl delete pvc --all
# Or nuclear:
minikube -p minikube-auth delete
```

### 4. Dev-blue box

*TODO: document dev-blue setup and access*
