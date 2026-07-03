# Authentik Reference Example

This directory contains a local Authentik-backed NeMo Platform example. Use it
to verify three user-visible flows:

- log in to NeMo with Authentik
- call NeMo APIs through the Authentik gateway
- run a NeMo job whose workload uses a real Authentik workload token

All credentials in this example are for local development only.

## Prerequisites

- Docker with `docker compose`
- a bootstrapped NeMo Platform checkout
- a shell from the repo root

## Demo Identities

The stack seeds these local-only identities:

- Human user: `nemo-user`
- Human password: `nemo-user-password-dev`
- Human email: `nemo-user@example.com`
- CLI OIDC client: `nemo-platform-cli`
- Workload identity: `svc-nemo-ci`
- Workload group: `nemo-editors`

## Start The Stack

From the repo root:

```bash
contrib/auth/authentik/run.sh stack
```

This starts NeMo, Authentik, and the local gateway with the existing default
NeMo API image, `my-registry/nmp-api:local`. The script does not build images.
Leave this process running. Stop it with `Ctrl-C` when you are done; the script
removes the Compose stack and volumes on exit.

To use a different prebuilt image for the example, pass it explicitly:

```bash
contrib/auth/authentik/run.sh stack --image registry.example.com/nemo/nmp-api:<tag>
```

The auth-idp test suite has one entrypoint:

```bash
make test-auth-idp
```

To run the tests against the same prebuilt image used by the example, pass the
matching registry and tag to that test target:

```bash
IMAGE_REGISTRY=registry.example.com/nemo BAKE_TAG=<tag> make test-auth-idp
```

Wait until the gateway is ready:

```bash
until curl -sf http://127.0.0.1:18080/apis/auth/discovery >/dev/null; do
  sleep 2
done
```

The local gateway URL is:

```text
http://127.0.0.1:18080
```

## Log In With Authentik

Point the CLI at the Authentik gateway:

```bash
nemo config set --context authentik-human --base-url http://127.0.0.1:18080 --activate
```

Start browser login:

```bash
nemo auth login --context authentik-human --base-url http://127.0.0.1:18080
```

Log in with:

- username: `nemo-user`
- password: `nemo-user-password-dev`

Verify the saved session:

```bash
nemo --context authentik-human auth status
nemo --context authentik-human workspaces list
```

Expected result: `auth status` shows `Auth Type: oauth`, the email
`nemo-user@example.com`, and a refresh token. `workspaces list` should return
without an auth error.

## Create A Demo Workspace

```bash
export WORKSPACE=authentik-demo

nemo --context authentik-human workspaces create "$WORKSPACE" \
  --description "Authentik reference example" \
  --wait-role-propagation
```

Grant the demo workload group access to the workspace:

```bash
nemo --context authentik-human workspaces members create \
  --workspace "$WORKSPACE" \
  --principal nemo-editors \
  --roles Viewer \
  --roles JobLogWriter \
  --wait-role-propagation
```

Expected result: the human user can manage the workspace, and the workload
group can read the workspace and upload job logs.

## Run A Workload Job

```bash
export JOB_NAME=authentik-workload-demo
export WORKLOAD_TOKEN_SECRET="${JOB_NAME}-token"
```

Fetch a local demo token for the seeded workload identity and store it as a
workspace secret:

```bash
export NEMO_WORKLOAD_TOKEN="$(
  curl -fsS http://127.0.0.1:18080/application/o/token/ \
    -d grant_type=password \
    -d client_id=nemo-platform \
    -d client_secret=nemo-platform-secret-dev \
    -d username=svc-nemo-ci \
    -d password=svc-nemo-ci-token-secret-dev \
    -d scope="openid email groups" \
  | python -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
)"

printf '%s' "$NEMO_WORKLOAD_TOKEN" \
  | nemo --context authentik-human secrets create "$WORKLOAD_TOKEN_SECRET" \
      --workspace "$WORKSPACE" \
      --from-file -
```

Create the job request:

```bash
python - <<'PY' >/tmp/authentik-workload-job.json
import json
import os
import sys

payload = {
    "source": "authentik-reference-example",
    "spec": {"demo": "authentik-workload-auth"},
    "platform_spec": {
        "steps": [
            {
                "name": "workload-workspace-get",
                "executor": {
                    "provider": "cpu",
                    "profile": "workload",
                    "container": {
                        "entrypoint": ["nemo-platform"],
                        "command": [
                            "run",
                            "task",
                            "--task",
                            "nmp.hello_world.tasks.workload_workspace_get",
                        ],
                    },
                },
                "environment": [
                    {
                        "name": "NEMO_WORKLOAD_TOKEN",
                        "from_secret": {"name": os.environ["WORKLOAD_TOKEN_SECRET"]},
                    }
                ],
                "config": {"workspace": os.environ["WORKSPACE"]},
            }
        ]
    },
}

json.dump(payload, sys.stdout, indent=2)
PY
```

Submit the job:

```bash
nemo --context authentik-human jobs create "$JOB_NAME" \
  --workspace "$WORKSPACE" \
  --input-file /tmp/authentik-workload-job.json
```

Watch it complete:

```bash
nemo --context authentik-human jobs get-status "$JOB_NAME" --workspace "$WORKSPACE"
```

After the job reaches `completed`, read the logs:

```bash
nemo --context authentik-human jobs get-logs "$JOB_NAME" \
  --workspace "$WORKSPACE" \
  --all-pages
```

Expected result: the logs include:

```text
Successfully retrieved workspace: authentik-demo
```

That confirms the job workload used the Authentik workload token to call NeMo
through the gateway.

## Refresh The CLI Session

The example requests `offline_access`, so the CLI stores a refresh token.

```bash
nemo --context authentik-human auth refresh
nemo --context authentik-human auth status
```

Expected result: the context remains authenticated and still reports a refresh
token.

## Cleanup

Remove the demo job and workspace if you created them:

```bash
nemo --context authentik-human jobs delete "$JOB_NAME" --workspace "$WORKSPACE"
nemo --context authentik-human secrets delete "$WORKLOAD_TOKEN_SECRET" --workspace "$WORKSPACE"
nemo --context authentik-human workspaces delete "$WORKSPACE"
```

Then stop the stack with `Ctrl-C` in the terminal running
`contrib/auth/authentik/run.sh stack`.

## Troubleshooting

- `Audiences in Jwt are not allowed`: restart the stack so Envoy reloads the
  latest gateway config, then log in again.
- `Permission denied`: verify `nemo --context authentik-human auth status`,
  then check
  `nemo --context authentik-human workspaces members list --workspace "$WORKSPACE"`.
  If you just created the workspace or member bindings, wait a few seconds and
  retry so the authorization cache can refresh.
- Job stays `created` or `pending`: confirm the stack was started with
  `contrib/auth/authentik/run.sh stack` and Docker is running.
- Job completes but logs are missing: confirm `nemo-editors` has `JobLogWriter`
  on the workspace.

## Adapting This Example

Before adapting this pattern outside a local sandbox:

- replace all bundled demo passwords and client secrets
- configure Authentik with your real users, groups, and OIDC clients
- configure NeMo `auth.oidc` with your Authentik issuer and claim mappings
- keep the gateway as the only public entrypoint to NeMo
