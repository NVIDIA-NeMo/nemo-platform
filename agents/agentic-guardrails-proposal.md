# Agentic Guardrails Proposal

## Purpose

This proposal captures what we learned while prototyping agentic guardrails in the
NeMo Guardrails plugin. The near-term implementation focuses on tool calls: the
agent's model proposes a tool call, the Inference Gateway runs policy before the
agent executes that tool, and blocked calls are replaced with a refusal response.

The goal is not to claim that tool-call checks are the whole agent safety story.
The goal is to establish the first enforcement primitive for governing agent
actions at the platform boundary.

## What "Agentic Guardrails" Means

Guardrails for a normal chat model usually operate on text:

- Input rails check user messages before the model sees them.
- Output rails check model text before the user sees it.

Agents add more surfaces. A model can now decide to call tools, pass structured
arguments, receive tool results, persist memory, and make later decisions based
on those results. Applying guardrails to agents means checking the full agent
loop: what the agent may perceive, plan, call, execute, remember, and say.

| Component | What it Does |
|---|---|
| User intent | Checks whether the user's request is allowed before planning or tool use. |
| Planning | Constrains goals, decomposition, autonomy level, and allowed workflows. |
| Tool selection | Checks whether the model may call a proposed tool. |
| Tool arguments | Validates proposed arguments for safety and policy compliance. |
| Tool schema | Validates proposed calls against the declared tool contract. |
| Tool results | Checks whether tool results are linked to prior calls and safe for model consumption. |
| Action sequencing | Detects unsafe multi-step behavior that is not obvious from one call. |
| Authorization | Checks user, workspace, environment, or deployment permissions. |
| Execution containment | Constrains allowed actions with sandboxes, scoped credentials, and egress limits. |
| Memory governance | Controls what the agent can read from or write to memory. |
| Final response | Checks the final user-visible answer for safety and correctness. |

The current implementation starts with the most important action boundary:
checking proposed tool calls before execution.

## Problem Scope

The immediate problem is that agents can execute tools based on model output. A
prompt can instruct the model not to call dangerous tools, but prompts are not
policy enforcement. The model may still emit a tool call because of prompt drift,
prompt injection, ambiguous instructions, or normal reasoning errors.

The Guardrails plugin previously guarded text, but it did not provide a platform
enforcement point for:

- Blocking a specific tool call before the agent executes it.
- Blocking a safe tool when its arguments are unsafe.
- Validating tool-call shape against the declared tool schema.
- Validating that `role: "tool"` results correspond to real prior tool calls.
- Handling streamed OpenAI `tool_calls` safely before the agent observes enough
  streamed data to execute the tool.

This proposal focuses on those gaps. It does not attempt to solve full workflow
authorization, long-horizon planning safety, execution sandboxing, memory
governance, human approval flows, or semantic reasoning about every possible
tool side effect.

## Why This Belongs in the Platform

Users can wrap every tool with custom checks, but that pushes governance into
each agent and each tool implementation. That approach does not scale well across
many agents, teams, or frameworks.

The platform value-add is central enforcement:

- Policy lives in `GuardrailConfig`, not in every agent prompt.
- Enforcement happens before tool execution, at the inference boundary.
- The same policy can be reused across agents that route through a guarded
  VirtualModel.
- Streaming tool calls are handled consistently instead of left to each agent
  framework.
- Future authorization and approval checks have one control point.

## Current Tool-Call Design

The short-term design uses the existing Guardrails plugin, VirtualModels, and
LLMRails.

The flow is:

```text
Agent -> IGW request with messages and declared tools
  -> upstream model returns assistant tool_calls
  -> Guardrails plugin response middleware detects tool_calls
  -> plugin runs tool_output rails through LLMRails
  -> allowed: original tool_calls response is returned to the agent
  -> blocked: content_filter refusal is returned; agent does not execute tool
```

For tool results:

```text
Agent executes allowed tool
  -> next IGW request includes role:"tool" messages
  -> Guardrails plugin request middleware detects tool results
  -> plugin runs tool_input rails before the next LLM call
  -> allowed: request reaches model
  -> blocked: immediate refusal is returned; model never sees tool result
```

The naming follows the Guardrails library perspective:

- `tool_output` rails run on model output that contains tool calls.
- `tool_input` rails run on tool results that are input to the next model call.

## Current Policy Capabilities

The current PoC implementation adds deterministic built-in actions:

- `check tool allowlist`: blocks tool calls whose names are not configured as
  allowed.
- `check tool arguments`: blocks tool calls whose arguments match configured
  blocked keywords or exceed configured length limits.
- `check tool schema`: validates proposed arguments against the request's
  declared tool schema.
- `check tool result linkage`: validates that tool-result messages correspond
  to prior assistant tool calls.

Example policy shape:

```json
{
  "rails": {
    "tool_output": {
      "flows": [
        "check tool allowlist",
        "check tool arguments",
        "check tool schema"
      ]
    },
    "tool_input": {
      "flows": [
        "check tool result linkage"
      ]
    }
  },
  "custom_data": {
    "tool_allowlist": {
      "allowed_tools": [
        "clock"
      ]
    }
  }
}
```

`custom_data` is the free-form extension field on `GuardrailConfig`. The
Guardrails plugin passes it through to the `nemoguardrails` runtime, so
plugin-owned actions can read policy data without changing the platform entity
schema. In this PoC, `custom_data.tool_allowlist` and
`custom_data.tool_arguments` are where we store tool policy such as allowed tool
names, blocked argument keywords, and maximum argument lengths.

For NAT function groups, policy must currently use the runtime tool names that
NAT exposes to the model, such as
`governed_optimization_tools__run_eval`, not only the local Python function name
`run_eval`.

That is correct for enforcement but not ideal as a product surface. A production
schema should make tool identity easier to author, validate, and inspect.

## What This Enables

### Safe Research Agent

The safe research agent is a minimal NAT ReAct agent for answering simple
research questions. It has access to both a deterministic time tool and a
Wikipedia lookup tool, but central policy allows only the low-risk time tool.

The safe research PoC exposes both a deterministic time tool and a Wikipedia
lookup tool:

- Agent capability: `clock` and `wiki` are both available to the model.
- Central policy: only `clock` is allowlisted.
- Enforcement: `wiki` tool calls are blocked before NAT executes the Wikipedia
  tool.

This was not possible with the previous text-only plugin behavior because the
plugin did not inspect OpenAI `tool_calls` as an action proposal.

### Governed Optimization Agent

The governed optimization agent is a NAT ReAct agent for agent optimization
workflows. It can search internal guidance, estimate inference cost, run evals,
and draft proposed updates, while central policy blocks deployment actions and
unsafe eval arguments.

The governed optimization PoC demonstrates cost and quality optimization under
central governance:

- Allow safe analysis tools:
  `governed_optimization_tools__search_internal_knowledge`,
  `governed_optimization_tools__estimate_cost`,
  `governed_optimization_tools__run_eval`, and
  `governed_optimization_tools__propose_update`.
- Block deployment:
  `governed_optimization_tools__deploy_candidate` is not on the allowlist.
- Block unsafe arguments:
  `governed_optimization_tools__run_eval` is allowed, but the `dataset`
  argument is blocked when it contains values such as `customer_pii` or
  `production`.

This demonstrates the distinction between tool-level policy and argument-level
policy. The same tool can be allowed for safe datasets and blocked for unsafe
datasets.

### Future Use Cases

The same enforcement point can support other agent governance scenarios:

- **Incident response agent**: allow health checks and runbook search, block
  destructive production actions such as service restarts unless approval exists.
- **Data access agent**: allow public documentation search, block customer record
  queries unless the user and purpose are authorized.
- **Knowledge publishing agent**: allow drafting knowledge-base updates, block
  direct publishing, and block drafts derived from unredacted customer data.
- **Model routing agent**: allow cost estimates and quality checks, block routing
  to expensive hosted models unless an escalation condition is present.

These were not first-class plugin use cases before tool rails because the plugin
only saw text before and after model generation. It could not centrally inspect
the structured action the model was asking the agent to perform.

## Short-Term Implementation State

The current implementation is an LLMRails-based bridge.

In the plugin:

- `process_response` detects assistant responses with `tool_calls`.
- For non-streaming responses, it passes the reconstructed assistant message and
  tool-call context into LLMRails with `rail_types=["tool_output"]`.
- For streaming responses, it buffers chunks, reconstructs the full tool call,
  runs `tool_output` rails, then either replays the original chunks or replaces
  them with a refusal stream.
- `process_request` detects `role: "tool"` messages and runs
  `rail_types=["tool_input"]` before forwarding the request to the model.
- Built-in Colang flows wrap deterministic Python actions registered with
  LLMRails.

This approach is useful because it validates the product shape quickly using the
existing runtime and existing `GuardrailConfig` fields.

The short-term limitations are:

- The policy surface is `custom_data`, a free-form extension field on
  `GuardrailConfig`, not a typed product schema with validation and discovery.
- Tool names must match the exact runtime names declared to the model.
- Block responses are generic unless policy metadata is inspected.
- The deterministic actions are plugin-owned rather than part of a broader
  platform policy model.
- LLMRails and Colang are heavier than necessary for simple deterministic tool
  validation.
- More advanced checks, such as user authorization or approval state, need a
  richer context model.

## Phase 1 Proposal: Tool Rails Without IORails

Phase 1 should treat the current LLMRails-based implementation as the product
validation path for agentic tool-call guardrails.

The implementation should provide:

- `tool_output` enforcement in the Guardrails plugin response hook.
- `tool_input` enforcement in the Guardrails plugin request hook.
- Streaming support for OpenAI `tool_calls` by buffering tool-call chunks before
  the agent can execute the tool.
- Built-in deterministic checks for tool allowlists, argument rules, schema
  validation, and tool-result linkage.
- Integration tests proving allowed calls pass through, blocked calls return a
  content-filter response, and streamed tool calls cannot bypass policy.
- Demo agents that show policy outside the prompt:
  safe research, governed optimization, and one high-stakes action governance
  scenario such as incident response.

Phase 1 should also improve the developer experience enough for serious PoCs:

- Return policy decision metadata with clear tool names, arguments, violated
  rules, and block reasons.
- Provide a way to inspect the runtime tool names that policy must match.
- Document NAT function-group naming, such as
  `governed_optimization_tools__run_eval`.
- Keep the policy in `GuardrailConfig`, but avoid pretending that `custom_data`
  is the final product schema.

The Phase 1 implementation should not become a full policy framework. It should
prove that the enforcement point is correct and collect requirements for a
better policy surface. In particular, Phase 1 should make clear that tool rails
mediate the model's proposed tool call; they do not replace downstream
authorization, execution containment, human approval, or post-action
verification.

### Phase 1 Open Questions

The main Phase 1 design questions are:

- Whether tool policies should stay as plugin-owned built-in flows or be exposed
  as first-class platform schema fields.
- How to represent logical tool aliases when frameworks expose transformed
  runtime names.
- How much policy reason detail should be returned to the agent versus kept for
  developers.
- Whether argument checks should remain simple deterministic rules or support
  pluggable validators.
- How to represent action risk tiers, such as read-only, reversible write,
  destructive, production-affecting, or externally visible.

## Phase 2 Proposal: IORails Migration

Phase 2 should move eligible tool-call guardrails to IORails once the IORails
runtime supports the required built-in tool rail behavior in the platform path.

Based on the local Guardrails library, IORails is designed around explicit,
built-in flow support. `IORails.unsupported_reason()` checks configured rail
sections and flow names against static supported sets. For tool rails, those sets
currently include:

- `tool_output`: `tool call validation`
- `tool_input`: `tool result validation`

`RailsManager` then dispatches those flow names through a static action map. An
unknown tool rail flow is not dynamically imported like an LLMRails Colang flow;
it is rejected or routed away from IORails. In other words, IORails currently
supports the tool flows it explicitly defines. It does not provide the same
general custom-flow extension model as LLMRails.

That has an important design implication: Phase 2 cannot assume that every
plugin-defined tool capability automatically moves into IORails. We should
separate:

- **Core native checks** that IORails should own, such as declared-tool allowlist,
  schema validation, and tool-result linkage. These match the shape of the
  current native `tool call validation` and `tool result validation` flows.
- **Platform policy compilation** that maps user-facing policy into whichever
  native IORails config or request parameters those checks require.
- **Custom or advanced checks**, such as keyword-based argument policy or
  role-aware authorization, that either need a new IORails-native action, a
  formal IORails extension mechanism, or an LLMRails/plugin fallback.

The expected Phase 2 target is:

- Common tool-call validation runs through IORails-native flows.
- Tool parsing and provider normalization are owned by IORails model-engine code,
  not reimplemented in the plugin.
- Streaming tool-call reconstruction and validation are owned by IORails or a
  shared runtime abstraction.
- The plugin routes eligible configs to IORails and keeps LLMRails as a fallback
  for unsupported custom flows.
- Guardrail responses expose consistent tool-policy decisions across text rails
  and tool rails.

The Phase 2 proposal should stay lighter until IORails' extension story is
settled. If the product needs plugin-defined tool checks that IORails does not
ship natively, we have three possible directions:

- Add those checks as first-class IORails actions.
- Add a registration mechanism to IORails for tool rail handlers.
- Keep those checks on the LLMRails/plugin path and route only native checks to
  IORails.

The correct direction depends on how much extensibility we want IORails to carry.
For now, the safe assumption is that IORails handles explicit built-in flows, and
additional capabilities require either upstream IORails work or a fallback path.

## Open Design Questions

### Tool Identity

Policies currently operate on the exact tool names exposed to the model. That is
the only safe enforcement key in the current implementation, but it is not always
the name users expect.

We need a product answer for:

- How users discover runtime tool names.
- Whether configs support aliases.
- Whether NAT can expose stable logical names for function-group tools.
- Whether policy should match on both tool name and owning function group.

### Block Reasons

The current blocked response is intentionally generic:

```text
I'm sorry, I can't respond to that.
```

That is safe but poor for debugging and demos. We need separate behavior for:

- User-facing refusal text.
- Developer-facing policy reason.

### Context and Authorization

The current checks are deterministic and local to the tool call. Real deployments
will need context:

- User identity and role.
- Workspace or project.
- Environment, such as dev, staging, or production.
- Approval state.
- Resource ownership.

The enforcement point can support these checks, but the context contract is not
yet designed.

### Execution Containment and Approval

Tool-call guardrails decide whether the agent may attempt an action. They do not
contain the side effects after an action is allowed. High-risk agents still need
hard boundaries outside the model path:

- Sandboxes, VMs, directory scopes, network egress limits, and isolated
  credentials.
- Human approval for destructive, regulated, financial, production, or
  externally visible actions.
- Post-action verification before committing state or returning final output.
- Fail-safe behavior such as stopping the run, degrading to read-only mode, or
  escalating to a human.

The platform boundary can be the policy decision point, but it should not be
presented as the only safety boundary for agents with real side effects.

### Tool Result Safety

`check tool result linkage` verifies structural integrity, but future tool-input
rails should also support content checks on tool results:

- PII or secret detection.
- Prompt-injection detection in retrieved content.
- Source trust and provenance checks.
- Result size and format constraints.

### Cross-Step Policy

Some unsafe behavior emerges across multiple tool calls. For example, querying
customer data, summarizing it, then publishing it may be unsafe even if each
single step looks acceptable. The current implementation is per-request and does
not model cross-step policy state.

## Recommendation

Continue with tool-call guardrailing as the first agentic guardrails capability.
It is the right enforcement primitive because it blocks agent actions before
execution, does not rely on prompts, and can be centralized in the platform.

Keep the current LLMRails bridge as a short-term implementation for PoCs and
early validation. Do not overinvest in expanding the bridge's custom action
surface. The long-term path should keep the user-facing tool policy independent
of the runtime, then route each policy to the appropriate implementation:
IORails-native flows for supported checks, and a fallback or new IORails
extension for checks that are not native.

The next product milestone should be:

- A typed policy shape for tool allowlists and argument rules.
- Clear tool identity handling for NAT function groups.
- Better block reason metadata.
- One more high-stakes demo, such as incident response, to validate that the
  primitive generalizes beyond research and optimization agents.
