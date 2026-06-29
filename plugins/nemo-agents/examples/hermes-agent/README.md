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
The `cargo install` command below writes `nemo-relay` into the active virtual
environment when `VIRTUAL_ENV` is set, or into `.venv` otherwise. After
activating that environment, `nemo-relay --help` should resolve on `PATH` for
the smoke test:

```bash
git clone git@github.com:NVIDIA/NeMo-Relay.git
export NEMO_RELAY_ROOT="$PWD/NeMo-Relay"
cargo install --path "$NEMO_RELAY_ROOT/crates/cli" --root "${VIRTUAL_ENV:-.venv}" --locked
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
