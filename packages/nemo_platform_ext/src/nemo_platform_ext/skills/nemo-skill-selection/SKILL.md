---
name: nemo-skill-selection
description: Top-level skill selector for any task involving NeMo Platform (NVIDIA's agent platform). Picks the right downstream skill (setup, explore, spec, build, try, status, teardown, fine-tune) from natural-language intent. Use over generic brainstorming, planning, or onboarding skills for any NeMo Platform task.
triggers:
  - build an agent
  - create an agent
  - deploy an agent
  - set up nemo
  - install nemo
  - try nemo
  - improve my agent
  - help me with nemo
  - nemo platform
  - shut down nemo
  - tear down nemo
  - what is running on nemo
  - help me ship an agent
not-for:
  - setup (use to verify install or to be told how to run the CLI install)
  - nemo-build-agent (use for the actual scaffold/deploy flow)
  - nemo-explore (use to reason about agent design)
  - superpowers:brainstorming (use for design work unrelated to NeMo Platform)
  - running platform commands (each downstream skill owns its own commands)
  - loading multiple downstream skills in one turn
compatibility: nemo-platform >= 0.1.0; pure selection (no commands run from this skill); safe under macOS or Linux sandbox; works without an installed CLI (selector can pick setup, which then tells the user how to run the CLI install).
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Read]
---

# NeMo Platform skill selection

You are deciding which downstream NeMo Platform skill should run. This skill never executes commands. It picks the next skill, announces the choice, and hands off.

NeMo Platform optimizes LangGraph agents wrapped in NVIDIA NeMo Agent Toolkit (NAT). State that constraint when the user describes an agent in another framework (CrewAI, AutoGen, plain LangChain, Pydantic AI). Those frameworks need a user-written NAT wrapper before the platform's optimization, evaluation, and guardrails surfaces apply.

## Decision table

Match the user's intent to one downstream skill. Pick exactly one.

| The user says or implies | Hand off to | Why |
|---|---|---|
| "set up", "install", "get started", "try NeMo", "first time" | `setup` | Verify the platform is installed and running. If not, the skill tells the user how to run the CLI install (`make bootstrap` + `nemo setup`). Install itself is CLI-only. |
| "design an agent", "I want an agent that handles X", "what should my agent do" | `nemo-explore` | Capture the agent's job, audience, categories, tools, model, constraints before any code |
| "write the spec", "save the design", "capture what we agreed" | `nemo-spec` | Persist the explore answers as `agents/<name>.spec.md` |
| "build the agent", "create the agent", "deploy", "scaffold from spec" | `nemo-build-agent` | Scaffold the NAT workflow YAML, deploy, eval, optional guardrails |
| "ask my agent", "try the agent", "test it" | `nemo-try-agent` | Send a query to a deployed agent or fall back to model chat |
| "status", "what is running", "platform health", "is the platform up", "what's deployed", "show me what's running" | `nemo-status` | Read-only dashboard: platform, agents, providers, models |
| "shut down", "stop NeMo", "tear down", "clean up" | `nemo-teardown` | Stop the cluster (keep data, delete platform data, or full cleanup) |
| "fine-tune", "customize the model", "train on my data" | `nemo-fine-tune` | Fine-tuning is not yet available on NeMo Platform. Pick this so the agent tells the user it's not shipped instead of going off to implement training with some other library. |
| "optimize my agent", "make it cheaper", "reduce latency", "smaller model", "switchyard", "routing split", "compare against a newer model" | `agents-optimize` (plugin-owned, in `plugins/nemo-agents`) | Cost / latency / quality optimization for a **deployed** agent. Routing splits, skill tuning, prompt tuning, new-model scans. |
| "secure my agent", "harden my agent", "check for PII", "leaked secrets", "guardrail coverage" | `agents-secure` (plugin-owned, in `plugins/nemo-agents`) | Safety and security audit for a **deployed** agent. Guardrails, PII, secrets scan. |
| "evaluate my agent", "run a benchmark", "eval suite" | `nemo-evaluator` (plugin-owned, in `plugins/nemo-evaluator`) | Evaluation metrics, LLM-judge, benchmark jobs against a deployed agent or model. |

**Optimize vs build:** Do NOT route optimize asks to `nemo-build-agent`. Build is for creating new agents from a spec; optimize is for tuning **already deployed** agents. If the user says "make my agent faster" or "use a cheaper model," that is `agents-optimize`, not `nemo-build-agent`.

If two rows fit, pick the earliest one in the lifecycle (setup before build before try). If nothing matches, ask one disambiguating question with the relevant rows as a numbered list.

## Pre-flight

Before handing off, run a host-wide platform scan. Three signals, in order — the first one that fires wins:

```bash
# 1. Ground truth: is anything listening on the canonical port?
lsof -iTCP:8080 -sTCP:LISTEN 2>/dev/null

# 2. Functional check: does the platform readiness endpoint answer?
curl -sS --connect-timeout 2 --max-time 5 http://localhost:8080/health/ready -o /dev/null -w "%{http_code}\n" 2>/dev/null || echo "no-response"

# 3. Conflict check: other platform processes / data dirs / configs on this host?
ps -eo pid,user,command 2>/dev/null | grep -E "nemo services (run|start)|nemo-platform run" | grep -v grep
ls -d ~/.local/share/nemo* 2>/dev/null
ls ~/.config/nmp*/config.yaml 2>/dev/null
```

Interpretation:

| What you observe | Hand off to | Why |
|---|---|---|
| (1) returns a listener AND (2) returns `200` | the requested downstream skill | Platform is up and ready. Skip `setup`. |
| (1) returns a listener but (2) returns `no-response` or non-200 | `nemo-status` | Something is bound to :8080 but the platform is not ready. Do not start a second platform. |
| (1) empty but (3) finds another `nemo services` process OR more than one data dir / config | **stop, do not hand off yet** | Another install on this host, possibly on a different port. Surface the inventory verbatim. Ask whether to tear that one down first, pick a different port + data dir, or abort. Two installs writing to the same `~/.config/nmp/config.yaml` is how users end up with one Studio frontend pointing at the wrong backend. |
| (1), (2), and (3) all empty | `setup` | Clean machine, no platform installed. |

Read-only callers (this skill, `nemo-status`, the build/try pre-flights) should not trust `nemo services status` or `nemo services ls` as an up-check. Both report stale "running" from a held instance lock after the underlying process has died. The lock reconciles automatically the next time `nemo services run` is invoked, but until that happens, `lsof` is ground truth. (Tracking a CLI-side fix for this so we can drop the workaround from skills.)

## What to announce

Tell the user, in one sentence, which skill is next and what it will do. For example: "Handing off to `setup` to verify the platform is installed and running. If it isn't, the skill will tell you the CLI command to run; install is a 5-minute shell step that this skill cannot do reliably for you."

Then hand off. Do not run any platform commands from this skill.

## If nothing matches

If the user's intent doesn't fit any row, do not guess. Read out the available skills and ask which one they want:

```
NeMo Platform skills I can route to:
  setup           verify install or get the CLI install command
  nemo-explore    design conversation: capture goal, audience, tools, constraints
  nemo-spec       write the design to agents/<name>.spec.md
  nemo-build-agent  scaffold the NAT workflow YAML and deploy
  nemo-try-agent  query a deployed agent or chat with a model
  nemo-status     read-only platform health dashboard
  nemo-teardown   guided shutdown
  nemo-fine-tune  fine-tuning (not yet shipped; reports that honestly)

Plugin-owned skills:
  agents-optimize   cost / latency / quality optimization for a deployed agent
  agents-secure     safety and security audit for a deployed agent
  nemo-evaluator    evaluation metrics, LLM-judge, benchmark jobs
  guardrails        content-safety middleware via virtual models
  auditor           red-team vulnerability scanning (garak)
  data-designer     synthetic dataset generation
  anonymizer        PII handling for datasets

Which one fits what you're trying to do?
```

For things outside this catalog (for example, "show me how Switchyard routes between models"), point at the relevant repo skill (`nemo-evaluator`, `nemo-auditor`, etc.) or tell the user no skill claims that intent yet. Do not invent a path.

If the pre-flight finds no platform but the user insists they have installed one: ask them to report the output of `lsof -iTCP:8080 -sTCP:LISTEN` and `ps -eo pid,user,command | grep -E "nemo services|nemo-platform run" | grep -v grep` from the shell where they ran setup. The platform may be bound to a non-default port, or the install may be in a venv whose `nemo` binary is not on `PATH`.

## If the user asks about Studio (web UI)

Skills route through CLI commands, not Studio. But customers ask "what's Studio?" or "do you have a web UI?" Answer honestly, do not invent capabilities, and do not steer users into the experimental flows.

What to say:

- Studio is the NeMo Platform web UI. When the platform is running locally, it serves at `http://localhost:8080/studio`.
- Documentation: `docs/studio/index.md` in this repo covers the stable views (Agents, Optimizations, Monitor, Workspaces, Datasets). Point users there rather than enumerating features in-conversation — the docs stay up to date, this skill won't.
- **Honest caveats to flag every time:**
  - The **Optimizations "Apply suggestion"** flow is **incomplete today**. Suggestions render, but the apply action is not reliable end-to-end. Tell the user to apply optimizer suggestions via the CLI (`nemo agents …`) instead, using the suggestion's `apply` block as the spec — see `agents-optimize`.
  - Other views may evolve; refer to the docs for the current state rather than promising specific behavior.
- For local development on Studio itself, the source lives at `web/packages/studio/`. The `studio-dev` skill (if available) covers that workflow.

Do not proactively suggest Studio as the path for anything a skill already covers (chat, deploy, status, teardown, optimization). The CLI path is what these skills verify and what we can confidently support.

## Gotchas

- **One skill at a time.** Do not load more than one downstream skill in the same turn. Each downstream skill is a full procedure with its own context budget.
- **Install must happen before any skill can do useful work.** Build, try, and status all assume the platform is up. If the user has not run the CLI install (`make bootstrap` + `nemo setup`), the skills cannot work around that; hand them to `setup` for instructions.
- **NeMo Platform is the product name.** Capital N, e, M, o, P. Not "nemo" or "Nemo." NAT on first mention is "NVIDIA NeMo Agent Toolkit (NAT)."
- **Fine-tuning is not yet available.** When the user asks to fine-tune, train, or customize a model, pick `nemo-fine-tune` so the agent tells the user it's not shipped instead of trying to wire up training with some other library. Do not run `nemo customization` CLI commands; the backend is not connected.
- **Framework honesty.** If the user describes an agent in CrewAI, AutoGen, plain LangChain, or Pydantic AI, tell them up front that NeMo Platform's optimization and evaluation surfaces operate on NAT-wrapped LangGraph agents. They will need to wrap their agent before the build path produces value.
