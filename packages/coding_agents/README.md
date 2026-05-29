# coding-agents

Python library for invoking coding agents in headless mode through a uniform
abstraction.

Assumes the relevant agent CLI (e.g. `claude`) is installed on the host and
the user has already authenticated with it interactively. The library only
spawns subprocesses; it does not manage credentials.

## Status

v0 — Claude Code only. One prompt in, one `ResultEvent` out. Multi-turn is
supported by chaining: pass the previous result's `session_id` as
`resume_session_id=` to the next call. No live event stream; if a caller
needs progress reporting, that lives in a higher layer.

## Quick example

```python
import asyncio
from pathlib import Path
from coding_agents import ClaudeCodeAgent

async def main():
    agent = ClaudeCodeAgent()
    await agent.check_available()

    result = await agent.run(
        "Summarize this repo in one sentence.",
        working_dir=Path.cwd(),
        timeout=60,
    )
    print(result.success, result.text, f"${result.cost_usd:.4f}")

asyncio.run(main())
```

## Architecture

The library is a thin Python wrapper around a coding-agent CLI. There's no
state, no fleet, no streaming — just **`agent.run(prompt, working_dir=...) →
ResultEvent`**.

Two layers:

1. **Vendor-neutral interface** (`base.py`, `events.py`, `errors.py`,
   `permissions.py`) — what callers code against.
2. **Claude Code backend** (`claude_code/`) — the concrete implementation:
   spawn `claude -p`, parse the result, hand it back.

Future backends (Codex, Aider) would add another sibling directory next to
`claude_code/` implementing the same `CodingAgent` ABC.

```text
packages/coding_agents/
├── pyproject.toml                              uv workspace member declaration
├── README.md                                   this file
└── src/coding_agents/
    ├── __init__.py                             public API; re-exports everything a caller imports
    ├── base.py                                 the CodingAgent ABC (run + check_available) + AgentAvailability
    ├── events.py                               ResultEvent — the only return shape callers see
    ├── errors.py                               typed exceptions: NotInstalled / NotAuthenticated / Unsafe / Run
    ├── permissions.py                          PermissionMode enum + PermissionPolicy + is_headless_safe() check
    └── claude_code/
        ├── __init__.py                         re-exports ClaudeCodeAgent
        ├── agent.py                            ClaudeCodeAgent: spawn claude -p, wait, parse, return ResultEvent
        ├── process.py                          scrubbed_env() — strips CLAUDE_CODE_* before child spawn
        └── result.py                           stream-json result line → ResultEvent translation + JSONL scanner
└── tests/
    ├── unit/
    │   ├── test_result.py                      result-line parsing + JSONL scan happy/negative paths
    │   ├── test_permissions.py                 default policy + headless-safety guard + agent.run rejects unsafe
    │   └── test_process.py                     env scrubbing: drops CLAUDE_CODE_*, keeps ANTHROPIC_*/PATH/HOME
    └── integration/
        └── test_claude_code_smoke.py           real `claude` invocation; proves nested case works
```

### What each file actually does

**`base.py`** — defines `CodingAgent`, the ABC every backend implements. Two
abstract methods: `check_available()` and `run(prompt, working_dir, …)`. Also
defines `AgentAvailability` (a small frozen dataclass returned by
`check_available()`). This is the only thing callers should depend on if they
want to be backend-agnostic later.

**`events.py`** — just `ResultEvent`, a Pydantic model with `session_id`,
`artifact_dir`, `success`, `text`, `cost_usd`, `duration_ms`, `num_turns`,
`stop_reason`, `timestamp`. The single return type of `run()`.
`success=True` means the agent completed; `success=False` means it ran
but reported a problem. `session_id` is what you pass to a follow-up
`run(..., resume_session_id=...)` to continue the conversation;
`artifact_dir` points to the on-disk dir for *this specific run* (its
prompt, JSONL, and stderr files), which differs from `session_id` when
chaining via resume.

**`errors.py`** — exception hierarchy: `CodingAgentError` base + four
subclasses (`AgentNotInstalledError`, `NotAuthenticatedError`,
`PermissionModeUnsafeError`, `AgentRunError`). `AgentRunError` is the
"process died without producing a result" case.

**`permissions.py`** — `PermissionMode` enum mirrors Claude Code's
`--permission-mode` values plus `BYPASS`. `PermissionPolicy` is a frozen
dataclass holding the mode + allow/deny tool lists. The key method is
`is_headless_safe()` — returns True only for modes that won't deadlock
waiting for an interactive prompt (`BYPASS`, `PLAN`).

**`__init__.py`** — re-exports the public surface so callers write
`from coding_agents import ClaudeCodeAgent` instead of digging into
submodules.

**`claude_code/agent.py`** — the concrete backend. ~250 lines, mostly one
method (`run()`). Per invocation it:

1. Validates `working_dir` exists and `permissions.mode` is headless-safe.
2. Generates a UUID `run_id`, creates `<work_root>/<run_id>/`, writes
   `meta.json` + `turn_0000.prompt`.
3. Builds the `claude -p ...` command from the policy + system prompt +
   budget + model + extras.
4. Opens fds for stdin/stdout/stderr pointing at the three files, spawns
   the child with scrubbed env, closes our fds.
5. `await proc.wait()` with timeout; on timeout or asyncio cancellation,
   SIGTERM → 3s grace → SIGKILL.
6. Scans the JSONL for the `result` line and returns a `ResultEvent`. If
   there's no result line, raises `AgentRunError`.

Also has `check_available()` which runs `claude --version` then
`claude auth status`.

**`claude_code/process.py`** — one function: `scrubbed_env(extra=None)`.
Copies `os.environ`, strips `CLAUDECODE`, `CLAUDE_CODE_*`, `CLAUDE_EFFORT`,
then applies optional extras on top. This is what makes nested `claude`
invocations safe — without it the child detects the parent session via env.

**`claude_code/result.py`** — two functions:

- `find_result_in_jsonl(path)` walks the stream-json file looking for the
  single `{"type":"result", …}` line, returning the raw dict or None.
- `to_result_event(raw, run_id)` converts that dict into a `ResultEvent`,
  including the gotcha where `subtype="success"` *and* `is_error=true` must
  collapse to `success=False`.

These are split out from `agent.py` so they're testable without spawning
anything.

### The flow on one `agent.run()` call

```text
caller
  │
  ▼
ClaudeCodeAgent.run(prompt, working_dir, ...)
  │
  ├─ validate working_dir, validate permission policy
  ├─ mkdir <work_root>/<run_id>/, write meta.json + turn_0000.prompt
  ├─ build CLI args (claude -p --output-format stream-json --permission-mode ... --session-id <run_id>)
  ├─ scrubbed_env() → strip CLAUDE_CODE_* from env
  ├─ asyncio.create_subprocess_exec(...) with fds → turn_0000.{jsonl,stderr}
  ├─ await proc.wait()  ← cancel/timeout = SIGTERM/SIGKILL
  ├─ find_result_in_jsonl(turn_0000.jsonl)
  └─ to_result_event(raw, run_id) → ResultEvent
       │
       ▼
caller gets ResultEvent (or AgentRunError / TimeoutError / PermissionModeUnsafeError)
```

Everything that survives a run is on disk:
`<work_root>/<run_id>/{meta.json, turn_0000.prompt, turn_0000.jsonl, turn_0000.stderr}`.
The in-process state is gone the moment `run()` returns.
