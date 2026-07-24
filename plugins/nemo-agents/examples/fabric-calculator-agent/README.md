# Fabric Calculator Agent

This example runs the same agent in two modes:

- `agent.yaml` has no MCP servers. Codex answers the calculation itself.
- `profiles/with-mcp.yaml` adds the toy calculator in `mcps/` as a
  harness-native MCP stdio server. Codex must call the calculator tool.

Both modes write ATIF trajectories and ATOF events through NeMo Relay so the
tool call can be verified independently of the final answer.

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

## Run without MCP

Remove old telemetry first so this run is easy to identify:

```bash
rm -rf plugins/nemo-agents/examples/fabric-calculator-agent/artifacts

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/fabric-calculator-agent/agent.yaml \
  --input "What is 12 multiplied by 8?"
```

The response should report `96`. No MCP server is configured in this mode.

## Run with the MCP profile

```bash
rm -rf plugins/nemo-agents/examples/fabric-calculator-agent/artifacts

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/fabric-calculator-agent/agent.yaml \
  --profile plugins/nemo-agents/examples/fabric-calculator-agent/profiles/with-mcp.yaml \
  --input "What is 12 multiplied by 8?"
```

The response should again report `96`, this time after a `multiply` MCP tool
call.

## Check telemetry

List the generated files:

```bash
find plugins/nemo-agents/examples/fabric-calculator-agent/artifacts/relay \
  -maxdepth 3 -type f -print
```

Inspect all tool calls captured in the ATIF trajectory:

```bash
find plugins/nemo-agents/examples/fabric-calculator-agent/artifacts/relay \
  -name '*.atif.json' \
  -exec jq -c \
    '.steps[]? | .tool_calls[]? | {function_name, arguments}' {} +
```

With the base config this prints nothing. With the MCP profile, the output
includes a calculator `multiply` call and its arguments. The
`events.atof.jsonl` file in the same runtime directory contains the lower-level
event stream if deeper debugging is needed.

If Fabric reports that it cannot import `nemo_fabric_adapters`, confirm the
environment is activated rather than only placing `.venv/bin` on `PATH`:

```bash
test "$VIRTUAL_ENV" = "$PWD/.venv"
python -c "import nemo_fabric_adapters.codex.adapter; print('Codex adapter ready')"
```
