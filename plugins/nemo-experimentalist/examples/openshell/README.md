<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Experimentalist in OpenShell

This prototype separates the Experimentalist control plane from Harbor task
execution:

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
      | narrow evaluation request (not wired yet)
      v
NeMo Evaluator Harbor worker
  - trusted evaluator code
  - Harbor and Docker CLI
  - dedicated Docker-owning execution profile
      |
      v
Harbor task containers
```

The container and sandbox boundary are runnable. A full optimization currently
stops at Experimentalist's required `docker info` preflight because its
`HarborEvaluator` still executes in-process. That failure is intentional: do
not mount the host Docker socket into the OpenShell sandbox.

## Build the image

Install the OpenShell CLI and select a running gateway first. From the
repository root, build the Experimentalist image:

```bash
IMAGE_REGISTRY=local BAKE_TAG=local \
  docker buildx bake nmp-experimentalist-docker --load
```

The resulting local tag is `local/nmp-experimentalist:local`. Point the launcher
at it:

```bash
export NEMO_EXPERIMENTALIST_IMAGE=local/nmp-experimentalist:local
plugins/nemo-experimentalist/examples/openshell/run.sh /path/to/agent doctor
```

The launcher uploads the selected agent workspace into `/sandbox/project`,
applies [`policy.yaml`](policy.yaml), and runs the command as the non-root
`sandbox` user. It defaults the Platform API to
`http://host.docker.internal:8080` and model traffic to OpenShell's
`https://inference.local/v1` route. Direct Platform access is limited to
`GET /health/ready`; the future evaluation submission route must be added only
after its request contract is narrowed and validated.

## What NeMo Evaluator already provides

`AgentEvalJob` already accepts `HarborRunnerTarget`, and
`HarborAgentTaskRunner` already creates the Harbor job and converts its result
tree into evaluator trials. It is the right service boundary for Docker.

The submitted-job path still needs five pieces before Experimentalist can use
it:

1. A narrow Experimentalist evaluation API backed by `AgentEvalJob`. It should
   accept candidate/dataset references and construct a fixed
   `HarborRunnerTarget` and metrics server-side. The generic job contract must
   not be exposed directly to the sandbox: it currently accepts
   `agent_import_path` and bundled metric implementations. The exposed
   `--mode remote` option also exits as unimplemented, and the Docker preflight
   is still an unconditional local check.
2. A Harbor task image. The shipped `nmp-cpu-tasks` image does not install the
   `nemo-evaluator-sdk[harbor]` extra or Docker CLI.
3. A dedicated job execution profile that grants only that worker Docker
   access. The standard CPU task profile does not mount the socket.
4. Fileset materialization for the Harbor dataset and candidate bundle. The
   current runner expects local paths inside the worker.
5. A trusted candidate adapter. `agent_import_path` currently imports the
   candidate's Python wrapper in the Docker-owning worker process. LLM-mutated
   code must instead be treated as data and uploaded into Harbor's task
   container by a fixed, allowlisted adapter.

Even a deterministic worker with `/var/run/docker.sock` remains host-root
equivalent if compromised. "Only Harbor tasks" therefore requires a narrow
request schema plus validation/authorization of Docker operations; the socket
mount alone is not that control.

This policy also deliberately supports an uploaded local workspace only. Git
clone, registry download, and winner publication need separately scoped
OpenShell provider policies; they are not granted by the prototype's single
NeMo Platform endpoint.
