---
name: agent-description-setup
description: Bootstrap AGENT_DESCRIPTION.md for a new agent under test and register it with NeMo Platform.
version: 0.1
---

# Agent Description Setup (bootstrap mode)

Use this skill **once** when onboarding a new agent under test (AUT) to NeMo
Platform's insights plugin. It produces two artifacts:

1. An `AGENT_DESCRIPTION.md` file committed to the AUT's source repository.
2. An `AgentRegistration` entity in NeMo Platform pointing at that file.

Both are prerequisites for the analyst agent. Without them the analyst has no
grounding for what the AUT is supposed to do and can't filter intake traces to
this AUT.

## When to invoke

Run this skill once per AUT, before any insights work. If the file already
exists and the agent is registered, the **refinement-mode** skill (separate,
M2) is what you want instead.

## What the skill does

The skill drives the developer's coding agent through five steps. It does not
run autonomously — the developer is in the loop on each step.

### 1. Walk the AUT codebase

Inspect the AUT repository to extract:

- Entry points (CLI commands, HTTP routes, function signatures the agent
  exposes).
- System prompts (string literals, prompt-template files).
- Tool definitions (function tools, MCP tools, external integrations).
- Model configuration (model name, provider, temperature, max tokens, any
  routing config).

Capture file paths and line numbers for everything found. The agent will cite
these in `AGENT_DESCRIPTION.md`.

### 2. Ingest existing documentation

Read any PRDs, design notes, READMEs, or architecture docs in the repo or
linked from it. Surface anything that talks about goals, scope, or success
criteria.

### 3. Interview the developer

Cover, in order:

- **What is this agent for?** Plain-language purpose.
- **Who uses it?** End users, internal callers, both.
- **What does success look like?** Concrete behaviour, not metrics.
- **What signals tell you it's failing?** Where do you notice problems today?
- **What can the analyst change?** Allowed mutation surface — system prompt
  only, prompts + tools, model swaps, etc.
- **What's off-limits?** Anything the analyst must not touch.

One or two questions at a time, not a form. The developer is in their editor
and impatient.

### 4. Write AGENT_DESCRIPTION.md

Use this front-matter shape (required fields only; extend with project-specific
fields as needed):

```markdown
---
name: my-agent                              # canonical agent name; must match
                                            # the agent_id span attribute the
                                            # AUT emits into intake
eval_command: "nat eval --config evals.yml" # CLI command to run the eval suite
---

# my-agent

## Purpose
...

## Users
...

## Success criteria
...

## Failure signals
...

## Optimization scope
**Allowed:** ...
**Off-limits:** ...

## Implementation notes
- Entry point: `src/agent.py:main`
- System prompt: `src/prompts/system.md`
- Tools: ...
- Model: ...
```

Commit the file to the AUT repo. The developer reviews the PR before merging —
the skill does not push without confirmation.

### 5. Register the agent with NeMo Platform

POST the AgentRegistration. The canonical agent name must match the front
matter `name` field, which must also match the `agent_id` span attribute the
AUT emits into intake — this three-way alignment is how the analyst correlates
traces to a registered AUT.

```python
from nemo_platform import NeMoPlatform

c = NeMoPlatform()
c.insights.agent_registrations.create(
    workspace="default",                    # or the customer's workspace
    name="my-agent",
    description="One-line description from the interview.",
    repo_url="https://github.com/me/my-agent",
    agent_description_path="AGENT_DESCRIPTION.md",
    agent_description_content=open("AGENT_DESCRIPTION.md").read(),
    eval_command="nat eval --config evals.yml",
)
```

Equivalent CLI:

```
nemo insights registrations create \
  --workspace default \
  --name my-agent \
  --repo-url https://github.com/me/my-agent \
  --agent-description-content "$(cat AGENT_DESCRIPTION.md)" \
  --eval-command 'nat eval --config evals.yml'
```

## Verification

After the skill completes:

```
nemo insights registrations get --workspace default --name my-agent
```

Should return the AgentRegistration with `agent_description_uploaded_at` set
and `agent_description_content` matching the file in the repo.

## Out of scope

- Defining eval scorers or building the eval dataset — that's the **eval-setup**
  skill (M2).
- Refining `AGENT_DESCRIPTION.md` based on recent Insights — that's the
  refinement-mode skill (M2).
- Configuring a cloud coding agent (Cursor/Claude Code/Codex) — M3.
