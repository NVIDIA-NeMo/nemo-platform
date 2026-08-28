<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Sandbox rho-agent Harbor runs

Pre-bake rho-agent into a Docker image, extend it per task, and restrict trial
network access with Harbor's Docker egress sidecar. Works on macOS when Docker
Desktop runs the Linux VM (Harbor probes nftables support inside that VM).

## One-time agent image build

From the nemo-platform checkout:

```bash
bash plugins/nemo-eval-author/walkthrough/rho-agent/build_agent_image.sh
```

This tags `nemo-eval-author/rho-agent-harbor:04b9cfa1c940` with rho-agent
@ `04b9cfa1` and the ATIF compat shim baked in. The build uses host network
access; trial containers do not reinstall the agent.

## Prepare a walkthrough workspace

```bash
source plugins/nemo-eval-author/walkthrough/env
mkdir -p tmp/rho-agent-walkthrough

git clone https://github.com/smith-nathanh/rho-agent.git tmp/rho-agent-walkthrough/rho-agent
git -C tmp/rho-agent-walkthrough/rho-agent checkout "$RHO_REVISION"

cp plugins/nemo-eval-author/walkthrough/rho-agent/rho_harbor_agent.py tmp/rho-agent-walkthrough/
cp plugins/nemo-eval-author/walkthrough/rho-agent/rho_atif_compat.py tmp/rho-agent-walkthrough/

uv run --with pyyaml \
  plugins/nemo-eval-author/walkthrough/rho-agent/prepare_sandbox.py \
  prepare-workspace tmp/rho-agent-walkthrough
```

This command:

1. Clones rho-agent @ `04b9cfa1` into `rho-agent/` when missing.
2. Builds the agent image when missing (`--skip-build` to opt out).
3. Copies bundled `task-0` from `walkthrough/assets/rho-agent/task-0/` into
   `.eval-author/sandbox/task-0/` with the sandbox Dockerfile and network policy.
4. Writes `.eval-author/baseline-job.yaml`.

Check egress support before a long demo (uses Harbor's own daemon kernel probe):

```bash
uv run --with pyyaml --with harbor \
  plugins/nemo-eval-author/walkthrough/rho-agent/prepare_sandbox.py check-egress
```

## Network policy

The walkthrough demo targets **macOS with Docker Desktop**. Harbor trials run in
Docker Desktop's Linux VM with phase policy:

| Phase | Policy |
|---|---|
| Environment baseline | `network_mode = "no-network"` |
| Agent run | `network_mode = "allowlist"` for the inference hostname only |
| Verifier | inherits no-network baseline |

If `check-egress` reports `"supported": false`, `prepare-workspace` fails. There is
no public-network fallback.

Harbor requires `CONFIG_NFT_FIB_INET=y|m` in the **Docker daemon** kernel.
`CONFIG_NFT_FIB_IPV4` alone is not sufficient. On macOS, Docker Desktop **4.86.0
or later** ships the required kernel support; OrbStack and Colima (current
releases) also work. The check delegates to Harbor's
`DockerEnvironment._egress_control_kernel_support()` when the `harbor` package is
installed.

## Adapter behavior

`rho_harbor_agent.py` expects `/rho-agent/.venv/bin/python` in the task image.
If it is missing, setup fails fast with instructions to build the walkthrough
image. Legacy unrestricted trials remain available:

```bash
export RHO_HARBOR_ALLOW_RUNTIME_INSTALL=1
```

Pass `--legacy` to `prepare_sandbox.py prepare-workspace` to reproduce the old
runtime-install / public-network path.

## Quick start CLI (sandbox default)

```bash
uv run \
  --with-requirements plugins/nemo-eval-author/walkthrough/quick-start-cli/requirements.txt \
  --with-requirements plugins/nemo-eval-author/skills/eval-author-audit/requirements.txt \
  --with pyyaml \
  python plugins/nemo-eval-author/walkthrough/quick-start-cli/cli.py \
  --agent=cursor \
  --workspace tmp/rho-agent-walkthrough
```

Re-run the same command to get an in-app prompt when prior artifacts exist.
