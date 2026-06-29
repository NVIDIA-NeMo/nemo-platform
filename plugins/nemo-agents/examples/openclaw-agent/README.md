# OpenClaw Agent

This example configures the vendored OpenClaw workflow adapter shipped with the
`nemo-agents` plugin.

The adapter is already packaged with `nemo-agents`; do not install a separate
NAT OpenClaw adapter package.

## Prerequisites

Install the OpenClaw CLI and configure authentication in the same environment
that will run `nemo`:

```bash
npm install -g openclaw@2026.6.10
openclaw --version
openclaw onboard
openclaw doctor
```

The example config uses OpenClaw Gateway mode because Relay telemetry is
provided by the NeMo Relay OpenClaw plugin running inside Gateway:

```bash
openclaw config set gateway.mode local
openclaw config set gateway.bind loopback
openclaw config set gateway.auth.mode token
openclaw config set gateway.auth.token "$(openssl rand -hex 32)"
openclaw config validate
```

Clone the NeMo Relay source locally, then build and link the OpenClaw plugin.
This requires Node.js and npm in addition to the OpenClaw CLI:

```bash
git clone git@github.com:NVIDIA/NeMo-Relay.git
export NEMO_RELAY_ROOT="$PWD/NeMo-Relay"
git -C "$NEMO_RELAY_ROOT" checkout 19a537ddb045d853304f0f6a43dbc5346ad84233
npm install --prefix "$NEMO_RELAY_ROOT" --workspace=nemo-relay-node --workspace=nemo-relay-openclaw --ignore-scripts
npm run --prefix "$NEMO_RELAY_ROOT" build --workspace=nemo-relay-node
npm run --prefix "$NEMO_RELAY_ROOT" build --workspace=nemo-relay-openclaw
openclaw plugins install --link "$NEMO_RELAY_ROOT/integrations/openclaw"
```

Install the OpenClaw Codex plugin and authenticate it if you want the example to
use OpenClaw's Codex app-server runtime:

```bash
openclaw plugins install @openclaw/codex@2026.6.10
openclaw models auth login --provider openai
openclaw models status
```

Configure OpenClaw to use a Codex-backed model by default:

```bash
openclaw config set 'plugins.entries["codex"].enabled' true --strict-json
openclaw config set 'agents.defaults.model.primary' openai/gpt-5.5
openclaw config set 'agents.defaults.models["openai/gpt-5.5"].agentRuntime.id' codex
openclaw config validate
```

The example config uses the OpenClaw default model configured above.

Enable the `nemo-relay` plugin and choose an absolute ATIF output directory:

```bash
export OPENCLAW_ATIF_DIR="$(pwd)/.tmp/nemo-relay-openclaw-atif"
mkdir -p "$OPENCLAW_ATIF_DIR"
openclaw config set 'plugins.entries["nemo-relay"].enabled' true --strict-json
openclaw config set 'plugins.entries["nemo-relay"].hooks.allowConversationAccess' true --strict-json
openclaw config set 'plugins.entries["nemo-relay"].config.plugins.components[0].kind' observability
openclaw config set 'plugins.entries["nemo-relay"].config.plugins.components[0].config.atif.enabled' true --strict-json
openclaw config set 'plugins.entries["nemo-relay"].config.plugins.components[0].config.atif.output_directory' "$OPENCLAW_ATIF_DIR"
openclaw config validate
```

Start Gateway in a separate terminal and leave it running while the platform
deployment invokes OpenClaw:

```bash
OPENCLAW_CODEX_APP_SERVER_MODE=guardian \
OPENCLAW_CODEX_APP_SERVER_APPROVAL_POLICY=on-request \
OPENCLAW_CODEX_APP_SERVER_SANDBOX=workspace-write \
openclaw gateway run
```

In the terminal that runs `nemo`, verify that Gateway loaded the plugin:

```bash
openclaw plugins inspect nemo-relay --runtime --json
openclaw gateway call nemoRelay.status --json
```

## Run on NeMo Platform

From the `nemo-platform` repository root, create and deploy the example agent:

```bash
nemo agents create \
  --name openclaw-agent \
  --agent-config plugins/nemo-agents/examples/openclaw-agent/openclaw-agent.yml

nemo agents deploy --agent openclaw-agent
```

Invoke it with a read-only prompt first:

```bash
nemo agents invoke \
  --agent openclaw-agent \
  --input "Read pyproject.toml and say only the project name. Do not edit files."
```

The config uses `local: false` so OpenClaw runs through Gateway and the
`nemo-relay` plugin can observe the agent run. If you only need a direct
OpenClaw run without Relay telemetry, set `local: true`.
