# Calculator Agent Examples

This directory contains two implementations of the calculator demo:

- `src/calculator_agent/calculator-agent.yml` is the NVIDIA NeMo Agent Toolkit
  (NAT) workflow used for Platform-managed deployment.
- `fabric/agent.yaml` is a Platform-owned `nemo-agents-spec-v1` config that runs
  through NeMo Fabric and the Codex adapter.

The Fabric variant is intentionally a local, one-shot example. It demonstrates
the `nemo agents invoke --agent-config` path added for Fabric-backed agents; it
does not register or deploy the agent through the Platform gateway.

## Run the Fabric calculator

Run these commands from the repository root. The repository requires
`uv>=0.9.14,<0.10.0`, so the commands select that version explicitly:

```bash
uvx uv@0.9.14 pip install \
  --python .venv/bin/python \
  -e "plugins/nemo-agents[fabric]"

source .venv/bin/activate
```

Authenticate Codex if needed:

```bash
npm install -g @openai/codex
codex login
codex login status
```

Invoke the agent:

```bash
nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/calculator-agent/fabric/agent.yaml \
  --input "What is 12 multiplied by 8?"
```

The successful response has `status: "succeeded"` and reports `96`. Additional
examples:

```bash
nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/calculator-agent/fabric/agent.yaml \
  --input "Add 15.5, 20, and 4.5."

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/calculator-agent/fabric/agent.yaml \
  --input "Is 42 greater than 17?"
```

The invocation sends the prompt and agent instructions to the model provider
used by the authenticated Codex session.

## How the Fabric variant works

NeMo Platform loads `fabric/agent.yaml`, translates it into an in-memory
`FabricConfig`, and starts an ephemeral Codex runtime through NeMo Fabric. The
runtime uses `fabric/workspace` as its working directory.

The example bundles the `0.1.0a1` Codex adapter descriptor under
`fabric/adapters`. The alpha Fabric planner discovers descriptors from the
config's `base_dir`, but does not yet discover the copy installed under the
virtual environment's shared-data directory. The adapter implementation still
comes from the separately installed `nemo-fabric-adapters-codex` package.

The config's Codex developer instructions require the agent to invoke
`workspace/calculator.py` instead of doing arithmetic itself. The script
supports the same calculator operations as the NAT demo: `add`, `subtract`,
`multiply`, `divide`, and `compare`.

This is harness-native tool execution through Codex's workspace and terminal
capabilities. Mapping Platform tools or NAT function groups into normalized
Fabric MCP/tool configuration is outside this initial example.

## Test

Run the focused local tests without invoking a model:

```bash
uvx uv@0.9.14 run --frozen pytest -q \
  plugins/nemo-agents/tests/unit/test_fabric_calculator_example.py \
  plugins/nemo-agents/tests/unit/test_fabric_translator.py
```
