# Authentik Reference Tutorial

This tutorial validates the Authentik reference deployment against one runtime:
Docker Compose or Kubernetes. Choose a runtime in the first section, then run
the remaining sections exactly the same way for both.

The tutorial covers:

- NeMo CLI login through Authentik.
- NeMo API calls through the Authentik gateway.
- Workload identity token exchange through a workload job.

For shared identities, token lifetimes, and automated test harness commands,
see [the top-level Authentik README](README.md). For runtime internals, see the
[Compose details](compose/implementation-details.md) or
[Kubernetes details](kubernetes/implementation-details.md).

All credentials in this example are for local development only.

## Choose A Runtime

Use either Docker Compose or Kubernetes. After the chosen runtime is running,
continue with [Wait For The Gateway](#wait-for-the-gateway).

From the repo root, prepare shared generated inputs once:

```bash
contrib/auth/authentik/run.sh prepare-local
```

This creates the shared workload-token signing key, gateway TLS material, and
rendered Authentik blueprint under `contrib/auth/authentik/.generated`.

### Docker Compose

Prerequisites:

- Docker with `docker compose`
- `openssl`
- `curl`
- a bootstrapped NeMo Platform checkout
- a shell from the repo root

Start Compose in one terminal:

```bash
docker compose -f contrib/auth/authentik/compose/docker-compose.yml up
```

This starts NeMo, Authentik, and the local gateway with the default NeMo API
image, `my-registry/nmp-api:local`. The Compose stack does not build images.

In another terminal from the repo root, export the runtime variables used by the
rest of the tutorial:

```bash
export AUTHENTIK_RUNTIME=compose
export AUTHENTIK_CONTEXT=authentik-compose
export AUTHENTIK_BASE_URL=https://127.0.0.1:18080
export AUTHENTIK_GATEWAY_CA=contrib/auth/authentik/.generated/gateway-tls/tls.crt
export NMP_CLIENT_SSL_CERT_FILE="$AUTHENTIK_GATEWAY_CA"
export AUTHENTIK_WORKLOAD_GROUP=nemo-workloads
export WORKSPACE=authentik-demo
export JOB_NAME=authentik-workload-demo
export IMAGE_REGISTRY="${IMAGE_REGISTRY:-my-registry}"
export BAKE_TAG="${BAKE_TAG:-local}"
export NMP_API_IMAGE="${NMP_API_IMAGE:-${IMAGE_REGISTRY}/nmp-api:${BAKE_TAG}}"
```

`AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD` has a local-development default. If you
override it, keep the same value until you remove the Compose volumes with
`docker compose down -v`.

### Kubernetes

Prerequisites:

- `helm`
- `kubectl`
- `kind`
- Docker
- `curl`
- outbound image pull access for the third-party Authentik, Envoy, and
  PostgreSQL images
- a NeMo Platform service image loaded into the kind cluster, or pushed to a
  registry the cluster can pull

From the repo root:

```bash
export AUTHENTIK_RUNTIME=kubernetes
export KIND_CLUSTER=nmp-authentik-dev
export KUBE_CONTEXT="kind-${KIND_CLUSTER}"
export NAMESPACE=nemo-authentik
export HELM_RELEASE=authentik-demo
export IMAGE_REGISTRY="${IMAGE_REGISTRY:-my-registry}"
export BAKE_TAG="${BAKE_TAG:-local}"
export NMP_API_IMAGE="${IMAGE_REGISTRY}/nmp-api:${BAKE_TAG}"
export NEMO_AUTHENTIK_TMP_DIR="${TMPDIR:-/tmp}/nemo-authentik"
export KUBECONFIG="${NEMO_AUTHENTIK_TMP_DIR}/kubeconfig.yaml"

mkdir -p "${NEMO_AUTHENTIK_TMP_DIR}"

if kind get clusters | grep -qx "${KIND_CLUSTER}"; then
  kind export kubeconfig --name "${KIND_CLUSTER}" --kubeconfig "${KUBECONFIG}"
else
  kind create cluster --name "${KIND_CLUSTER}" --kubeconfig "${KUBECONFIG}"
fi

kubectl --context "${KUBE_CONTEXT}" create namespace "${NAMESPACE}" \
  --dry-run=client -o yaml | \
  kubectl --context "${KUBE_CONTEXT}" apply -f -
```

Build the local NeMo Platform image and load it into kind:

```bash
make docker-load DOCKER_TARGET=nmp-api-docker
docker image inspect "${NMP_API_IMAGE}" >/dev/null
kind load docker-image "${NMP_API_IMAGE}" --name "${KIND_CLUSTER}"
```

Install the chart:

```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia --force-update
helm repo add authentik https://charts.goauthentik.io --force-update
helm repo update

helm dependency build k8s/helm
helm dependency build contrib/auth/authentik/helm
helm --kube-context "${KUBE_CONTEXT}" upgrade --install "${HELM_RELEASE}" contrib/auth/authentik/helm \
  --namespace "${NAMESPACE}" \
  --create-namespace \
  --wait \
  --wait-for-jobs \
  --timeout 10m \
  --set-string nemo-platform.api.image.repository="${IMAGE_REGISTRY}/nmp-api" \
  --set-string nemo-platform.api.image.tag="${BAKE_TAG}" \
  --set-string nemo-platform.core.image.repository="${IMAGE_REGISTRY}/nmp-api" \
  --set-string nemo-platform.core.image.tag="${BAKE_TAG}" \
  --set-string nemo-platform.platformConfig.platform.image_registry="${IMAGE_REGISTRY}" \
  --set-string nemo-platform.platformConfig.platform.image_tag="${BAKE_TAG}" \
  --set-file workloadTokenSigningKey.privateKeyPem=contrib/auth/authentik/.generated/workload-token-private-key.pem
```

Wait for the main workloads:

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" rollout status statefulset/shared-postgresql
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" rollout status deploy/authentik-server
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" rollout status deploy/authentik-worker
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" rollout status deploy/nemo-platform-api
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" rollout status deploy/nemo-platform-envoy
```

Port-forward the NeMo Platform Envoy service in a separate terminal with the
same `KUBECONFIG`, `KUBE_CONTEXT`, and `NAMESPACE` exports:

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" port-forward svc/nemo-platform-envoy 18081:8080
```

In the original terminal, export the demo CA and runtime variables used by the
rest of the tutorial:

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" get secret nemo-platform-envoy-tls \
  -o jsonpath='{.data.ca\.crt}' | base64 -d \
  > "${NEMO_AUTHENTIK_TMP_DIR}/ca.crt"

touch "${NEMO_AUTHENTIK_TMP_DIR}/config.yaml"

export AUTHENTIK_CONTEXT=authentik-k8s
export AUTHENTIK_BASE_URL=https://127.0.0.1:18081
export AUTHENTIK_GATEWAY_CA="${NEMO_AUTHENTIK_TMP_DIR}/ca.crt"
export NMP_CLIENT_SSL_CERT_FILE="$AUTHENTIK_GATEWAY_CA"
export NMP_CONFIG_FILE="${NEMO_AUTHENTIK_TMP_DIR}/config.yaml"
export AUTHENTIK_WORKLOAD_GROUP="system:serviceaccounts:${NAMESPACE}"
export WORKSPACE=authentik-demo
export JOB_NAME=authentik-workload-demo
```

## Wait For The Gateway

From this point on, the commands are the same for Compose and Kubernetes.

```bash
until curl --cacert "$AUTHENTIK_GATEWAY_CA" -sf "${AUTHENTIK_BASE_URL}/health/gateway/ready" >/dev/null; do
  sleep 2
done
echo "NeMo Platform and Authentik Ready"
```

## Log In With Authentik

Start the Authentik device-code login:

```bash
uv run nemo auth login \
  --context "$AUTHENTIK_CONTEXT" \
  --base-url "$AUTHENTIK_BASE_URL"
```

If a browser opens, log in with:

- username: `nemo-user`
- password: `nemo-user-password-dev`

If the browser does not open automatically, the CLI prints a URL and code. Open
the URL promptly, enter the code, and log in with the same demo credentials.

Verify the saved session:

```bash
uv run nemo --context "$AUTHENTIK_CONTEXT" auth status
```

Expected result: `auth status` shows `Auth Type: oauth`, the email
`nemo-user@example.com`, a refresh token, and an access token.

Wait for the short-lived access token to get close to expiry, then run a normal
authenticated command:

```bash
sleep 70
uv run nemo --context "$AUTHENTIK_CONTEXT" workspaces list
uv run nemo --context "$AUTHENTIK_CONTEXT" auth status
```

Expected result: `workspaces list` returns without an auth error. The CLI uses
the saved refresh token before the request and might print
`[Auto-refreshed expired token]` before the workspace output.

## Create A Demo Workspace

Create the workspace:

```bash
uv run nemo --context "$AUTHENTIK_CONTEXT" workspaces create "$WORKSPACE" \
  --description "Authentik reference example (${AUTHENTIK_RUNTIME})" \
  --wait-role-propagation
```

Grant the demo human Authentik group access:

```bash
uv run nemo --context "$AUTHENTIK_CONTEXT" workspaces members create \
  --workspace "$WORKSPACE" \
  --principal nemo-editors \
  --roles Viewer \
  --wait-role-propagation
```

Grant the workload identity group read access and permission to upload workload
logs. In Compose this is the dedicated `nemo-workloads` Authentik group; in
Kubernetes this is the projected service-account group:

```bash
uv run nemo --context "$AUTHENTIK_CONTEXT" workspaces members create \
  --workspace "$WORKSPACE" \
  --principal "$AUTHENTIK_WORKLOAD_GROUP" \
  --roles Viewer \
  --roles JobRunner \
  --wait-role-propagation
```

Expected result: the human user can manage the workspace, and the workload
identity can read the workspace from a job and upload the job logs.

## Run A Workload Job

Submit a workload job that reads the workspace through the public SDK:

```bash
cat <<EOF | uv run nemo --context "$AUTHENTIK_CONTEXT" jobs create "$JOB_NAME" \
  --workspace "$WORKSPACE" \
  --input-file -
{
  "source": "authentik-reference-example-${AUTHENTIK_RUNTIME}",
  "spec": {"demo": "authentik-workload-auth"},
  "platform_spec": {
    "steps": [
      {
        "name": "workload-workspace-get",
        "executor": {
          "provider": "cpu",
          "profile": "workload",
          "container": {
            "image": "${NMP_API_IMAGE}",
            "entrypoint": ["nemo-platform"],
            "command": [
              "run",
              "task",
              "--task",
              "nmp.hello_world.tasks.workload_workspace_get"
            ]
          }
        },
        "config": {"workspace": "${WORKSPACE}"}
      }
    ]
  }
}
EOF
```

Watch it complete and read the logs:

```bash
uv run nemo --context "$AUTHENTIK_CONTEXT" jobs get-status "$JOB_NAME" \
  --workspace "$WORKSPACE"

uv run nemo --context "$AUTHENTIK_CONTEXT" jobs get-logs "$JOB_NAME" \
  --workspace "$WORKSPACE" \
  --all-pages
```

Repeat `jobs get-status` until the job reaches `completed`, then read the logs.
Expected result:

```text
Successfully retrieved workspace: authentik-demo
```

That result means the workload used the runtime's managed subject token,
exchanged it for a NeMo access token, passed Envoy JWT validation, and called
the NeMo Platform API.

Do not include `NMP_WORKLOAD_IDENTITY_TOKEN_FILE`, `NEMO_WORKLOAD_TOKEN`, or
`NEMO_WORKLOAD_TOKEN_FILE` in the job request. Managed job backends own those
auth variables.

If a Kubernetes job pod does not start, inspect the pod:

```bash
if [ "$AUTHENTIK_RUNTIME" = "kubernetes" ]; then
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" get pods \
    -l "nmp.nvidia.com/job_id=${JOB_NAME}"

  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" get pod \
    -l "nmp.nvidia.com/job_id=${JOB_NAME}" \
    -o jsonpath='{range .items[*].spec.initContainers[*]}init {.name}: {.image}{"\n"}{end}{range .items[*].spec.containers[*]}container {.name}: {.image}{"\n"}{end}'

  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" describe pod \
    -l "nmp.nvidia.com/job_id=${JOB_NAME}"
fi
```

For the local kind path, `launcher-injector` and `nemo-job-task` should both use
`${NMP_API_IMAGE}`. If either container shows an unexpected image, rerun the
Helm install command with the image overrides shown above.

## Refresh The CLI Session

The example requests `offline_access`, so the CLI stores a refresh token.

```bash
uv run nemo --context "$AUTHENTIK_CONTEXT" auth refresh
uv run nemo --context "$AUTHENTIK_CONTEXT" auth status
```

Expected result: the context remains authenticated and still reports a refresh
token.

## Cleanup

Remove the demo job and workspace if you created them:

```bash
uv run nemo --context "$AUTHENTIK_CONTEXT" jobs delete "$JOB_NAME" --workspace "$WORKSPACE"
uv run nemo --context "$AUTHENTIK_CONTEXT" workspaces delete "$WORKSPACE"
```

Then clean up the runtime you chose.

For Compose, stop the foreground process with `Ctrl-C`, then run:

```bash
docker compose -f contrib/auth/authentik/compose/docker-compose.yml down -v
```

For Kubernetes:

```bash
helm --kube-context "$KUBE_CONTEXT" uninstall "$HELM_RELEASE" --namespace "$NAMESPACE"
kind delete cluster --name "$KIND_CLUSTER"
```

## Next Steps

- [Compose Implementation Details](compose/implementation-details.md)
- [Kubernetes Implementation Details](kubernetes/implementation-details.md)
- [Authentication and IdP integration](../../../docs/auth/authentication/idp-integration.mdx)
- [Production Helm deployment](../../../docs/set-up/helm/index.mdx)
