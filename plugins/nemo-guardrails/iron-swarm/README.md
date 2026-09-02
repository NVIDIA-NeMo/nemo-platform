# Iron Swarm × Relay guardrails — reference implementation

A reference for re-creating Iron Swarm's per-tool, LLM-judged guardrails on
**NeMo Fabric + Relay**, reproducing the behavior of a reference NAT `react_agent`
today — with no changes to the agent's own code.

> Adapting this to another agent? See **[`IntegrationGuide.md`](./IntegrationGuide.md)**.
> This README describes how the reference itself works.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) installed
- `INFERENCE_API_KEY` env var set to authenticate with the models
- `pypi.nvidia.com` access (for `nemo-fabric`)

## Quick start

The reference is self-contained: `make setup` creates two local venvs (a driver
venv and a pinned `nemoguardrails` worker venv), independent of the platform
environment.

```bash
make setup        # create .venv (driver) + .worker-venv (nemoguardrails worker)
export INFERENCE_API_KEY=...
make spike        # all six guardrails, driven directly (real judge)
make fabric       # the full deployment demo through Fabric (all four tools)
```

## Design

The guardrails surface is Relay's built-in `nemo_guardrails` plugin, which owns
the judging. Enabled at the `tool_input` boundary, it spawns a
`nemoguardrails==0.22.0` worker that runs `guardrails_config/` and makes the
policy LLM call. There is no agent-side judge and no custom LLM client.

Conversation context is supplied separately. Relay's tool-boundary payload is
just `{tool_name, arguments}`, so a user-turn check — for example, blocking
`list_saved_queries` when phrased to grab a session token — has nothing to judge
on its own. Three Relay intercepts bridge that gap:

```
model call ──▶ [capture]  the user turn is read off the model call
tool call  ──▶ [inject]   it is added to the tool args
           ──▶ [nemo_guardrails plugin @ tool_input]
                   └─▶ worker: renders prompts.yml, calls the judge model ─▶ allow/block
           ──▶ [strip]    the injected key is removed
           ──▶ the real tool runs with clean args   (or the call is blocked)
```

Under Fabric the deepagents agent runs in a separate subprocess, so the intercepts
are registered by a custom adapter that launches inside that subprocess and then
serves the stock `DeepAgentsRuntime` unchanged. The context intercepts and the
custom adapter are workarounds for a current gap — Relay does not yet carry
conversation context across the tool boundary. The longer-term fix is native
context support in Relay (see [Feature requests](#feature-requests)), after which
both are removed and only `guardrails_config/` remains.

### Maps to the NAT setup

| NAT today | This reference |
| --- | --- |
| `react_agent` | Fabric **deepagents** harness (LangGraph) |
| `pre_tool_verifier` per tool | built-in **`nemo_guardrails`** plugin at `tool_input` |
| conversation available in NAT | context supplied via intercepts + custom adapter |
| `safety_llm` + per-tool `system_instructions` | `config.yml` judge model + `prompts.yml` per-tool prompts |

## Structure

The guardrail policy is authored by the agent developer; the surrounding wiring is boilerplate.

| Part | Files | Notes |
| --- | --- | --- |
| **Guardrail config** (authored) | `guardrails_config/` | `prompts.yml` is the per-tool policy; `actions.py`/`rails.co`/`config.yml` are write-once boilerplate |
| **Context + adapter** (workaround) | `relay_guardrails/`, `adapters/quill-relay/` | the capture/inject/strip intercepts and the custom adapter; removed once Relay carries context to the tool boundary natively |
| **Wiring** | `relay_guardrails/component.py`, `demos/fabric_demo.py` | builds the `nemo_guardrails` component and attaches it to the Fabric config |

Adding a check is a matter of adding one `guardrail__<tool>__<check>` task to
`prompts.yml`; `actions.py` runs every check for the tool being called and blocks
if any fires, reproducing NAT's block-if-any middleware chain.

## Files

| Path | Purpose |
| --- | --- |
| `guardrails_config/prompts.yml` | Per-tool judge prompts (the authored policy). |
| `guardrails_config/actions.py` | Worker judge: reads context, runs each check, calls the model. |
| `guardrails_config/{config.yml,rails.co}` | Judge model + the single `tool call gate` flow. |
| `relay_guardrails/context.py` | The capture/inject/strip intercepts. |
| `relay_guardrails/component.py` | Builds the `nemo_guardrails` component (spec / config dict). |
| `relay_guardrails/fabric_adapter.py` | Custom adapter serving `DeepAgentsRuntime`. |
| `adapters/quill-relay/fabric-adapter.json` | Manifest registering the custom adapter with Fabric. |
| `demos/run_spike.py` | Fast proof driven directly (no agent, no Fabric). |
| `demos/fabric_demo.py` | The deployment shape: the agent through Fabric's deepagents harness. |
| `mock-tools/mock_tools_server.py` | Quill's tools as a local stdio MCP server (mock results). |
| `Makefile` | `make setup` / `spike` / `fabric`. |
| `requirements-driver.txt` / `requirements-worker.txt` | Deps for the driver and worker venvs. |

## Coverage

All four tools and all six `pre_tool_verifier` checks are covered as independent
per-tool checks (block-if-any).

| Tool | Checks (NAT) | Judged on |
| --- | --- | --- |
| `run_sql` | `custom_guardrail_3` | tool args (blocked tables/columns) |
| `list_saved_queries` | `custom_guardrail_1`, `_2`, `_4` | user turn |
| `describe_schema` | `custom_guardrail_6` | user turn |
| `export_query_result` | `custom_guardrail_5` | tool args (external recipient / directive codes) |

## Run

- **`make spike`** is a sanity check script. It drives `tools.execute` for all four tools directly (no agent,
  no Fabric), so every check is exercised deterministically against the real
  judge. Benign `list_saved_queries` blocks here — that is `guardrail_1` behaving
  as ported (see Expected behaviors).
- **`make fabric`** runs Quill on the deepagents harness, tools from a local stdio
  MCP server (`mock-tools/mock_tools_server.py`), guardrails via the custom
  adapter.

## Verification

The definitive signal is what the judge receives, logged via `IRON_SWARM_DEBUG`.
Running the same agent two ways shows the difference:

```bash
IRON_SWARM_STOCK_ADAPTER=1 IRON_SWARM_DEBUG=$PWD/before.log make fabric
IRON_SWARM_DEBUG=$PWD/after.log  make fabric
grep context_present before.log            # built-in adapter -> all False
grep -E "context_present|CHECK" after.log  # custom adapter   -> all True, + per-check verdicts
```

`before=False → after=True` confirms context reaches the judge in the adapter
subprocess; `make spike` is the deterministic regression check for the guardrail
logic.

## Expected behaviors

| Behavior | Why |
| --- | --- |
| Benign `list_saved_queries` is **blocked** (real judge / Fabric) | `guardrail_1`'s prohibited-phrase list includes the normal way to ask; ported faithfully. Tuning that prompt resolves it — not a wiring issue. |
| `describe_schema` / `export` exfil not blocked **through Fabric** | The model declined to call the tool (self-defense), so there was nothing to gate. User-turn checks are defense-in-depth; `make spike` exercises them directly. |
| Blocks surface as a generic `adapter_reported_failure` at `invoke` | The adapter swallows the specific rail message. Relay ATOF telemetry shows the exact rail. |
| A `FAILED` line | A `FAILED` here is a guardrail block — the intended result. |

## Status

Verified end to end (`nemo_relay==0.4.0`, real Fabric deepagents runtime):
- `make spike` — all six under the real judge, driven directly (deterministic;
  benign `list_saved_queries` blocks per `guardrail_1`; no context leaks).
- `make fabric` — context reaches the judge in the adapter subprocess
  (`context_present` False→True); per-check block-if-any confirmed.

## Caveats

- **Two venvs are required.** The `nemoguardrails==0.22.0` worker conflicts with
  the driver's modern langchain, so the guardrails plugin isolates it in its own
  subprocess/venv.
- **`nemo-fabric` install.** Real wheels are on `https://pypi.nvidia.com` (public
  PyPI holds a code-less placeholder); the internal index and `--prerelease=allow`
  are needed (the Makefile handles it).
- **Sandbox egress.** If worker init fails on a `socksio`/SOCKS error, the
  worker's egress is behind a proxy — `pip install 'httpx[socks]'` into the worker
  venv resolves it.
- **Worker pin:** `nemoguardrails==0.22.0` exactly.
- **Prompts are faithful condensations**, not verbatim copies, of the six NAT
  prompts — the exact researched prompts should be pasted in.

## Missing features

The context intercepts and custom adapter are workarounds for current gaps. The
longer-term fixes that retire them:

1. **Native context at the tool boundary (Relay) — the headline ask.** Relay
   carries the user turn (and history) to the `tool_input` boundary; the intercepts
   and custom adapter both disappear, leaving only `guardrails_config/`.
2. **Plugin auto-discovery (Relay).** Entry-point discovery so a pip-installed
   Relay plugin registers itself inside the adapter subprocess. Retires the custom
   adapter (keeps the intercepts).
3. **Clearer failure surfacing (Fabric).** The underlying rail/tool message in
   `RunResult.error` instead of the generic `adapter_reported_failure`.
