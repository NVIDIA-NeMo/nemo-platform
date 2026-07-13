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
- Workload identity: `svc-nemo`
- Workload group: `nemo-editors`

## Start The Stack

From the repo root:

```bash
contrib/auth/authentik/run.sh stack
```

This starts NeMo, Authentik, and the local gateway with the existing default
NeMo API image, `my-registry/nmp-api:local`. The `stack` action does not build
images.
Leave this process running. Stop it with `Ctrl-C` when you are done; the script
removes the Compose stack and volumes on exit.

To use a different prebuilt image for the example, pass it explicitly:

```bash
export IMAGE_REGISTRY=registry.example.com/nemo
export BAKE_TAG=<tag>

contrib/auth/authentik/run.sh stack --image "$IMAGE_REGISTRY/nmp-api:$BAKE_TAG"
```

Use the same `IMAGE_REGISTRY` and `BAKE_TAG` values in the shell where you
submit the workload job so the job container image matches the running NeMo API
image.

The auth-idp test suite uses the same helper script:

```bash
contrib/auth/authentik/run.sh test
```

For iteration or prebuilt images, pass options to the script directly. See
`contrib/auth/authentik/run.sh --help` for the full option list.

```bash
contrib/auth/authentik/run.sh test --lifecycle reuse
contrib/auth/authentik/run.sh test --image registry.example.com/nemo/nmp-api:<tag>
```

Wait until the platform is ready through the gateway:

```bash
until curl -sf http://127.0.0.1:18080/health/ready >/dev/null; do
  sleep 2
done
echo "NeMo Platform Ready"
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
  --roles JobRunner \
  --wait-role-propagation
```

Expected result: the human user can manage the workspace, and the workload
group can read the workspace from a job.

## Run A Workload Job

```bash
export JOB_NAME=authentik-workload-demo
```

Fetch a local demo token for the seeded workload identity:

```bash
export WORKLOAD_ACCESS_TOKEN="$(
  curl -fsS http://127.0.0.1:18080/application/o/token/ \
    -d grant_type=password \
    -d client_id=nemo-platform \
    -d client_secret=nemo-platform-secret-dev \
    -d username=svc-nemo \
    -d password=svc-nemo-token-secret-dev \
    -d scope="openid email groups" \
  | python -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
)"
```

Keep this token in a non-reserved shell variable. Do not export it as
`NEMO_WORKLOAD_TOKEN` in your shell. The NeMo CLI uses that variable as a
runtime credential override, which would make later CLI commands run as the
workload identity instead of `authentik-human`.

Submit a job that runs the built-in hello-world workload auth task:

```bash
export NMP_API_IMAGE="${NMP_API_IMAGE:-${IMAGE_REGISTRY:-my-registry}/nmp-api:${BAKE_TAG:-local}}"

cat <<EOF | nemo --context authentik-human jobs create "$JOB_NAME" \
  --workspace "$WORKSPACE" \
  --input-file -
{
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
        "environment": [
          {
            "name": "NEMO_WORKLOAD_TOKEN",
            "value": "${WORKLOAD_ACCESS_TOKEN}"
          }
        ],
        "config": {"workspace": "${WORKSPACE}"}
      }
    ]
  }
}
EOF
```

Watch it complete:

```bash
nemo --context authentik-human jobs get-status "$JOB_NAME" --workspace "$WORKSPACE"
```

Expected result: the job reaches `completed`. The workload exits successfully
only after it uses the Authentik workload token to call NeMo through the gateway
and retrieve the workspace.

Read the job logs:

```bash
nemo --context authentik-human jobs get-logs "$JOB_NAME" \
  --workspace "$WORKSPACE" \
  --all-pages
```

Expected result: the logs include:

```text
Successfully retrieved workspace: authentik-demo
```

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
nemo --context authentik-human workspaces delete "$WORKSPACE"
```

Then stop the stack with `Ctrl-C` in the terminal running
`contrib/auth/authentik/run.sh stack`.

## Adapting This Example

Before adapting this pattern outside a local sandbox:

- replace all bundled demo passwords and client secrets
- configure Authentik with your real users, groups, and OIDC clients
- configure NeMo `auth.oidc` with your Authentik issuer and claim mappings
- keep the gateway as the only public entrypoint to NeMo
