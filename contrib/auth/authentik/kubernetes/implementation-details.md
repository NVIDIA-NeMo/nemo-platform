# Authentik Kubernetes Implementation Details

This page explains how the Authentik Kubernetes reference deployment is wired.
For the step-by-step test flow, see the [shared tutorial](../tutorial.md).

## Chart Structure

Install exactly one chart for this example:
`contrib/auth/authentik/helm`. That umbrella chart depends on the official
Authentik chart and the repository's `k8s/helm` NeMo Platform chart. The
umbrella chart owns the shared PostgreSQL StatefulSet used by both Authentik
and NeMo Platform, plus the demo-specific glue resources needed for Authentik,
workload token exchange, and the NeMo Platform Envoy configuration.

The shared PostgreSQL image is pinned to
`docker.io/library/postgres:18.4`, which reports PostgreSQL `18.4` at runtime.

The chart blueprint includes a `nemo-setup` service account and app-password
solely for the automated auth-idp E2E test harness. It is not part of the
browser/device login path and it is not a workload identity pattern. Do not copy
`nemo-setup` or `e2e_setup_password_grant` into production deployments; use
normal OIDC login for users and workload token exchange for workloads.

## Demo Secrets

The local Authentik smoke test does not require an NGC key. The umbrella chart
leaves `nemo-platform.existingSecret` unset, so the NeMo Platform chart creates
its demo `ngc-api` Secret from chart values. If the NeMo Platform image comes
from a private registry instead of `kind load docker-image`, create an
image-pull Secret and add
`--set-string nemo-platform.imagePullSecrets[0].name=<secret>` to the Helm
upgrade command.

The chart creates or reuses these additional local-demo Secrets during Helm
rendering:

- `shared-postgresql` for the shared PostgreSQL superuser, Authentik, and NeMo
  database passwords.
- `shared-postgresql-nemo` for the NeMo Platform external database password.
- `nemo-platform-envoy-tls` for the demo Envoy TLS certificate and CA.
- `nemo-workload-token-signing-key` for the NeMo-issued workload access token
  signing key.

The chart generates `Secret/nemo-platform-envoy-tls` during Helm rendering and
reuses an existing Secret on upgrade. The Envoy TLS private key is never checked
into the repository and is not supplied through `values.yaml`.

All credentials and generated keys in this example are for local development
only.

## Authentik Blueprint

The umbrella chart packages the shared blueprint from
`helm/files/blueprints/nemo.yaml` into `ConfigMap/authentik-nemo-blueprint` and
configures the official Authentik chart to mount it. A Helm
`post-install,post-upgrade` hook Job runs `ak apply_blueprint` against that
mounted file.

Use `--wait --wait-for-jobs` when installing the chart so Helm only returns
after the blueprint has been applied.

## NeMo Kubernetes Override

The umbrella chart passes the Kubernetes-specific NeMo Platform configuration
through `nemo-platform.platformConfig` values. It also configures
`nemo-platform.envoyProxy.configOverride` so the NeMo Platform chart's Envoy
deployment keeps the Authentik path split and validates both Authentik-issued
tokens and NeMo workload-exchange tokens.

Kubernetes projected service account token expiration defaults to `600` seconds
in the jobs backend. Override it through the NeMo Platform chart values if you
need a longer projected token lifetime.

## Workload Token Exchange

The Kubernetes jobs backend projects a Kubernetes service account token into
workload pods and injects:

```text
NMP_WORKLOAD_IDENTITY_TOKEN_FILE=/var/run/secrets/nemo-platform/workload/token
```

The SDK reads that file and sends an RFC 8693 token exchange request to the NeMo
auth service over HTTPS. The chart mounts `ca.crt` from
`Secret/nemo-platform-envoy-tls` into Kubernetes workload pods and sets
`SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` so in-pod Python HTTP clients verify
the demo Envoy certificate. Host-side `nemo` commands should use
`NMP_CLIENT_SSL_CERT_FILE` instead so unrelated tools keep their normal trust
store.

The NeMo auth service validates projected service account tokens with the
TokenReview API and returns a NeMo-signed JWT trusted by the NeMo Platform
Envoy. The useful end-to-end validation is the workload job in the tutorial:
the job pod uses the exchanged token to call the NeMo Platform API and read the
workspace.

The workload job request should not include workload auth environment
variables. The Kubernetes jobs backend owns `NMP_WORKLOAD_IDENTITY_TOKEN_FILE`;
users must not set `NEMO_WORKLOAD_TOKEN` or `NEMO_WORKLOAD_TOKEN_FILE`.

To inspect the projected token mount for a submitted job:

```bash
kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" get pods \
  -l "nmp.nvidia.com/job_id=${JOB_NAME}"

kubectl --context "${KUBE_CONTEXT}" -n "${NAMESPACE}" describe pod \
  -l "nmp.nvidia.com/job_id=${JOB_NAME}"
```

## Workload Token Signing Key

Workload identity token exchange requires the NeMo auth service to sign the
access token it mints from a Kubernetes projected service account subject
token. The chart creates `Secret/nemo-workload-token-signing-key` by default,
mounts `private-key.pem` into the NeMo Platform API pod at
`/etc/nmp/workload-token/private-key.pem`, and sets
`auth.oidc.workload_token_private_key_file` to that path. The matching public
key is served from `/apis/auth/jwks`; the NeMo Platform chart's Envoy deployment
uses that JWKS endpoint to validate exchanged workload tokens.

The manual walkthrough can rely on the Helm chart to create and preserve this
Secret.

If you need the same deterministic key for manual debugging, generate one and
add the `--set-file` line to the Helm upgrade command:

```bash
mkdir -p contrib/auth/authentik/.generated
openssl genrsa -out contrib/auth/authentik/.generated/workload-token-private-key.pem 2048
chmod 600 contrib/auth/authentik/.generated/workload-token-private-key.pem
--set-file workloadTokenSigningKey.privateKeyPem=contrib/auth/authentik/.generated/workload-token-private-key.pem
```

For production-style deployments, provide an externally managed RSA private-key
Secret instead of relying on the demo-generated key. Set
`workloadTokenSigningKey.create=false`, keep
`workloadTokenSigningKey.secretName` and
`nemo-platform.api.extraVolumes[].secret.secretName` aligned, and keep
`auth.oidc.workload_token_private_key_file` pointed at the mounted file path.
