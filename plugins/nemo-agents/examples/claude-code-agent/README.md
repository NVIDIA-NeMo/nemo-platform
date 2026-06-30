# Claude Code Agent

This example configures the vendored Claude Code workflow adapter shipped with
the `nemo-agents` plugin.

The adapter is already packaged with `nemo-agents`; do not install a separate
NAT Claude Code adapter package.

## Prerequisites

Install Claude Code and configure authentication in the same environment that
will run `nemo`:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
claude auth login
claude auth status
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
  --name claude-code-agent \
  --agent-config plugins/nemo-agents/examples/claude-code-agent/claude-code-agent.yml

nemo agents deploy --agent claude-code-agent
```

Invoke it with a read-only prompt first:

```bash
nemo agents invoke \
  --agent claude-code-agent \
  --input "Read pyproject.toml and say only the project name. Do not edit files."
```

The config uses `permission_mode: plan` and denies write-capable Claude Code
tools by default so the first smoke test can inspect files without editing the
workspace.
