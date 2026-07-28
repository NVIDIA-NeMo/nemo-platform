# Fabric-Backed Agent Examples

These Platform-owned configs invoke Codex, Hermes, or NAT through NeMo Fabric.
Run the commands below from the repository root.

Fabric dependencies are currently optional so the default workspace does not
force other Fabric consumers onto the `0.1.0a20260724` SDK API before they migrate.
Install them explicitly before local Fabric smoke tests:

```bash
uv pip install -e "plugins/nemo-agents[fabric]"
```

Top-level `models`, `skills`, `mcp`, and `tools` are Platform-owned fields that
translate into `FabricConfig`. Prompt settings are harness-specific for now and
should be configured under `harnesses.<name>.settings`.

The shared `agent.yaml` configures Codex, Hermes, and NAT. Select one by setting
`default_harness` to `codex`, `hermes`, or `nat` before invoking it.

## NAT

The plugin install includes the Platform-packaged calculator and email phishing
NAT components. Each has a dedicated `agent.yaml` because they are distinct NAT
workflows. For the harness comparison, the shared `agent.yaml` uses calculator
as its representative NAT harness so all three harness kinds can be exercised
from one Platform config. `agent.yaml` is the only configuration source: the
adapter translates its normalized Fabric model and NAT harness settings into an
in-memory typed NAT configuration.

The initial NAT contract supports `react` and `current_timezone` workflows. A
`react` workflow accepts the Platform-packaged `calculator`,
`current_datetime`, and `email_phishing_analyzer` tools. The adapter maps those
names to NAT functions and function groups; those native details are not part of
the public Platform config.

```yaml
harnesses:
  nat:
    kind: nat
    settings:
      workflow: react
      tools:
        - calculator
        - current_datetime

models:
  default:
    provider: nvidia
    model: nvidia/nemotron-3-nano-30b-a3b
    api_key_env: NVIDIA_API_KEY
    temperature: 0.0
    settings:
      max_tokens: 1024
```

For `react`, the adapter translates `models.default` into NAT's `default` LLM.
The `nvidia` and `nim` providers select NAT's NIM client, while `openai` selects
its OpenAI-compatible client. Provider-specific fields such as `base_url` and
`max_tokens` belong in `models.default.settings`.

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

Unsupported workflow and tool names fail during Platform translation. Expanding
the supported set requires an explicit Platform-to-NAT mapping in the adapter;
the adapter does not accept arbitrary native NAT configuration.

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
them. Put React-specific instructions in
`harnesses.<name>.settings.instructions`.

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
