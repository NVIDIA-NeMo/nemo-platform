# AIRCORE-757 Smoke Results

Share-only evidence for AIRCORE-757 k8s backend smoke testing. This branch is
for communicating ephemeral validation results and is not intended to merge.

## Code Under Test

- Branch: `757-smoke-epilogue/tbray`
- Base: `main`
- Commit: `649df518bcf0443f9391f01a3e60cc5c42d26c49`
- Worktree: `/Users/tbray/dev/aire/microservices/nmp-757-smoke`

## Tier B: Local Kind Integration Smoke

Status: PASS

Cluster:

- Context: `kind-kind`
- Namespace: `default`
- Kubernetes version: `v1.32.2`
- Node: `kind-control-plane`
- Storage class: kind local-path default (`WaitForFirstConsumer`)

Commands:

```bash
kubectl --context kind-kind config view --minify --raw > /tmp/nmp-757-kind-kubeconfig.yaml
export KUBECONFIG=/tmp/nmp-757-kind-kubeconfig.yaml
uv run pytest plugins/nemo-deployments/tests/integration/backends/k8s -v
uv run pytest plugins/nemo-deployments/tests/integration/test_reconcile_k8s.py -v
```

Results:

```text
plugins/nemo-deployments/tests/integration/backends/k8s/test_k8s_backend.py
5 passed in 7.58s

plugins/nemo-deployments/tests/integration/test_reconcile_k8s.py
1 passed in 3.31s
```

Coverage exercised:

- PVC create/read/delete lifecycle.
- Finite `batch/v1.Job` success path.
- ConfigMap mount round trip.
- `apps/v1.Deployment` plus `v1.Service` readiness path.
- Label-gated delete rejection for foreign resources.
- Reconciler prerequisite chain against the real k8s backend.

Note: the first run used the ambient merged `KUBECONFIG`:

```text
/Users/tbray/.kube/kubeconfig-nemollm.yaml:/Users/tbray/.kube/config
```

That caused the Python Kubernetes client availability gate to hit a Teleport
context and skip all tests with `No reachable Kubernetes cluster`, even though
`kubectl` was on `kind-kind`. Re-running with the explicit minified kind
kubeconfig above produced the passing result.

## Tier C: Dev-Blue Manual Smoke

Status: PASS, with operational findings noted below

### Infra

| Item | Value |
|------|-------|
| Cluster | `nemo-dev-blue` |
| Namespace | `tbray-dev` |
| Pod | `nemo-platform` @ `10.244.5.139` |
| Platform | READY (`deployments` service + controller enabled) |
| Config | `/work/nmp-config.yaml` in pod |
| RBAC applied | `nemo-models-vllm` (vLLM path) |
| Supplemental RBAC | `nemo-models-vllm`, `nemo-deployments-smoke` |

### Mission leg (deployments-plugin direct) — attempt 1

Script: HTTP API against `/apis/deployments/v2/workspaces/default/...`

| Step | Resource | Result | Notes |
|------|----------|--------|-------|
| Volume | `smoke-data` | PENDING | PVC `dep-vol-default-smoke-data-79140390` — `WaitForFirstConsumer` on `oci-bv` (expected until mounted) |
| Job + ConfigMap | `smoke-cm-job` | **FAILED** | `403 Forbidden`: `system:serviceaccount:tbray-dev:default` cannot create `configmaps` |
| Deployment + Service | `smoke-http-svc` | **STARTING** (stuck) | K8s objects created; pod `ImageInspectError` — cri-o short-name enforcement rejects `nginx:alpine` |

Evidence:

- `dev-blue/mission-leg-api.json` — API snapshots after attempt 1
- `dev-blue/deployment-smoke-http-svc.yaml`, `service-smoke-http-svc.yaml`, `pvc-smoke-data.yaml`
- `dev-blue/describe-smoke-http-pod.txt` — `Failed to inspect image "": short name mode is enforcing, but image name nginx:alpine returns ambiguous list`

Retry plan (`dev-blue/mission-leg.py`):

1. User applies `dev-blue/rbac-nemo-deployments-smoke.yaml` (out-of-band; agent cannot mutate cluster RBAC).
2. Re-run mission script with FQ images: `docker.io/library/nginx:alpine`, `docker.io/library/alpine:3.20`.

### Mission leg (deployments-plugin direct) — final pass

Status: PASS

Script: `dev-blue/mission-leg.py`

Resources:

- Volume: `smoke4-data`
- ConfigMap job: `smoke4-cm-job`
- HTTP deployment/service: `smoke4-http-svc`

Results:

```text
deployments/smoke4-cm-job status=SUCCEEDED
deployments/smoke4-http-svc status=READY
```

The ConfigMap-mounted job printed:

```text
hello-from-configmap
```

Evidence:

- `dev-blue/mission-leg-api-pass.json`
- `dev-blue/mission-leg-k8s-after-pass.yaml`
- `dev-blue/mission-leg-cm-job.log`

Notes:

- The deployment API reports finite job success as `SUCCEEDED`, not `READY`.
- JSON payloads must use API field names (`config_files`, `restart_policy`, `backend_config`); camelCase fields were ignored.

### vLLM/GPU reference leg

Status: PASS

Per `docs/run-inference/tutorials/deploy-models.mdx` § Deploy with vLLM (Qwen3-1.7B, `engine: vllm`, `gpu: 1`).

Resources:

- Fileset: `aircore757b-qwen3-1-7b`
- Model: `aircore757b-qwen3-1-7b`
- Deployment config: `aircore757b-qwen3-vllm-config`
- Deployment/provider: `aircore757b-qwen3-vllm-deployment`

Results:

```text
deployment status=READY
chat object=chat.completion
model=default/aircore757b-qwen3-1-7b
system_fingerprint=vllm-0.22.1-d56dddd7
```

Evidence:

- `dev-blue/vllm-leg.py`
- `dev-blue/vllm-leg.log`
- `dev-blue/vllm-leg-api.json`
- `dev-blue/vllm-serving-pod.log`
- `dev-blue/vllm-serving-pod-describe.txt`
- `dev-blue/vllm-k8s-aircore757b-final.yaml`

Prerequisites used:

- GPU nodes available (8× GPU workers)
- `nemo-models-vllm` Role/RoleBinding
- Secret `nemo-models-files-token` present for model-file access

Operational findings:

- The generated files CLI failed for fileset creation:

  ```text
  Unexpected error: 'FilesResource' object has no attribute 'filesets'
  ```

  The final pass used direct HTTP `POST /apis/files/v2/workspaces/default/filesets`.

- The model PVC briefly hit a cross-node RWO attach delay:

  ```text
  Multi-Attach error for volume "...": Volume is already exclusively attached to one node and can't be attached to another
  ```

  The controller eventually progressed after attach succeeded, and the deployment reached `READY`.

### Cleanup

Status: COMPLETE

After evidence capture, smoke-created deployments, model resources, PVCs, jobs,
services, configmaps, and pods were deleted. A follow-up delete was required for
the vLLM deployment configs because deployment deletion is asynchronous.

Final namespace check:

```text
kubectl --context nemo-dev-blue -n tbray-dev get pod,job,deploy,pvc,svc,configmap -o wide | rg 'aircore757|smoke|NAME'

NAME                READY   STATUS    RESTARTS   AGE     IP             NODE           NOMINATED NODE   READINESS GATES
NAME                                             STATUS    VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE    VOLUMEMODE
NAME                           DATA   AGE
```

