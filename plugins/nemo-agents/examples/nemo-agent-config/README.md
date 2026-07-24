# Fabric-Backed Agent Config

These Platform-owned configs invoke Codex, Hermes, or NAT through NeMo Fabric.
Run the commands below from the repository root.

Fabric dependencies are currently optional so the default workspace does not
force other Fabric consumers onto the prerelease SDK API before they migrate.
Install them explicitly before local Fabric smoke tests:

```bash
uv pip install -e "plugins/nemo-agents[fabric]"
```

## NAT

The plugin install includes the Platform-packaged calculator and email phishing
NAT components. Their workflow YAML remains the source of truth; the adjacent
`agent.yaml` only selects the Platform-owned NAT Fabric adapter.

Run the calculator workflow:

```bash
export NVIDIA_API_KEY="<your NVIDIA API key>"

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/calculator-agent/fabric/agent.yaml \
  --input "What is 12 multiplied by 8?"
```

Run the email phishing analyzer:

```bash
export NVIDIA_API_KEY="<your NVIDIA API key>"

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/email-phishing-analyzer/fabric/agent.yaml \
  --input "Subject: Verify your account. Send your password immediately."
```

To use another NAT workflow, keep its config and relative resources under the
Platform `agent.yaml` directory and set `harness.settings.config_file` to that
workflow. Install any package that exposes workflow-specific `nat.components`
into the same Python environment. Keep those packages on the same NAT release
as the `nvidia-nat-*` packages installed by NeMo Agents.

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
uv venv --python 3.12 .venv-hermes
uv --no-config pip install \
  --python .venv-hermes/bin/python \
  "nemo-fabric-adapters-hermes==0.1.0a20260724" \
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
