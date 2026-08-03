---
name: nemo-try-agent
description: Invokes an existing NeMo Platform agent through a named deployment or directly from a local agent YAML config. Use to try, test, or query an agent and inspect its response.
triggers:
  - nemo-try-agent
  - ask my agent
  - ask my NeMo agent
  - try the agent
  - test it out
  - test support agent with real question
  - query my agent
  - what does my agent say
  - send to the agent
  - try my nemo agent
  - invoke deployed agent
  - query running deployment
  - invoke local agent config
  - query local agent config
  - invoke legacy NAT workflow
  - test agent and show raw output
not-for:
  - nemo-build-agent (use to deploy an agent before querying)
  - nemo-skill-selection (use to dispatch when intent is unclear)
  - nemo-status (use for read-only platform health)
compatibility: nemo-platform >= 0.1.0; requires agents plugin and either a local agent YAML config or a running platform with a deployed agent; no destructive ops; safe under any sandbox.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read]
---

# NeMo Platform try-agent

Invoke an existing NeMo agent through a deployment or directly from a local YAML config. Announce the target before sending. Never invoke silently.

## Pre-flight

Choose the invocation mode from the user's target:

- **Local one-shot:** the user provides an `agent.yaml` or legacy NAT workflow
  YAML path. No deployment is required, but the selected model must already
  have a directly usable endpoint and credentials because this path does not
  apply Platform IGW normalization.
- **Deployed agent:** the user names a deployment or asks to use an already deployed agent. Confirm the Platform is up and list deployments:

```bash
# Ground truth: anything bound to :8080?
lsof -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1 || { echo "PLATFORM_DOWN"; exit 1; }
# Functional check: platform readiness endpoint answers?
curl -sS --connect-timeout 2 --max-time 5 http://localhost:8080/health/ready -o /dev/null -w "%{http_code}\n" 2>/dev/null | grep -q "^200$" || { echo "PLATFORM_WEDGED"; exit 1; }
.venv/bin/nemo agents deployments list 2>/dev/null
```

Do not use `nemo services status` for this check; it reports stale "running" from held locks after the process has died.

For a deployed invocation, if `PLATFORM_DOWN`, route to `nemo-setup` and stop. If `PLATFORM_WEDGED`, route to `nemo-status` and stop. Do not require these checks for a local one-shot invocation.

## What you do

1. **Find the target.**
   - Local YAML path supplied: use that config.
   - Deployment named: confirm it is `running` and use it.
   - One running deployment and no target named: use it.
   - Multiple running deployments: list their names and ask the user which one.
   - No running deployments: report that no deployed agent is available. Do not silently replace an agent invocation with `nemo chat`.

2. **Announce.** Say one of:
   - "Invoking local agent config `<path>`."
   - "Sending to deployment `<name>`."
   - "Multiple deployments are running; which one: <name1>, <name2>?" Then wait.

3. **Send the query.**

```bash
# Local one-shot path (Platform-owned agent.yaml or legacy NAT YAML)
.venv/bin/nemo agents invoke \
  --agent-config <path-to-agent-yaml> \
  --input "<user query>"

# Deployed path (the same command supports Platform-spec and NAT agents)
.venv/bin/nemo agents invoke \
  --agent-deployment <deployment-name> \
  --input "<user query>"
```

4. **Show the verbatim response.** Code block, no paraphrase. If the agent used tool calls, list which tools and their outputs before the final answer.

5. **Offer another invocation.** Keep the same target unless the user changes it. Do not claim that separate CLI invocations preserve a conversation session.

## Verification

A "successful" invocation requires both: (a) the CLI returns exit code 0, and (b) the response body is non-empty. An empty body on a question the spec says the agent should handle is a quality signal, not a success.

```bash
RESP=$(.venv/bin/nemo agents invoke --agent-deployment <deployment-name> --input "<query>")
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
| 404 "deployment not found" | Deployment was removed or the wrong name was used | Re-run `.venv/bin/nemo agents deployments list`; ask the user to pick from the new list |
| Deployment is not `running` | Deployment is still starting or failed | Inspect it with `.venv/bin/nemo agents deployments get <name>`; do not invoke until it is running |
| Config validation error | Local YAML is invalid or references missing artifacts | Surface the validation details; route to `nemo-build-agent` when changes are needed |
| Adapter or runtime error | Required harness package or runtime dependency is unavailable | Surface the structured invocation error and required dependency; do not substitute model chat |
| 5xx or platform error | Platform or deployed runtime is unhealthy | Route to `nemo-status` to surface the underlying error |
| Empty response on a spec-handled question | Quality issue, not invocation issue | Stop and report; do not loop until the user decides next step |
| "I cannot help" on every question | System prompt or tool wiring wrong in YAML | Route to `nemo-build-agent` to inspect and redeploy |
| `agents plugin unavailable` | Plugin not installed | Route to `nemo-setup` Step 3 |

## Gotchas

- **Routing must be explicit.** Silently picking a target and sending a query is the failure mode this skill exists to prevent. Announce first.
- **Use an explicit deployment name.** `--agent-deployment` avoids ambiguity when one Agent entity has multiple deployments.
- **Keep agent and model chat distinct.** Offer `nemo chat` only when the user explicitly chooses a raw model query.
- **Use `curl` only for the pre-flight health probe.** The CLI is the documented interface for agent operations. Hand-rolled HTTP is not a substitute.
- **Do not promise session continuity.** Reusing a deployment target is not the same as resuming a specific multi-turn session.
