---
name: nemo-try-agent
description: Sends a query to a deployed NeMo Platform agent (or falls back to direct model chat) and announces the routing decision before sending. Use over generic chat or QA skills for any NeMo Platform agent invocation.
triggers:
  - ask my agent
  - try the agent
  - test it out
  - query my agent
  - what does my agent say
  - send to the agent
  - try my nemo agent
not-for:
  - nemo-build-agent (use to deploy an agent before querying)
  - nemo-skill-selection (use to dispatch when intent is unclear)
  - nemo-status (use for read-only platform health)
compatibility: nemo-platform >= 0.1.0; running platform with at least one deployed agent (or a registered model for fallback); requires agents plugin; no destructive ops; safe under any sandbox.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read]
---

# NeMo Platform try-agent

Route a user query to a deployed agent or direct model. Announce the routing decision before sending. Never invoke silently.

## Pre-flight

Confirm the platform is up and check what deployed agents exist before doing anything:

```bash
# Ground truth: anything bound to :8080?
lsof -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1 || { echo "PLATFORM_DOWN"; exit 1; }
# Functional check: platform readiness endpoint answers?
curl -sS --connect-timeout 2 --max-time 5 http://localhost:8080/health/ready -o /dev/null -w "%{http_code}\n" 2>/dev/null | grep -q "^200$" || { echo "PLATFORM_WEDGED"; exit 1; }
.venv/bin/nemo agents deployments list 2>/dev/null
```

Do not use `nemo services status` for this check — it reports stale "running" from held locks after the process has died.

If `PLATFORM_DOWN`: route to `nemo-setup` and stop. If `PLATFORM_WEDGED`: route to `nemo-status` to surface the underlying error and stop.

## What you do

1. **Find the target.**
   - One agent deployed: pick it as the target.
   - Multiple agents deployed: ask the user which one. List names + statuses.
   - No agents deployed: fall back to `nemo chat` against a model from `nemo models list`. Tell the user this is a model query, not an agent query.

2. **Announce.** Say one of:
   - "Sending to agent `<name>`."
   - "No agents deployed; sending to model `<id>` via `nemo chat`."
   - "Multiple agents deployed; which one: <name1>, <name2>?" (then wait)

3. **Send the query.**

```bash
# Agent path
.venv/bin/nemo agents invoke --agent <name> --input "<user query>"

# Model fallback path
.venv/bin/nemo chat <model-id> "<user query>"
```

4. **Show the verbatim response.** Code block, no paraphrase. If the agent used tool calls, list which tools and their outputs before the final answer.

5. **Loop for follow-ups.** After the response, ask: "Another question, or done?" Keep the same target until the user changes it.

## Verification

A "successful" invocation requires both: (a) the CLI returns exit code 0, and (b) the response body is non-empty. An empty body on a question the spec says the agent should handle is a quality signal, not a success.

```bash
RESP=$(.venv/bin/nemo agents invoke --agent <name> --input "<query>")
RC=$?
if [ $RC -ne 0 ]; then
  echo "INVOKE_FAILED (exit $RC)"
elif [ -z "$RESP" ]; then
  echo "EMPTY_RESPONSE"
else
  echo "OK"
fi
```

If `INVOKE_FAILED` or `EMPTY_RESPONSE`: surface that to the user and stop. Do not claim the invocation succeeded.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| 404 "agent not found" | Agent undeployed since last list | Re-run `.venv/bin/nemo agents deployments list`; ask user to pick from the new list |
| 5xx or platform error | Platform unhealthy | Route to `nemo-status` to surface the underlying error; offer to fall back to model chat |
| Empty response on a spec-handled question | Quality issue, not invocation issue | Stop and report; do not loop until the user decides next step |
| "I cannot help" on every question | System prompt or tool wiring wrong in YAML | Route to `nemo-build-agent` to inspect and redeploy |
| `agents plugin unavailable` | Plugin not installed | Route to `nemo-setup` Step 3 |

## Gotchas

- **Routing must be explicit.** Silently picking a target and sending a query is the failure mode this skill exists to prevent. Announce first.
- **`nemo chat` and `nemo agents invoke` take different model id formats.** Chat uses entity-name (hyphens). Agents use whatever the YAML specifies. Pass through what the user says; do not auto-translate.
- **Use `curl` only for the pre-flight health probe.** The CLI is the documented interface for agent and model operations. Hand-rolled HTTP is not a substitute.
- **Loop in this skill, not in another.** Do not invoke `nemo-skill-selection` between turns. Stay here until the user asks to do something else.
