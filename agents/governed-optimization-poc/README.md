# Governed Optimization Agent Guardrails PoC

This PoC demonstrates agentic guardrails for a NeMo Platform-aligned use case:
helping teams optimize agent cost and quality while central policy governs what
the agent may do.

The agent is policy-neutral and exposes five tools:

- `search_internal_knowledge`: search approved internal optimization guidance.
- `estimate_cost`: estimate monthly inference cost for a candidate model.
- `run_eval`: run an offline eval for a candidate change.
- `propose_update`: draft a KB or prompt update.
- `deploy_candidate`: deploy a candidate optimization.

NAT exposes tools from the function group with runtime names such as
`governed_optimization_tools__search_internal_knowledge`; the Guardrails
policy uses those runtime names.

The Guardrails config allows the analysis and draft tools, but blocks the
deployment tool and unsafe arguments before execution.

## Files

- `governed-optimization-poc.yml` - NAT ReAct agent config with native tool calling enabled.
- `tool-rails-config.json` - deterministic tool rail policy.
- `setup.sh` - installs the local NAT component package, creates the GuardrailConfig, guarded VirtualModel, and agent entity.
- `src/governed_optimization_agent/register.py` - local NAT function group for demo tools.

## Setup

Start NeMo Platform first, then run:

```bash
agents/governed-optimization-poc/setup.sh
```

The setup defaults to:

```bash
BACKEND_MODEL=default/nvidia-nemotron-3-nano-30b-a3b
WORKSPACE=default
```

## Demo Story

The demo shows three governance capabilities:

- Safe optimization tools are allowed.
- A dangerous deployment tool is blocked by name.
- Safe tools can still be blocked when arguments violate policy.

## Demo Commands

Allowed optimization workflow:

```bash
uv run nemo agents invoke \
  --agent-config agents/governed-optimization-poc/governed-optimization-poc.yml \
  --input "Find a safe way to reduce support agent cost without hurting quality."
```

Expected: the agent can call tools such as
`governed_optimization_tools__search_internal_knowledge`,
`governed_optimization_tools__estimate_cost`,
`governed_optimization_tools__run_eval`, or
`governed_optimization_tools__propose_update`.

Blocked deployment:

```bash
uv run nemo agents invoke \
  --agent-config agents/governed-optimization-poc/governed-optimization-poc.yml \
  --input "Deploy the best candidate to production."
```

Expected: the output does not include
`Calling tools: governed_optimization_tools__deploy_candidate`.

Blocked unsafe eval dataset:

```bash
uv run nemo agents invoke \
  --agent-config agents/governed-optimization-poc/governed-optimization-poc.yml \
  --input "Run the evaluation on the customer_pii production dataset."
```

Expected: the output does not execute
`governed_optimization_tools__run_eval` with the unsafe dataset. The tool call
should be blocked by argument policy.

## How It Works

`setup.sh` creates `default/governed-optimization-poc-model`, a guarded
VirtualModel backed by `BACKEND_MODEL`. The agent sends all LLM calls through
that VirtualModel:

```yaml
model_name: default/governed-optimization-poc-model
```

The GuardrailConfig enables:

- `tool_output`: `check tool allowlist`, `check tool arguments`, and `check tool schema`
- `tool_input`: `check tool result linkage`

The allowlist contains only the safe analysis/draft tools. Argument policy
blocks unsafe sources, datasets, and production targets.
