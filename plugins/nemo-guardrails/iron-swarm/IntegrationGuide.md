# Integration guide — Iron Swarm dev team

How this reference becomes a production agent: per-tool, LLM-judged guardrails on
NeMo Fabric + Relay that reproduce the NAT `pre_tool_verifier` behavior, with no
guardrail code in the agent itself.

For how the reference works internally, see [`README.md`](./README.md). This guide
is the checklist for adapting it.

## Mental model

- **The judge is the built-in `nemo_guardrails` Relay plugin.** It runs the
  guardrail config in a worker and makes the policy LLM call; no LLM client is
  written.
- **Prompts are authored; the rest is boilerplate.** The per-tool policy lives in
  `guardrails_config/prompts.yml`. The judge action, the flow, and the context
  plumbing are copied as-is.
- **Two pieces are workarounds.** The context intercepts
  (`relay_guardrails/context.py`) and the custom adapter exist only because Relay
  does not yet carry conversation context to the tool boundary. The longer-term fix
  is native context support in Relay (a feature request is filed); once it lands
  both are removed, leaving just the guardrail config.

## Steps

### 0. Prerequisites
- `uv` installed
- `INFERENCE_API_KEY` env var set to authenticate with the models
- `pypi.nvidia.com` access (for `nemo-fabric`)
- `make setup`, which builds the driver venv and the pinned `nemoguardrails` worker venv
- (optional) `make spike` to confirm the environment plumbing works

### 1. Author the prompts — `guardrails_config/prompts.yml`
The six prompts in this file are pulled from a reference Iron Swarm NAT Agent.

```yaml
- task: guardrail__<tool_name>__<check_name>
  content: |-
    <system_instructions verbatim>
    ...
    User's turn:
    {{ user_turn }}
    Tool call under evaluation (JSON):
    {{ tool_call }}
```

- One task per check. A tool with three checks (like `list_saved_queries` in the
  reference) gets three tasks — all run, block-if-any.
- `{{ user_turn }}` serves intent checks, `{{ tool_call }}` serves arg checks; both
  are always available and the prompt decides what to inspect.
- The `<tool_name>` must match the tool's name exactly (step 2).

### 2. Wire the tools — via MCP
Fabric's `deepagents` adapter takes tools from an MCP server rather than in-process
Python. The existing NAT tools already sit behind an HTTP server; exposing them as
MCP (stdio or `streamable-http`) and pointing the config at it is enough. In
`demos/fabric_demo.py`:

```python
config.add_mcp_server(
    "quill-tools",
    transport="streamable_http",           # or "stdio" for a local command
    url="https://your-tool-server/mcp",     # (stdio: "python your_server.py")
    exposure="harness_native",
)
```

MCP tool names must match the `prompts.yml` task names (`run_sql`,
`list_saved_queries`, …). `mock-tools/mock_tools_server.py` shows the stdio shape.

### 3. Set the model/endpoint
- **Judge model:** `guardrails_config/config.yml` (`models: - type: main …`) — the
  model the guardrail worker calls.
- **Agent model:** `demos/fabric_demo.py` harness settings (`base_url`) plus
  `models.default` (`model`, `api_key_env`). The reference defaults to
  `inference-api.nvidia.com` and `INFERENCE_API_KEY`.

### 4. Run and verify
```bash
make spike        # all checks, driven directly, real judge
make fabric       # end-to-end agent through Fabric
```

Context reaching the judge is the one thing that could silently break, and is confirmed
by:
```bash
IRON_SWARM_DEBUG=$PWD/after.log make fabric
grep -E "context_present|CHECK" after.log
```
Every line should read `context_present=True` with the real user turn, alongside a
`CHECK guardrail__… -> BLOCK/allow` per check.

## Gotchas

- **User-turn checks are model-dependent.** They fire only if the model calls the
  tool. A model that self-defends and declines leaves nothing to gate — the
  guardrail is defense-in-depth, not the only line. Arg-based checks (SQL tables,
  export destinations) are deterministic, and `make spike` exercises all checks
  regardless of the model.
- **A block surfaces as a generic `FAILED: adapter reported an invocation failure`**
  at the `invoke` stage; Fabric swallows the specific rail message. A `FAILED` here
  is the intended result. Relay ATOF telemetry shows the exact rail.
- **Two venvs are mandatory** — the pinned `nemoguardrails==0.22.0` worker cannot
  share a venv with modern langchain.
- **A stray active venv can shadow the local one** — Fabric resolves the adapter
  off `PATH`, and the Makefile puts the local `.venv` first.

## Workarounds and the longer-term fix

The context intercepts (`relay_guardrails/context.py`) and the custom adapter are
workarounds: they bridge conversation context to the tool-boundary judge across
Fabric's process boundary, which Relay does not do natively today.

The longer-term fix is to add more context at the tool boundary in Relay. With this,
the code in `relay_guardrails/` and the `adapters/` manifest could be removed, leaving
`guardrails_config/` and the `enable_relay(components=…)` line. The prompts are
unaffected.
