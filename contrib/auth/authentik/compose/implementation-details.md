# Authentik Docker Compose Implementation Details

This page explains how the Authentik Docker Compose reference deployment is
wired. For the step-by-step test flow, see the
[shared tutorial](../tutorial.md).

## Compose Structure

The Compose tutorial starts exactly one Compose file:
`contrib/auth/authentik/compose/docker-compose.yml`.

That file declares the Docker Compose project name
`nemo-platform-authentik`, while keeping Compose-specific orchestration in
`compose/`. Set `COMPOSE_PROJECT_NAME` before running `docker compose` to use a
different local namespace. The stack mounts shared Auth IdP example assets from
the parent directory:

- `../config/platform-compose-authentik.yaml` as the NeMo Platform config.
- `../gateway/envoy.yaml` as the local gateway config.
- `../helm/files/blueprints` as Authentik's custom blueprint directory.
- `../.generated` for local generated keys and certificates.

The shared tutorial does not build NeMo images for Compose. It runs
`${IMAGE_REGISTRY:-my-registry}/nmp-api:${BAKE_TAG:-local}` for both the NeMo
API service and workload jobs submitted by the tutorial.

## Services

The stack contains:

- `nemo`: the NeMo Platform API service configured for Authentik and the Docker
  jobs backend.
- `gateway`: Envoy terminating local HTTPS on host port `18080`.
- `gateway-tls-init`: a small init container that copies local TLS material into
  the named `gateway-tls` volume with permissions suitable for Envoy.
- `authentik-postgres`: PostgreSQL for Authentik.
- `authentik-redis`: Redis for Authentik.
- `authentik-server` and `authentik-worker`: Authentik itself.

`nemo` is only on the internal network. Host and workload traffic reaches NeMo
through the `gateway` service, which also joins the workload network as
`nemo-gateway`.

## Generated Local Inputs

The shared tutorial writes generated material under
`contrib/auth/authentik/.generated` so Compose and Kubernetes debugging can
share local keys:

- `.generated/workload-token-private-key.pem`
- `.generated/gateway-tls/tls.crt`
- `.generated/gateway-tls/tls.key`

The workload-token private key is mounted into `nemo` at
`/var/run/secrets/nemo-platform/workload-token-signing/private-key.pem`.
`platform-compose-authentik.yaml` points
`auth.oidc.workload_token_private_key_file` at that mounted path. The NeMo auth
service uses the private key to sign workload-exchange access tokens, and Envoy
validates those exchanged tokens through the NeMo auth service JWKS endpoint.

The gateway TLS files are copied into the `gateway-tls` named volume by
`gateway-tls-init`. The `gateway` service uses that volume to serve HTTPS, and
the `nemo` service mounts the same volume read-only so Python HTTP clients
inside NeMo trust the demo gateway certificate.

All generated keys and certificates in this example are for local development
only.

## Authentik Blueprint

Compose mounts the shared blueprint directory
`../helm/files/blueprints` directly into Authentik at `/blueprints/custom`.
Authentik applies `nemo.yaml` from that directory to create the demo OIDC
providers, demo user, demo groups, workload identity, and E2E setup identity.

The blueprint reads `AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD` when creating the
`svc-nemo` app-password token. Compose provides a local-development default,
`svc-nemo-token-secret-dev`. Override it only when you also keep the same value
for the lifetime of the Authentik database volume, or recreate the stack with
`docker compose down -v`.

The `nemo-setup` service account and app-password in the blueprint exist solely
for automated auth-idp contract tests. They are not part of the browser login
flow or the workload identity pattern.

## NeMo Compose Configuration

`platform-compose-authentik.yaml` configures NeMo Platform for this topology:

- `platform.base_url` is `https://nemo-gateway:8080`, which is the gateway name
  visible to Docker workload containers.
- The embedded policy decision point stays on `http://127.0.0.1:8080` inside
  the `nemo` container.
- Host-side CLI login uses the port-forward-like public gateway URL
  `https://127.0.0.1:18080`.
- Workload subject tokens come from Authentik's workload OIDC provider.
- Exchanged workload access tokens come from NeMo's `/apis/auth/token` endpoint.

The Docker jobs executor mounts the `gateway-tls` volume into workload
containers and sets `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` so workload code
trusts the local gateway certificate.

## Gateway And Auth Headers

Envoy is the public entrypoint for the Compose example. It routes:

- NeMo paths such as `/.well-known/nemo-platform/`, `/apis/`, `/health/`,
  `/status`, and `/studio/` to `nemo`.
- `/health/gateway/ready` to an Envoy-owned readiness check that verifies both
  NeMo and Authentik through their upstream clusters.
- Authentik paths to `authentik-server`.

Before JWT validation, Envoy removes incoming `X-NMP-Principal-*` headers so a
client cannot spoof identity headers. For `/apis/` requests, Envoy accepts
either:

- Authentik-issued tokens from the demo providers.
- NeMo-issued workload-exchange tokens from `/apis/auth/token`.

Envoy copies the validated `sub` and `groups` claims into NeMo's principal
headers. NeMo then applies its normal workspace authorization checks.

## Workload Token Exchange

For Docker jobs, the managed jobs backend owns workload identity injection. The
job request should not include `NMP_WORKLOAD_IDENTITY_TOKEN_FILE`,
`NEMO_WORKLOAD_TOKEN`, or `NEMO_WORKLOAD_TOKEN_FILE`.

When a managed Docker workload starts, the backend creates a dedicated workload
identity volume, writes an Authentik subject token to:

```text
/var/run/secrets/nemo-platform/workload/token
```

It injects:

```text
NMP_WORKLOAD_IDENTITY_TOKEN_FILE=/var/run/secrets/nemo-platform/workload/token
```

The SDK reads that file and sends an RFC 8693 token exchange request to the
NeMo auth service through the gateway. The NeMo auth service validates the
Authentik subject token, mints a NeMo-signed access token, and returns it to the
workload. The workload uses that exchanged token for normal NeMo API calls.

The useful end-to-end validation is the workload job in the shared tutorial:
the job uses the exchanged token to call the NeMo Platform API and read the
workspace.

## Cleanup Behavior

`docker compose down -v` removes the Compose containers and volumes, including
the Authentik database and the named `gateway-tls` volume. It does not remove
files under `contrib/auth/authentik/.generated`. Keeping those files lets later
Compose and Kubernetes debugging reuse the same local workload-token signing
key.
