# Safe Research Agent Guardrails PoC

This PoC demonstrates how the `nemo-guardrails` inference middleware plugin can
guardrail a tool-calling research agent without baking the policy into the
agent prompt.

The agent is intentionally small and policy-neutral:

- `clock` uses NAT's built-in `current_datetime` tool.
- `wiki` uses NAT's built-in `wiki_search` tool.
- The agent prompt tells the model to use both tools when appropriate.
- The model path goes through a guarded VirtualModel.
- The Guardrails config centrally allows `clock` calls and blocks `wiki` calls
  before NAT can execute them.
- Non-streaming OpenAI `tool_calls` are checked before NAT executes tools.
  Streaming tool-call rails are intentionally left as follow-up work.

## Files

- `agentic-guardrails-poc.yml` - NAT ReAct agent config with native tool calling enabled.
- `tool-rails-config.json` - deterministic GuardrailConfig data for tool rails.
- `setup.sh` - creates the GuardrailConfig, guarded VirtualModel, and agent entity.

## Prerequisites

Start NeMo Platform first and make sure the backend model entity exists.

The setup script defaults to:

```bash
BACKEND_MODEL=default/nvidia-nemotron-3-nano-30b-a3b
WORKSPACE=default
```

Override `BACKEND_MODEL` if your local platform uses a different model entity.

## Setup

```bash
agents/agentic-guardrails-poc/setup.sh
```

To deploy the managed agent as part of setup:

```bash
DEPLOY_AGENT=1 agents/agentic-guardrails-poc/setup.sh
```

## Demo Story

The demo shows the same agent under a centralized tool policy:

- Agent capability: both `clock` and `wiki` are available in the NAT config.
- Central policy: only `clock` is allowed in `tool-rails-config.json`.
- Enforcement point: the Guardrails plugin runs at the VirtualModel boundary.

The blocked case is successful only when NAT does not execute `wiki`.

## Demo Commands

Allowed tool call:

```bash
uv run nemo agents invoke \
  --agent-config agents/agentic-guardrails-poc/agentic-guardrails-poc.yml \
  --input "What time is it right now?"
```

Expected: the output includes `Calling tools: clock`, then a final answer with
the current time.

Blocked tool call:

```bash
uv run nemo agents invoke \
  --agent-config agents/agentic-guardrails-poc/agentic-guardrails-poc.yml \
  --input "Look up NVIDIA on Wikipedia and summarize it."
```

Expected: the output does not include `Calling tools: wiki`. The model may
explain that it cannot complete the Wikipedia lookup, but the key signal is that
the `wiki` tool never executes.

## How It Works

`setup.sh` creates a guarded VirtualModel named
`default/agentic-guardrails-poc-model` with `default_model_entity` set to
`BACKEND_MODEL`. The agent YAML points its OpenAI LLM at that
workspace-qualified VirtualModel:

```yaml
model_name: default/agentic-guardrails-poc-model
```

This PoC disables streaming in the NAT OpenAI client because the first
implementation only supports non-streaming tool-call rails. Streaming tool-call
rails are planned as follow-up work.

The GuardrailConfig enables:

- `tool_output`: `check tool allowlist` and `check tool schema`
- `tool_input`: `check tool result linkage`

The allowlist contains only `clock`, so tool calls to `wiki` are refused before
tool execution.
