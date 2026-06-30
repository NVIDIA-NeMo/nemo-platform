# Codex Agent

This example configures the vendored Codex workflow adapter shipped with the
`nemo-agents` plugin.

The adapter is already packaged with `nemo-agents`; do not install a separate
NAT Codex adapter package.

## Prerequisites

Install the Codex CLI and configure authentication in the same environment that
will run `nemo`:

```bash
npm install -g @openai/codex
codex login
codex login status
```

Install Rust so `cargo` is available on `PATH`, then install the NeMo Relay CLI.
If `VIRTUAL_ENV` is set, the commands below install into that environment;
otherwise they install into a local `.nemo-relay` directory. The `PATH` export
makes the installed `nemo-relay` binary available for the smoke test:

```bash
git clone git@github.com:NVIDIA/NeMo-Relay.git
export NEMO_RELAY_ROOT="$PWD/NeMo-Relay"
export NEMO_RELAY_INSTALL_ROOT="${VIRTUAL_ENV:-$PWD/.nemo-relay}"
cargo install --path "$NEMO_RELAY_ROOT/crates/cli" --root "$NEMO_RELAY_INSTALL_ROOT" --locked
export PATH="$NEMO_RELAY_INSTALL_ROOT/bin:$PATH"
nemo-relay --help
```

## Run on NeMo Platform

From the `nemo-platform` repository root, create and deploy the example agent:

```bash
nemo agents create \
  --name codex-agent \
  --agent-config plugins/nemo-agents/examples/codex-agent/codex-agent.yml

nemo agents deploy --agent codex-agent
```

Invoke it with a read-only prompt first:

```bash
nemo agents invoke \
  --agent codex-agent \
  --input "Read pyproject.toml and say only the project name. Do not edit files."
```

The config uses `sandbox_mode: read-only` and `approval_policy: never` by
default so the first smoke test can inspect files without editing the workspace.
