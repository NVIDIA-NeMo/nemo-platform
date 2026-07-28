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
  - git, gh, and glab clients
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
root, build the Experimentalist image defined by
[`plugins/nemo-experimentalist/Dockerfile`](../../../Dockerfile):

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

In another shell with the same token, configure the provider profiles. The
inference provider is held by the gateway and backs `inference.local`; its
credential is never attached to the sandbox. The bridge and selected
source-control provider expose randomized placeholders in the sandbox, which
OpenShell replaces only in proxied requests:

```bash
export NVIDIA_API_KEY=nvapi-...
export NEMO_EXPERIMENTALIST_INFERENCE_MODEL=meta/llama-3.3-70b-instruct

# Configure either or both source-control credentials. Only one is attached
# to any individual sandbox by run.sh.
export GH_TOKEN="$(gh auth token)"
export GITLAB_TOKEN=glpat-...
# For self-managed GitLab:
export NEMO_EXPERIMENTALIST_GITLAB_HOST=gitlab.example.com

plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/openshell/configure-providers.sh
```

The setup script enables the gateway-global OpenShell
`providers_v2_enabled=true` setting. Without it OpenShell injects credential
placeholders but does not compose the provider profiles' endpoint rules into
the sandbox policy.

`NVIDIA_INTERNAL_API_KEY` is also accepted for the default NVIDIA inference
provider. To use another OpenShell inference profile, set
`NEMO_EXPERIMENTALIST_INFERENCE_PROVIDER_TYPE` and the credential environment
variables that profile discovers.

Then launch Experimentalist. Source control is disabled by default:

```bash
export NEMO_EXPERIMENTALIST_IMAGE=local/nmp-experimentalist:local
plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/openshell/run.sh /path/to/agent doctor
plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/openshell/run.sh /path/to/agent run
```

For a GitHub or GitLab agent source, attach one provider with the least
authority the run needs:

```bash
# HTTPS clone/fetch and API reads
export NEMO_EXPERIMENTALIST_SOURCE_CONTROL=github-read

# Or allow HTTPS branch push and draft winner PR creation
export NEMO_EXPERIMENTALIST_SOURCE_CONTROL=github-publish

# GitLab equivalents
export NEMO_EXPERIMENTALIST_SOURCE_CONTROL=gitlab-read
export NEMO_EXPERIMENTALIST_SOURCE_CONTROL=gitlab-publish
```

The current profiles support `github.com` and either `gitlab.com` or one exact
self-managed GitLab hostname configured before provider setup and launch. SSH,
Git LFS, and GitHub Enterprise are not included in this research-preview
policy.

The launcher uploads the selected agent workspace into `/sandbox/project`,
applies [`policy.yaml`](policy.yaml), attaches the bridge provider, and runs as
the non-root `sandbox` user. When selected, it also attaches exactly one
source-control provider. The launcher sets
`NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL`, which selects the remote evaluator
and makes preflight probe the bridge instead of local Docker.

Experimentalist itself calls `git` for clone, fetch, checkout, commit, and
push. It calls `gh pr create` for a GitHub winner and `glab mr create` for a
GitLab winner; preflight also calls `gh auth status` or `glab auth status`.
The image therefore includes all three CLIs. `GIT_ASKPASS` supplies provider
placeholders to HTTPS Git without storing a real source-control token in the
container. For GitLab, the launcher writes the placeholder—not the real
token—to `glab`'s per-host config so its auth-status check recognizes the
self-managed host.

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

OpenShell static provider placeholders are currently resolved from a
sandbox-wide map rather than being cryptographically bound to one target
hostname. This launcher never attaches GitHub and GitLab providers together,
so one source-control token cannot be substituted into a request to the other
service. The source-control placeholder can still be sent to the trusted local
bridge endpoint, and the bridge placeholder can be sent to the selected source
host; neither endpoint reflects the resolved Authorization header. Endpoint
binding in OpenShell would make this defense stronger.

Registry download is not granted by this policy.
