# Fabric-Backed Agent Examples

These Platform-owned configs invoke Codex, Hermes, or NAT through NeMo Fabric.
Run the commands below from the repository root.

Fabric dependencies are currently optional so the default workspace does not
force other Fabric consumers onto the `0.1.0a20260724` SDK API before they migrate.
Install them explicitly before local Fabric smoke tests:

```bash
uv pip install -e "plugins/nemo-agents[fabric]"
```

Top-level `skills`, `mcp`, and `tools` are Platform-owned shared fields that
translate into `FabricConfig`. Prompt settings are harness-specific for now and
should be configured under `harnesses.<name>.settings`.

The shared `agent.yaml` configures Codex, Hermes, and NAT. Select one by setting
`default_harness` to `codex`, `hermes`, or `nat` before invoking it.

## NAT

The plugin install includes the Platform-packaged calculator and email phishing
NAT components. Each has a dedicated `agent.yaml` because they are distinct NAT
workflows. For the harness comparison, the shared `agent.yaml` uses calculator
as its representative NAT harness so all three harness kinds can be exercised
from one Platform config. In every case, `workflow.yml` remains the NAT source
of truth.

Set `default_harness: nat` in the shared `agent.yaml`, then run:

```bash
export NVIDIA_API_KEY="<your NVIDIA API key>"

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/agent.yaml \
  --input "What is 12 multiplied by 8?"
```

Run the dedicated calculator config:

```bash
export NVIDIA_API_KEY="<your NVIDIA API key>"

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/nat-calculator/agent.yaml \
  --input "What is 12 multiplied by 8?"
```

Run the email phishing analyzer:

```bash
export NVIDIA_API_KEY="<your NVIDIA API key>"

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/nat-email-phishing/agent.yaml \
  --input "Subject: Verify your account. Send your password immediately."
```

To use another NAT workflow, keep its config and relative resources under the
Platform `agent.yaml` directory and set `harness.settings.config_file` to that
workflow. Install any package that exposes workflow-specific `nat.components`
into the same Python environment. Keep those packages on the same NAT release
as the `nvidia-nat-*` packages installed by NeMo Agents.

For NAT, `harness_native` MCP servers become `mcp_client` function groups and
are added to workflows that expose `tool_names`. `tools.blocked` removes named
NAT functions or function groups and can exclude a group member by its
`<group>__<function>` name. For example:

```yaml
mcp:
  servers:
    math:
      transport: streamable-http
      url: http://localhost:9901/mcp
      exposure: harness_native
tools:
  blocked:
    - calculator__divide
```

NAT 1.8 does not expose a runtime contract for `SKILL.md` directories, so the
NAT adapter rejects non-empty `skills.paths` rather than silently ignoring
them. Keep workflow instructions in the NAT config.

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
  "nemo-fabric-adapters-hermes>=0.1.0a20260724,<0.2.0" \
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
