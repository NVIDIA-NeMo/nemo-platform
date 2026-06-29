# Authentik Reference

This directory contains a standalone local reference deployment for running
NeMo Platform with Authentik as the OIDC identity provider.

The bundle includes:

- an Authentik application for NeMo
- a `groups` scope mapping so NeMo can authorize by group membership
- a demo human admin user
- a demo machine identity that authenticates with a service token
- an Envoy gateway that strips inbound `X-NMP-Principal-*` headers before
  forwarding traffic to NeMo

## What This Deployment Verifies

This local deployment proves the customer-facing service-token flow:

1. Authentik issues a real access token for a machine identity.
2. NeMo treats that identity as an external OIDC principal, not as an internal
   `service:*` caller.
3. NeMo authorizes the machine identity through group-based workspace bindings.

## Prerequisites

- Docker with `docker compose`
- a bootstrapped NeMo Platform checkout

## Included Demo Identities

This bundle seeds the following demo identities:

- Human admin user:
  `username=akadmin`
  `password=akadmin-dev`
  `email=admin@example.com`
- Machine identity:
  `principal_id=svc-nemo-ci`
  `group=nemo-editors`
  `service token secret=svc-nemo-ci-token-secret-dev`
- OIDC client:
  `client_id=nemo-platform`
  `client_secret=nemo-platform-secret-dev`

These values are for local development only. Change them before adapting this
bundle to any shared environment.

## Local Deployment

### 1. Start the local Authentik + NeMo stack

From the repo root:

```bash
make run-contrib-auth-authentik
```

This target:

- builds and loads the local CPU image set
- starts the `nemo`, `gateway`, and Authentik services in the foreground
- uses the local image tag `local/nmp-api:authentik-local`
- tears the stack down automatically when you stop it with `Ctrl-C`

If `IMAGE_REGISTRY` or `BAKE_TAG` are already set in your shell, the target
uses those existing values. Otherwise it defaults to `local` and
`authentik-local`.

This compose stack starts:

- NeMo API on the internal hostname `nemo`
- gateway: `http://127.0.0.1:18080`
- Authentik UI and OIDC issuer: `http://127.0.0.1:19000`

The gateway forwards to the NeMo container on the same Docker network, so no
manual Envoy rewrite is required.

### 2. Verify OIDC discovery

```bash
curl -sf http://127.0.0.1:19000/application/o/nemo/.well-known/openid-configuration >/dev/null && echo "OIDC discovery OK"
```

### 3. Point the NeMo CLI at the Authentik gateway

The CLI talks to the gateway, not directly to the NeMo container.

```bash
nemo config set --context authentik-human --base-url http://127.0.0.1:18080 --activate
nemo config set --context authentik-machine --base-url http://127.0.0.1:18080
```

## Verify Service Tokens

The commands below use the NeMo CLI for workspace operations and context
switching. The only non-CLI step is minting bearer tokens so they can be loaded
into CLI contexts.

### Configure CLI contexts with access tokens

The `nemo` CLI stores bearer tokens per context. The command shape is:

```bash
nemo config set --context <context-name> --access-token "$TOKEN"
```

To switch the active context later:

```bash
nemo config use-context <context-name>
```

To inspect which context is active:

```bash
nemo config current-context
```

### 1. Get a human admin token

Use the seeded admin user to obtain a bearer token:

```bash
export HUMAN_TOKEN="$(
  uv run python - <<'PY'
import httpx

response = httpx.post(
    "http://127.0.0.1:19000/application/o/token/",
    data={
        "grant_type": "password",
        "client_id": "nemo-platform",
        "client_secret": "nemo-platform-secret-dev",
        "username": "akadmin",
        "password": "akadmin-dev",
        "scope": "openid profile email groups",
    },
    timeout=30.0,
)
response.raise_for_status()
print(response.json()["access_token"])
PY
)"
```

Load that token into the human CLI context:

```bash
nemo config set --context authentik-human --access-token "$HUMAN_TOKEN"
nemo config use-context authentik-human
```

### 2. Get a machine token

Use the seeded machine identity to obtain a bearer token:

```bash
export MACHINE_TOKEN="$(
  uv run python - <<'PY'
import httpx

response = httpx.post(
    "http://127.0.0.1:19000/application/o/token/",
    data={
        "grant_type": "client_credentials",
        "client_id": "nemo-platform",
        "client_secret": "nemo-platform-secret-dev",
        "username": "svc-nemo-ci",
        "password": "svc-nemo-ci-token-secret-dev",
        "scope": "openid email groups",
    },
    timeout=30.0,
)
response.raise_for_status()
print(response.json()["access_token"])
PY
)"
```

Load that token into the machine CLI context:

```bash
nemo config set --context authentik-machine --access-token "$MACHINE_TOKEN"
nemo config use-context authentik-machine
```

### 3. Create a workspace as the human admin

```bash
export WORKSPACE="authentik-demo"

nemo --context authentik-human workspaces create "$WORKSPACE" \
  --description "Authentik service-token demo" \
  --wait-role-propagation
```

The creator is automatically granted workspace admin access.

### 4. Confirm the machine token is denied before binding

```bash
nemo --context authentik-machine workspaces get "$WORKSPACE"
```

Expected result: an authorization failure.

### 5. Bind the machine group to the workspace

The demo machine identity belongs to the Authentik group `nemo-editors`. Grant
that group a NeMo workspace role:

```bash
nemo --context authentik-human workspaces members create \
  --workspace "$WORKSPACE" \
  --principal nemo-editors \
  --roles Viewer \
  --wait-role-propagation
```

### 6. Confirm the machine token is now allowed

```bash
nemo --context authentik-machine workspaces get "$WORKSPACE"
```

Expected result: the workspace is returned successfully.

### 7. Revoke the binding and confirm access is removed

```bash
nemo --context authentik-human workspaces members delete nemo-editors \
  --workspace "$WORKSPACE" \
  --wait-role-propagation
```

Then retry the machine request:

```bash
nemo --context authentik-machine workspaces get "$WORKSPACE"
```

Expected result: access returns to an authorization failure.

## Cleanup

Stopping `make run-contrib-auth-authentik` with `Ctrl-C` automatically removes the
compose stack and volumes.

If you created a temporary workspace for verification before stopping the
stack, you can also delete it with the human CLI context:

```bash
nemo --context authentik-human workspaces delete "$WORKSPACE"
```

## Production Adaptation

- configure NeMo `auth.oidc` with your production Authentik issuer, client ID,
  and claim mappings
- ensure your access tokens include the `groups` claim NeMo binds to roles
- keep the gateway rule that strips inbound `X-NMP-Principal-*` headers before
  forwarding to NeMo
- keep external machine callers as ordinary OIDC subjects rather than internal
  `service:*` principals
- replace all bundled development secrets before using this pattern anywhere
  outside a local sandbox

## CI Note

This compose topology is also compatible with CI as long as the `nemo` service
uses a prebuilt `nmp-api` image. The current local instructions use
`local/nmp-api:authentik-local`, while CI can provide the same service image via
`IMAGE_REGISTRY` and `BAKE_TAG` without rebuilding it.
