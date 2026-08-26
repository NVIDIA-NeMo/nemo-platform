<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# OpenSandbox example overlays

The NeMo Platform Helm chart does **not** install OpenSandbox. These files are
values and BatchSandbox templates for the upstream OpenSandbox charts. Point
jobs at **one** already-installed server.

Use OpenSandbox for **sandboxed GRPO / NeMo Gym**: untrusted custom environment
FileSets run in isolated pods, not in the training container. It does **not**
sandbox the rest of the platform (API, DPO, SFT, inference). The default path
is **shared-kernel** (cluster default OCI runtime: often runc on containerd, or
crun on CRI-O including OKE/OpenShift). **Kata is not required**; use Kata only
when those Gym/GRPO sandbox pods must be isolated from the host kernel (QEMU VM).

Full procedure: [OpenSandbox](https://docs.nvidia.com/nemo-platform/latest/documentation/self-managed-deployment/setup/helm/opensandbox)
and [OpenSandbox with Kata](https://docs.nvidia.com/nemo-platform/latest/documentation/self-managed-deployment/setup/helm/opensandbox-kata)
in the NeMo Platform documentation. `helm show readme` of this chart points at
those pages.

## Namespace rule

`[kubernetes] namespace` in the server TOML **must be the Helm release
namespace** (the namespace platform jobs run in). Control plane can stay in
`opensandbox-system`. PVC remounts and image-pull secrets do not work across
namespaces.

Replace `REPLACE_WITH_RELEASE_NAMESPACE` in the server values before install.

## Files

| File | Role |
|------|------|
| `opensandbox-controller.yaml` | Shared controller (snapshots unused on CRI-O) |
| `opensandbox-server.yaml` | Shared-kernel server (no `[secure_runtime]`) |
| `opensandbox-server-kata-qemu.yaml` | Kata QEMU server (`[secure_runtime] type=kata`) |
| `batchsandbox-template.yaml` | ConfigMap — exclude control-plane; soft-avoid GPU/Kata |
| `batchsandbox-template-kata-qemu.yaml` | ConfigMap — example Kata node selectors |

`[secure_runtime]` is server-global. Install **one** server for production
(shared-kernel **or** Kata). Dual releases are only for proving both paths.

## Install (shared-kernel)

Requires a local OpenSandbox checkout with charts under
`kubernetes/charts/`, or a published chart tarball.

```bash
export NMP_NAMESPACE=nemo-platform          # must match the platform job namespace
export OPENSANDBOX_DIR=/path/to/OpenSandbox
export EXAMPLES=k8s/helm/examples/opensandbox

# Replace the placeholder in the server values
sed -i.bak "s/REPLACE_WITH_RELEASE_NAMESPACE/${NMP_NAMESPACE}/g" \
  "${EXAMPLES}/opensandbox-server.yaml"

kubectl create namespace opensandbox-system --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace "${NMP_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f "${EXAMPLES}/batchsandbox-template.yaml"

# API key in the control-plane namespace (server reads it)
kubectl create secret generic opensandbox-server-api-key \
  -n opensandbox-system --from-literal=api-key="$(openssl rand -hex 32)"

# Copy the same key into the job namespace (jobs use secretKeyRef)
kubectl get secret opensandbox-server-api-key -n opensandbox-system -o json \
  | jq 'del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.namespace)' \
  | kubectl apply -n "${NMP_NAMESPACE}" -f -

# Image pull secret for sandbox pods must also exist in the job namespace
kubectl get secret nvcrimagepullsecret -n "${NMP_NAMESPACE}"

helm upgrade --install opensandbox-controller \
  "${OPENSANDBOX_DIR}/kubernetes/charts/opensandbox-controller" \
  --namespace opensandbox-system \
  -f "${EXAMPLES}/opensandbox-controller.yaml"

helm upgrade --install opensandbox-server-crun \
  "${OPENSANDBOX_DIR}/kubernetes/charts/opensandbox-server" \
  --namespace opensandbox-system \
  -f "${EXAMPLES}/opensandbox-server-crun.yaml"
```

Then set on the platform chart:

```yaml
sandboxClusterCapable: true
opensandbox:
  domain: opensandbox-server-crun.opensandbox-system.svc.cluster.local
  protocol: http
  apiKeySecret: opensandbox-server-api-key
  apiKeySecretKey: api-key
```

Client env names are `OPEN_SANDBOX_DOMAIN` and `OPEN_SANDBOX_API_KEY` (not
Gym's `OPENSANDBOX_*`).

## Install (Kata)

Follow the Kata page for `kata-deploy` and CRI-O retrofit, then the same
controller install plus `-f opensandbox-server-kata-qemu.yaml`. Override
`opensandbox.domain` to `opensandbox-server-kata.opensandbox-system.svc.cluster.local`.

## Verify

```bash
export OPEN_SANDBOX_WORKLOAD_NS="${NMP_NAMESPACE}"
./k8s/helm/examples/opensandbox/verify/crun.sh
# or, after installing the Kata server:
./k8s/helm/examples/opensandbox/verify/kata-qemu.sh
```
