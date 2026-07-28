<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Experimentalist in OpenShell

This research-preview path separates the Experimentalist control plane from
Harbor task execution:

```text
developer files
      |
      v
OpenShell sandbox: nmp-experimentalist
  - NOOA / Experimentalist agents
  - candidate mutation and orchestration
  - no Docker CLI
  - no Docker socket
      |
      | authenticated, typed POST /v1/evaluations
      v
local Harbor bridge
  - fixed trusted candidate adapter
  - validates and hardens Harbor tasks
  - owns Harbor and the host Docker client
      |
      v
Harbor task containers
```

The OpenShell sandbox has no Docker CLI or socket. Candidate Python is archived
as data, authenticated through a narrow bridge request, and uploaded by fixed
bridge code into each Harbor task container. The Docker-owning bridge never
imports the candidate's `harbor_wrapper.py`.

## Start the local components

Install the OpenShell CLI and select a running gateway. From the repository
root, build the Experimentalist image:

```bash
export NEMO_EXPERIMENTALIST_PLATFORM=linux/arm64  # use linux/amd64 on x86 hosts
IMAGE_REGISTRY=local BAKE_TAG=local \
  docker buildx bake nmp-experimentalist-docker \
    --set "*.platform=$NEMO_EXPERIMENTALIST_PLATFORM" \
    --load
```

The resulting local tag is `local/nmp-experimentalist:local`. Point the launcher
at it. Generate one bridge token and keep it in the shell used for both the
bridge and provider setup:

```bash
export NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN="$(openssl rand -hex 32)"
export NEMO_EXPERIMENTALIST_IMAGE=local/nmp-experimentalist:local
```

Start the trusted bridge on the developer host:

```bash
uv run --frozen nemo-experimentalist-harbor-bridge --host 0.0.0.0
```

`0.0.0.0` is required for Docker Desktop sandboxes to reach the host through
`host.docker.internal`. The bearer token is required on every evaluation
request; use a host firewall on untrusted networks.

In another shell with the same token, create the OpenShell provider. Supplying
the credential name without a value makes the CLI read it from the environment
instead of placing the value in the process arguments:

```bash
openshell provider create \
  --name nemo-experimentalist-harbor-bridge \
  --type generic \
  --credential NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_TOKEN
```

Then launch Experimentalist:

```bash
export NEMO_EXPERIMENTALIST_IMAGE=local/nmp-experimentalist:local
plugins/nemo-experimentalist/examples/openshell/run.sh /path/to/agent doctor
plugins/nemo-experimentalist/examples/openshell/run.sh /path/to/agent run
```

The launcher uploads the selected agent workspace into `/sandbox/project`,
applies [`policy.yaml`](policy.yaml), attaches the bridge provider, and runs as
the non-root `sandbox` user. The provider exposes only a placeholder token to
the sandbox; OpenShell replaces it in the outbound Authorization header for
the allowed REST endpoint. The launcher sets
`NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL`, which selects the remote evaluator
and makes preflight probe the bridge instead of local Docker.

For Docker Desktop, set
`NEMO_EXPERIMENTALIST_POLICY_MODE=docker-desktop`. That uses
[`policy.docker-desktop.yaml`](policy.docker-desktop.yaml), which keeps process
and network enforcement but falls back to best-effort filesystem isolation
because the Docker Desktop kernel does not expose Landlock.

## Boundary and remaining risk

The bridge accepts only bounded evaluator settings, candidate/dataset archives,
and task IDs. It rejects caller-selected import paths, Docker Compose,
host-environment interpolation, MCP servers, and accelerators, and forces
Harbor's verifier into a separate container.

The bridge still owns a host-root-equivalent Docker socket. Uploaded Harbor
tasks can contain arbitrary Dockerfiles, and the candidate receives its model
credential inside the Harbor task container. This preview therefore reduces
the Docker API surface and removes Docker authority from Experimentalist; it
does not make untrusted Harbor tasks safe against Docker/Harbor escapes,
resource exhaustion, or credential exfiltration from their own task
container. Production follow-up should move the same API to a dedicated
evaluator worker with resource quotas, approved task sources/images, scoped
task-network policy, and short-lived inference credentials.

Git clone, registry download, and winner publication also need separately
scoped OpenShell providers and are not granted by this policy.
