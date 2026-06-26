# Cursor Agent

This example configures the vendored Cursor workflow adapter shipped with the
`nemo-agents` plugin.

The adapter is already packaged with `nemo-agents`; do not install a separate
NAT Cursor adapter package.

## Prerequisites

Install the Cursor Agent CLI and configure authentication in the same
environment that will run `nemo`:

```bash
curl https://cursor.com/install -fsS | bash
cursor-agent login
cursor-agent status
```

For non-interactive environments, set `CURSOR_API_KEY` before starting `nemo`.

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
  --name cursor-agent \
  --agent-config plugins/nemo-agents/examples/cursor-agent/cursor-agent.yml

nemo agents deploy --agent cursor-agent
```

Invoke it with a read-only prompt first:

```bash
nemo agents invoke \
  --agent cursor-agent \
  --input "Read pyproject.toml and say only the project name. Do not edit files."
```

The config uses `mode: plan` by default. It also sets `trust_workspace: true`
because Cursor Agent requires workspace trust for headless `--print` runs.
