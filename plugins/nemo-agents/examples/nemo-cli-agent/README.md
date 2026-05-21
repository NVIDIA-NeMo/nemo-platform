# NeMo CLI Agent

`nemo-cli-agent` is a proof-of-concept NeMo Platform reference agent. It uses a NAT wrapper around a DeepAgents graph to help users operate NeMo Platform through natural language and the `nemo` CLI.

## Invoke

```bash
export NEMO_DEFAULT_INFERENCE_BASE_URL=https://inference-api.nvidia.com/v1
export NEMO_DEFAULT_INFERENCE_API_KEY=nvapi-...
export NEMO_DEFAULT_MODEL=nvidia/nvidia/nemotron-3-super-v3
```

The workflow reads these variables from `nemo-cli-agent.yml` and passes them to
NAT's OpenAI-compatible LLM provider.

The fastest path is the bundled `nemo ask` shortcut:

```bash
nemo ask "load the nemo cli skills"
nemo ask "list all my workspaces"
```

`nemo ask` is registered as a top-level command via the `nemo.cli` plugin hook and dispatches to this example agent.

Or run via the standard agent invocation from the repository root:

```bash
nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-cli-agent/nemo-cli-agent.yml \
  --input "list all my workspaces"
```

On first run, the DeepAgents runtime installs the NeMo CLI skills into `.agents/skills/`. `AGENTS.md` stays portable for Cursor and other harnesses; `DEEP_AGENTS.md` adds the runtime-specific instructions for the bundled LangChain DeepAgents graph.

Or register it as a platform-managed agent:

```bash
nemo agents create \
  --name nemo-cli-agent \
  --agent-config plugins/nemo-agents/examples/nemo-cli-agent/nemo-cli-agent.yml
nemo agents deploy --agent nemo-cli-agent
nemo agents invoke --agent nemo-cli-agent --input "show me what is running"
```

Operations that call the Platform API still require the local platform to be running and inference to be configured.
