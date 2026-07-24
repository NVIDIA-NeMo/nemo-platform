# Fabric Calculator Agent

This example provides two complete Platform-owned agent configurations:

| Config | Harness | Calculator MCP |
| --- | --- | --- |
| `configs/agent.yaml` | Codex | Disabled |
| `configs/agent_with_mcp.yaml` | Codex | Enabled |

The MCP variant exposes the toy calculator in `mcps/` as a harness-native
stdio server. Both variants write ATIF trajectories and ATOF events through
NeMo Relay so their behavior can be compared from telemetry.

Generated runtime state and telemetry are stored under `.tmp/`.

## Install

Run from the repository root:

```bash
uvx uv@0.9.14 sync \
  --package nemo-agents-plugin \
  --package nemo-agents-example-fabric-calculator \
  --extra fabric

source .venv/bin/activate
```

The Codex and NeMo Relay CLIs must also be on `PATH`. Authenticate Codex if
needed:

```bash
npm install -g @openai/codex
codex login
codex login status
```

To build NeMo Relay from a sibling checkout:

```bash
export NEMO_RELAY_ROOT="$PWD/../nemo-relay"
export NEMO_RELAY_INSTALL_ROOT="${VIRTUAL_ENV:-$PWD/.nemo-relay}"
cargo install --path "$NEMO_RELAY_ROOT/crates/cli" \
  --root "$NEMO_RELAY_INSTALL_ROOT" \
  --locked
export PATH="$NEMO_RELAY_INSTALL_ROOT/bin:$PATH"
nemo-relay --help
```

## Run Codex without MCP

Remove telemetry from a previous run:

```bash
rm -rf plugins/nemo-agents/examples/fabric-calculator-agent/.tmp
```

Invoke the base config:

```bash
nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/fabric-calculator-agent/configs/agent.yaml \
  --input "What is 12 multiplied by 8?"
```

The response should report `96`. No MCP server is configured in this variant.

## Run Codex with MCP

```bash
rm -rf plugins/nemo-agents/examples/fabric-calculator-agent/.tmp

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/fabric-calculator-agent/configs/agent_with_mcp.yaml \
  --input "What is 12 multiplied by 8?"
```

The response should report `96` after a calculator `multiply` tool call.

## Check telemetry

List the generated files:

```bash
find plugins/nemo-agents/examples/fabric-calculator-agent/.tmp/artifacts/relay \
  -maxdepth 3 -type f -print
```

Inspect all tool calls captured in the ATIF trajectory:

```bash
find plugins/nemo-agents/examples/fabric-calculator-agent/.tmp/artifacts/relay \
  -name '*.atif.json' \
  -exec jq -c \
    '.steps[]? | .tool_calls[]? | {function_name, arguments}' {} +
```

The base Codex config prints no tool calls. The MCP config includes a
calculator `multiply` call and its arguments. The `events.atof.jsonl` file in
the same runtime directory contains the lower-level event stream.

If Fabric reports that it cannot import `nemo_fabric_adapters`, confirm the
Platform environment is activated rather than only placing `.venv/bin` on
`PATH`:

```bash
test "$VIRTUAL_ENV" = "$PWD/.venv"
python -c "import nemo_fabric_adapters.codex.adapter; print('Codex adapter ready')"
```
