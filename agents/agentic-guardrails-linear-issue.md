# Agentic guardrails: RFC, PoCs, and tool-call enforcement implementation

## Description

We need to formalize and track the initial agentic guardrails work for the Guardrails plugin. The first supported scope is tool-call guardrailing: intercepting model-proposed tool calls before agent execution, validating the tool name, arguments, and schema, and validating tool results before the next model call.

## Background

Agentic guardrails are broader than input/output text moderation. Agents can plan, call tools, execute actions, consume tool results, and persist state. This issue tracks the first concrete enforcement primitive: centralized tool-call policy at the Inference Gateway / Guardrails plugin boundary.

The current proposal lives at:

`agents/agentic-guardrails-proposal.md`

Initial PoCs live at:

`agents/agentic-guardrails-poc/`

`agents/governed-optimization-poc/`

## Scope

This issue tracks three workstreams:

- RFC / design proposal
- Demo PoCs
- Production implementation of initial tool-call guardrails

## Goals

- Define what “agentic guardrails” means for NeMo Platform.
- Clearly scope the first implementation to tool calls, not the full agent safety lifecycle.
- Support `tool_output` rails for model-proposed tool calls before execution.
- Support `tool_input` rails for tool results before the next model call.
- Support streaming OpenAI `tool_calls` without allowing partial streamed tool calls to bypass policy.
- Provide deterministic built-in checks for:
  - Tool allowlist
  - Tool argument policy
  - Tool schema validation
  - Tool result linkage
- Demonstrate the feature with concrete agent PoCs.

## Non-Goals

- Full workflow authorization.
- Human approval flows.
- Execution sandboxing or containment.
- Memory governance.
- Cross-step policy state.
- Replacing downstream IAM or tool-level security.
- Full IORails migration in this issue.

## PoCs

### Safe Research Agent

Shows a small policy-neutral research agent with two tools:

- `clock`: allowed
- `wiki`: blocked

Goal: prove that central policy can block a model-proposed tool call before NAT executes it, without relying on prompt instructions.

### Governed Optimization Agent

Shows a cost/quality optimization agent with safe analysis tools and one unsafe deployment tool.

Allowed tools:

- `governed_optimization_tools__search_internal_knowledge`
- `governed_optimization_tools__estimate_cost`
- `governed_optimization_tools__run_eval`
- `governed_optimization_tools__propose_update`

Blocked behavior:

- `governed_optimization_tools__deploy_candidate` is blocked by allowlist.
- `governed_optimization_tools__run_eval` is blocked when unsafe dataset arguments include values such as `customer_pii` or `production`.

Goal: prove both tool-level and argument-level policy.

## Implementation Checklist

- [ ] Wire `rails.tool_output` into Guardrails plugin response middleware.
- [ ] Wire `rails.tool_input` into Guardrails plugin request middleware.
- [ ] Preserve OpenAI `tool_calls` when reconstructing assistant messages for rails.
- [ ] Add built-in tool rail actions and Colang wrappers.
- [ ] Register built-in tool rail actions with LLMRails.
- [ ] Add streaming tool-call buffering/reconstruction before policy evaluation.
- [ ] Return a content-filter refusal instead of forwarding blocked tool calls.
- [ ] Include guardrails data / policy decision metadata where appropriate.
- [ ] Add unit tests for deterministic tool rail actions.
- [ ] Add integration tests.
  - [ ] Allowed tool call passes through.
  - [ ] Blocked tool call returns refusal.
  - [ ] Argument-policy block.
  - [ ] Tool result linkage.
  - [ ] Streaming allowed tool call.
  - [ ] Streaming blocked tool call.

## Design Questions

- Should tool policy remain in `custom_data`, or become a first-class typed schema?
- How should users discover or author policy against runtime tool names, especially NAT function-group names?
- How much block reason detail should be returned to the agent versus kept for developers?
- Should advanced argument policy remain deterministic keyword/length checks or become pluggable validators?
- What is the longer-term migration path to IORails-native tool rails?
- If IORails only supports explicitly defined flows, how should plugin-specific checks migrate: native IORails actions, extension mechanism, or fallback to LLMRails/plugin path?

## Acceptance Criteria

- [ ] RFC/proposal explains the agentic guardrails surface area and clearly scopes Phase 1 to tool calls.
- [ ] Safe Research Agent PoC can demonstrate allowed and blocked tool calls.
- [ ] Governed Optimization Agent PoC can demonstrate allowed workflow, blocked deployment, and blocked unsafe eval dataset.
- [ ] Tool-call guardrails run before tool execution for both streaming and non-streaming responses.
- [ ] Tool-result guardrails run before the next LLM call.
- [ ] Tests cover allow, block, argument policy, schema validation, linkage validation, and streaming behavior.
- [ ] Documentation clearly distinguishes tool-call guardrails from authorization, sandboxing, approval, and memory governance.
