# Authentik Reference Example

This directory contains a local Authentik-backed NeMo Platform example. Use it
to validate three user-visible flows:

- log in to NeMo with Authentik
- call NeMo APIs through the Authentik gateway
- run a NeMo job whose workload exchanges a real Authentik workload subject token

All credentials in this example are for local development only.

## Tutorial

Use the shared tutorial when you want to understand or manually debug the
reference deployment:

- [Authentik Reference Tutorial](tutorial.md)

At the start, choose Docker Compose or Kubernetes. The rest of the tutorial uses
the same CLI and workload commands for both runtimes. Generated local material
lives under `.generated/`, including the workload-token signing key and gateway
TLS material when those files are created locally.

Runtime details live separately:

- [Compose Implementation Details](compose/implementation-details.md)
- [Kubernetes Implementation Details](kubernetes/implementation-details.md)

## Test Harness

`run.sh` is the automation entrypoint for CI-style validation and repeatable
local test runs. It can run the local Compose stack, run the Compose auth-idp
contract tests, run the Kubernetes auth-idp contract tests, and clean up local
resources.

```bash
contrib/auth/authentik/run.sh --help
```

Common commands:

```bash
contrib/auth/authentik/run.sh compose
contrib/auth/authentik/run.sh k8s
contrib/auth/authentik/run.sh prepare-local
contrib/auth/authentik/run.sh run-local
contrib/auth/authentik/run.sh down
```

The harness keeps generated local inputs in `contrib/auth/authentik/.generated`
so Compose and Kubernetes test runs can reuse the same workload-token signing
key. Diagnostics are written under `docker/logs/authentik-*` by default, or
under `E2E_SERVICES_LOG_DIR` when that environment variable is set.

For manual startup and walkthroughs, prefer the shared tutorial above.

## Demo Identities

Both runtimes seed these local-only identities:

- Human user: `nemo-user`
- Human password: `nemo-user-password-dev`
- Human email: `nemo-user@example.com`
- CLI OIDC client: `nemo-platform-cli`
- Workload identity: `svc-nemo`
- Workload group: `nemo-workloads`

The shared blueprint also seeds `nemo-setup` with an app-password for the
automated auth-idp E2E test harness. That identity is not used by the
browser/device login flow or by managed workloads. Do not copy `nemo-setup` or
`e2e_setup_password_grant` into production deployments; production users should
authenticate interactively through OIDC, and production workloads should use a
workload identity/token-exchange mechanism instead of an app-password.

## Token Lifetimes

The Authentik OAuth provider lifetimes are fixed in the shared checked-in
blueprint at `helm/files/blueprints/nemo.yaml`: CLI access tokens use
`minutes=2`, and workload access tokens use `minutes=5`. Kubernetes projected
service account token expiration defaults to `600` seconds in the jobs backend.
Override it through the deployment's normal NeMo Platform configuration if you
need a longer projected token lifetime.

The 2-minute CLI access-token lifetime is a local demo/testing setting so token
refresh is easy to observe. Do not use it as a production default; use a longer
value such as `hours=1` outside the refresh demonstration.

In the Docker Compose runtime, Authentik issues the demo workload subject token,
but it does not accept the RFC 8693 token exchange grant directly. The Docker
backend refreshes the Authentik subject token file, the SDK posts that token to
the NeMo auth service, and the gateway trusts the NeMo auth service JWKS for
exchanged workload access tokens.
