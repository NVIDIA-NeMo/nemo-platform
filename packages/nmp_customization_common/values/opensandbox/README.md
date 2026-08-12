# OpenSandbox values — nemo-dev-blue (OCI)

Target cluster: `nv-prd-nemo.teleport.sh-nemo-dev-blue`  
Prerequisite: `RuntimeClass/kata-qemu` installed via `install-kata-qemu.sh` / `kata-values.yaml`.

These values are the source of truth for the nemo-dev-blue layout until they are
promoted into `k8s/helm/`.

## Why two server releases

OpenSandbox `[secure_runtime]` is **server-global**. One server cannot mix `crun` and `kata-qemu` sandboxes. This layout therefore deploys:

| Component | Release | Workload NS | Isolation |
|-----------|---------|-------------|-----------|
| Controller + CRDs | `opensandbox-controller` | — | shared |
| Server (shared-kernel) | `opensandbox-server-crun` | `nmp-temp1` | cluster default (`crun`) |
| Server (Kata QEMU) | `opensandbox-server-kata` | `nmp-temp1` | `runtimeClassName: kata-qemu` |

Both profiles create BatchSandbox pods in the shared NMP temp workspace namespace
`nmp-temp1`. Isolation is still via RuntimeClass / BatchSandbox template labels,
not separate namespaces. Control plane (Deployments, Secrets, template
ConfigMaps, Services) stays in `opensandbox-system`.

Platform / Gym clients pick a profile by Service DNS + API key.

## Files

| File | Role |
|------|------|
| `opensandbox-controller.yaml` | Shared controller (CRI-O: empty `containerdSocketPath`) |
| `opensandbox-server-crun.yaml` | Shared-kernel server values |
| `opensandbox-server-kata-qemu.yaml` | Kata server values + `[secure_runtime]` |
| `batchsandbox-template-crun.yaml` | ConfigMap — soft-avoid GPU/kata nodes |
| `batchsandbox-template-kata-qemu.yaml` | ConfigMap — pin to kata-labeled H100 nodes |
| `install.sh` | Apply namespaces, Secrets, ConfigMaps, Helm releases |
| `verify/crun.sh` | Smoke-test shared-kernel / crun profile |
| `verify/kata-qemu.sh` | Smoke-test kata-qemu profile |
| `verify/all.sh` | Run both verifiers |
| `verify/lib.sh` | Shared helpers (sourced by verify/*.sh) |

## API keys (Kubernetes Secrets)

`api_key` is **not** in Helm values / ConfigMap. Each server reads
`OPENSANDBOX_SERVER_API_KEY` from a Secret via `server.env`:

| Profile | Secret | Key |
|---------|--------|-----|
| crun | `opensandbox-server-crun-api-key` | `api-key` |
| kata-qemu | `opensandbox-server-kata-api-key` | `api-key` |

`install.sh` creates them if missing (random hex, or `CRUN_API_KEY` /
`KATA_API_KEY` env vars). Re-runs keep existing Secrets.

## Image pull credentials (sandbox pods)

Sandbox pods are built by the OpenSandbox server from `batchsandbox-template-*.yaml`, 
not by the jobs controller, so `platformConfig.jobs.executor_defaults.*.image_pull_secrets` 
does not apply, and the chart's top-level `imagePullSecrets` covers only api/core pods.
Both templates therefore carry it directly:

```yaml
imagePullSecrets:
  - name: nvcrimagepullsecret
```

**The Secret must exist in the sandbox namespace** — `[kubernetes] namespace` in the server
values (`nmp-temp1` here), not `opensandbox-system`. `imagePullSecrets` is a namespace-local
reference.

```bash
kubectl -n nmp-temp1 get secret nvcrimagepullsecret     # must exist
```

Rename the Secret in both templates if your cluster uses a different one.

**Failure mode if this is missing:** the sandbox pod goes `ErrImagePull`, the server abandons
it on `KUBERNETES::POD_READY_TIMEOUT`, and the *training* log shows only
`SandboxInternalException('Network connectivity error: ')` wrapping an `httpcore.ReadTimeout` —
which points at the network, not at credentials. Check the server log for the real reason:

```bash
kubectl -n opensandbox-system logs deploy/opensandbox-server-crun --tail=300 | grep -iE "state:|reason="
```

A ServiceAccount-level patch is the quick unblock without touching this template:

```bash
kubectl -n nmp-temp1 patch serviceaccount default \
  -p '{"imagePullSecrets":[{"name":"nvcrimagepullsecret"}]}'
```

## Node pinning (kata)

Matches live `RuntimeClass/kata-qemu` scheduling on this cluster:

```yaml
nodeSelector:
  katacontainers.io/kata-runtime: "true"
  node.kubernetes.io/instance-type: BM.GPU.H100.8
  feature.node.kubernetes.io/cpu-cpuid.VMX: "true"
```

Currently two Ready workers carry `katacontainers.io/kata-runtime=true`.

## Install

Path: `nemo-platform/packages/nmp_customization_common/values/opensandbox/`

```bash
VALUES=packages/nmp_customization_common/values/opensandbox
chmod +x ${VALUES}/install.sh
# Optional: CRUN_API_KEY=... KATA_API_KEY=... ./install.sh
./${VALUES}/install.sh
```

Manual Secrets (if not using `install.sh`):

```bash
kubectl create secret generic opensandbox-server-crun-api-key \
  -n opensandbox-system --from-literal=api-key="$(openssl rand -hex 32)"
kubectl create secret generic opensandbox-server-kata-api-key \
  -n opensandbox-system --from-literal=api-key="$(openssl rand -hex 32)"
```

## Verify

After `install.sh` succeeds:

```bash
VALUES=packages/nmp_customization_common/values/opensandbox
./${VALUES}/verify/crun.sh
./${VALUES}/verify/kata-qemu.sh
# or both:
./${VALUES}/verify/all.sh
```

Each verifier:

1. Confirms the server Deployment is Ready and the API-key Secret exists
2. Port-forwards to the Service and hits `/health`
3. Creates a short-lived `busybox` sandbox
4. Waits for `Running`
5. Asserts `runtimeClassName` (empty for crun, `kata-qemu` for kata) and node placement
6. Compares sandbox kernel (`uname -r`, `/proc/version`, virt DMI) to the node `kernelVersion` and prints evidence (mismatches are red WARN, not hard fail):
   - **crun** — expect match with host (shared-kernel)
   - **kata-qemu** — expect differ from host (guest kernel)
7. Deletes the sandbox

Env overrides: `READY_TIMEOUT_S`, `SANDBOX_IMAGE`, `SANDBOX_TIMEOUT_S`, `LOCAL_PORT`.

## Client endpoints

| Profile | In-cluster domain | Notes |
|---------|-------------------|-------|
| crun | `opensandbox-server-crun.opensandbox-system.svc.cluster.local` | No `[secure_runtime]` |
| kata-qemu | `opensandbox-server-kata.opensandbox-system.svc.cluster.local` | Preferred strong isolation |

Client / live-test workload namespace (sandboxes + test PVCs):

```bash
export OPENSANDBOX_WORKLOAD_NS=nmp-temp1
```

NeMo-RL live helpers default to `nmp-temp1` when that env is unset.

Example Gym / broker provider block for Kata:

```yaml
sandbox_provider:
  opensandbox:
    domain: opensandbox-server-kata.opensandbox-system.svc.cluster.local
    protocol: http
    use_server_proxy: true
    # api_key via OPENSANDBOX_API_KEY / secret — not in FileSets
```

## Notes

- Images use OpenSandbox's signed Docker Hub publications (`docker.io/opensandbox/*`), not the upstream chart's China-region Aliyun defaults. Production deployment may mirror and digest-pin them in an approved internal registry.
- Ingress gateway is **disabled**; rely on in-cluster Service + `use_server_proxy`.
- Control-plane pods prefer non-GPU nodes; kata sandboxes are hard-pinned to kata nodes; crun sandboxes soft-prefer non-kata / non-GPU.
- API keys live only in Kubernetes Secrets; never commit them to values files.
- Legacy `opensandbox-crun` / `opensandbox-kata` namespaces (from earlier installs) are left in place; clean up manually if empty.
