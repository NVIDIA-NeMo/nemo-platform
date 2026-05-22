# About Agents

<a id="agents"></a>

An agent on {{platform_name}} is a workflow that calls tools, talks to models
through the local platform, and runs as a managed service you can deploy,
invoke, evaluate, and optimize as a unit. Agents are defined as NeMo Agent
Toolkit (NAT) workflows and are managed through the `nemo agents` command
group.

## About NeMo Agent Toolkit

NVIDIA NeMo Agent Toolkit is a flexible, lightweight, and unifying library
that allows you to easily connect existing enterprise agents to data sources
and tools across any framework.

{{platform_name}} uses NAT as the runtime wrapper around your agent so the
platform can deploy it, evaluate it, optimize it, and route its model traffic
through shared infrastructure. For the toolkit itself, see the
[NeMo Agent Toolkit documentation](https://docs.nvidia.com/nemo/agent-toolkit/latest/).

## Agent Definition

An agent's behavior is described by a NAT workflow YAML with three top-level sections:

| Section | Purpose | Examples |
|---------|---------|----------|
| `functions` | Tools the agent can call | `wiki_search`, `current_datetime`, custom MCP tools |
| `llms` | Model bindings the workflow can reference | OpenAI-compatible endpoints, NIM endpoints |
| `workflow` | The agent type and its wiring | `react_agent`, `tool_calling_agent`, custom NAT workflows |

ReAct is a common agent pattern where the model alternates between a
reasoning step and a tool call until it has enough information to answer. It
is a good default when you want the agent to decide which tool to use next
based on what it has already learned. A minimal ReAct agent looks like this:

```yaml
functions:
  wiki:
    _type: wiki_search
  clock:
    _type: current_datetime

llms:
  llm:
    _type: openai
    api_key: not-used                 # injected at deploy time
    model_name: nvidia-nemotron-3-nano-30b-a3b

workflow:
  _type: react_agent
  tool_names: [wiki, clock]
  llm_name: llm
```

The [Inference Gateway](../run-inference/about.md) is the local platform's
model proxy. Agents send model requests to it instead of to provider APIs
directly, so the platform can resolve model names, attach credentials, and
route through middleware on the agent's behalf. Two conventions apply when a
config targets a deployed agent:

- **Model names use the Inference Gateway entity form**, with slashes and dots converted to hyphens (`nvidia/nemotron-3-nano-30b-a3b` becomes `nvidia-nemotron-3-nano-30b-a3b`). The Inference Gateway resolves the entity to the upstream provider that owns it.
- **Leave `base_url` and `api_key` unset on `openai` and `nim` LLMs.** {{platform_name}} injects an Inference Gateway URL when it deploys the agent, and the gateway retrieves upstream credentials from the secrets service. Setting `base_url` explicitly bypasses both.

## Agent Lifecycle

Agents are managed end-to-end through the `nemo agents` command group:

| Stage | Command | What it does |
|-------|---------|--------------|
| Register | `nemo agents create --name <name> --agent-config <path>` | Store the workflow YAML as an `agent` entity in a workspace. |
| Deploy | `nemo agents deploy --agent <name>` | Start a running service from the stored config. |
| Wait | `nemo agents deployments wait --agent <name>` | Block until the deployment is `running` or `failed`. |
| Invoke | `nemo agents invoke --agent <name> --input "..."` or `nemo agents invoke --agent-config <path> --input "..."` | Send a single request through the Agents gateway or run a local config directly. |
| Evaluate | `nemo agents evaluate run --eval-config <path> --agent <name>` | Run a NAT evaluation against the deployed agent. |
| Optimize | `nemo agents optimize run --optimize-config <path> --agent <name>` | Run NAT parameter or prompt tuning trials against the agent's stored config. |
| Tear down | `nemo agents undeploy --agent <name>` then `nemo agents delete <name>` | Stop the running service and remove the agent entity. |

To run a workflow YAML directly without registering it on the platform, pass `--agent-config <path>` to `nemo agents invoke` or `nemo agents run`.

## How It Works

A platform-managed agent consists of three components:

1. **The agent entity.** `nemo agents create` stores the workflow YAML as an entity in the workspace. The same configuration can be redeployed, evaluated, or optimized without re-registering it.
1. **The deployment controller.** `nemo agents deploy` passes the stored config to the Agents service controller, which launches a `nat start fastapi` process for it, assigns a port, watches its health, and tears it down on `nemo agents undeploy`.
1. **The Agents gateway.** Client requests reach the agent at `/apis/agents/v2/workspaces/<workspace>/agents/<name>/-/<path>`. The gateway resolves the agent to its current running deployment and proxies the request, including streaming responses. From a client's perspective, the agent is an OpenAI-compatible endpoint owned by {{platform_name}}.

Model traffic from inside the agent process routes back through the Inference Gateway, which resolves model entity names to upstream providers and supplies their credentials. This is why agent configs do not carry `base_url` or `api_key` values — the deployment injects the gateway URL automatically, and the gateway looks up the rest.

A virtual model is a platform-managed wrapper around one or more backend
models. An agent can point at a virtual model entity while the virtual model
handles routing, format translation, and [guardrails](../guardrails/index.md)
behind the scenes — no changes to the agent's workflow YAML required.

### Applying Changes Through Candidate Agents

The Agents v2 API has no in-place patch for a stored agent config. When the
optimize or secure workflows propose a change — a model swap, a routing
split, a guardrailed virtual model — they apply it by creating a sibling
agent with the new config, deploying it, and running an evaluation against
it. The original agent stays untouched until you decide to promote the
candidate.

The sibling-candidate pattern is the recommended way to apply changes: you
always have a baseline to compare against, and you can roll back by
undeploying the candidate.

## Common Tasks

- [Optimize Agents](optimization.md): analyze deployed agents for model routing,
  skill, prompt, and new-model opportunities.
- [Secure Agents](security.md): check guardrail coverage and scan recent
  telemetry for sensitive data.
- [Plugins and Skills](plugins.md): understand how agent, middleware, and
  coding-agent integrations extend the local platform.
- [Agentic Metrics](../evaluator/metrics/agentic.md): evaluate tool use, goal completion, topic adherence, answer accuracy, and trajectories.
- [Agent Configuration](../evaluator/metrics/agent-configuration.md): use agents as online evaluation targets.
