# Fabric-Backed Agent Config

This Platform-owned config invokes Codex or Hermes through NeMo Fabric. Run the
commands below from the repository root.

Fabric dependencies are currently optional so the default workspace does not
force other Fabric consumers onto the `0.1.0a1` SDK API before they migrate.
Install them explicitly before local Fabric smoke tests:

```bash
uv pip install -e "plugins/nemo-agents[fabric]"
```

## Codex

Authenticate Codex, leave `default_harness: codex` in `agent.yaml`, and run:

```bash
npm install -g @openai/codex
codex login

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/agent.yaml \
  --input "Reply with exactly: platform fabric works"
```

## Hermes

Hermes Agent has dependencies that conflict with the Platform environment, so
install it with the Fabric adapter in a separate Python 3.12 environment:

```bash
uvx uv@0.9.14 venv --python 3.12 .venv-hermes
uvx uv@0.9.14 --no-config pip install \
  --python .venv-hermes/bin/python \
  "nemo-fabric-adapters-hermes==0.1.0a1" \
  "hermes-agent==0.19.0"

export HERMES_ADAPTER_PYTHON="$PWD/.venv-hermes/bin/python"
export NVIDIA_API_KEY="<your NVIDIA API key>"
```

Temporarily set `default_harness: hermes` in `agent.yaml`, then run:

```bash
nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/agent.yaml \
  --input "Reply with exactly: platform hermes works"
```
