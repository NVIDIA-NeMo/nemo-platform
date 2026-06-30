# Hermes Agent

This example configures the vendored Hermes workflow adapter shipped with the
`nemo-agents` plugin.

The adapter is already packaged with `nemo-agents`; do not install a separate
NAT Hermes adapter package.

## Prerequisites

Install and configure Hermes Agent in the same environment that will run
`nemo`. The workflow config launches Hermes with `uvx`, so a global `hermes`
executable is not required:

```bash
uvx --from hermes-agent hermes setup
uvx --from hermes-agent hermes auth
uvx --from hermes-agent hermes model
uvx --from hermes-agent hermes status
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
  --name hermes-agent \
  --agent-config plugins/nemo-agents/examples/hermes-agent/hermes-agent.yml

nemo agents deploy --agent hermes-agent
```

Invoke it with a read-only prompt first:

```bash
nemo agents invoke \
  --agent hermes-agent \
  --input "Read pyproject.toml and say only the project name. Do not edit files."
```

`uvx --from hermes-agent hermes status` should show a concrete model and an
authenticated provider before a live model-backed workflow run.
