# How to adapt this example for your own agent

**Goal:** turn the email-phishing example into your own agent — a DeepAgents
orchestrator that delegates to a sub-agent and calls your tool.

**Prerequisites:** you can deploy and invoke the example ([README.md](README.md)).

The shape you're reusing:

```text
orchestrator (deepagents) ── delegates ──▶ <your> verdict sub-agent
      ├──────────── consults ────────────▶ <your> specialist sub-agents
      └───────────── calls ─────────────▶ <your tool> (stdio MCP)
```

## Parts & what to change

| Path | What it is | Swap for your own |
|---|---|---|
| `agent.yaml` | The `nemo-agents-spec-v1` config: harness, sub-agents, model, MCP server, telemetry | Rewrite the orchestrator `instructions.system` and each sub-agent `system_prompt` + `description`; set `models.default` (+ `temperature`); rename `name` / `telemetry.project` |
| `mcps/iocs.py` | `extract_iocs` (pure regex) + a FastMCP stdio server | Replace the function body with your tool's logic; keep the `@mcp.tool()` wrapper + `main()`. Rename the module and tool |
| `pyproject.toml` | Packages `mcps/`; exposes console `email-phishing-iocs` | Set `name` and `[project.scripts] <console> = "mcps.<module>:main"` |
| `data/smaller_test.csv` + `build_dataset.py` | Labeled eval rows; the builder assembles a sender-inclusive `email` column | Drop in your rows; edit the assembly to the fields your agent reads |
| `email-phishing-eval.yml` | Eval config (`question_key: email`, `answer_key: label`, `id_key: subject`) | Point the keys at your columns; tune the judge weights/prompt |
| `tests/test_extract_iocs.py` | Unit tests for the tool | Rewrite for your tool's contract |

## Keep in sync

Two couplings break silently if you rename one side only:

- **Console name:** `pyproject.toml` `[project.scripts]` **must equal** `agent.yaml` → `mcp.servers.<name>.url`.
- **Workspace member:** add your directory to the **root** `pyproject.toml` `members`, then `uv sync --all-packages` — this installs the console so `--mode subprocess` can launch it.

Keep the `mcps/` directory name (a shared namespace across examples); rename the *module* inside it and the console, not the directory. `id_key` (default `subject`) must be unique across your rows — `build_dataset.py` fails generation on duplicates.

## Adding or removing a specialist

Specialists are entries in `harnesses.deepagents.settings.deepagents.subagents`.
Each needs a `name`, a `description` (this is what the orchestrator routes on —
say when to use it, not just what it is), and a `system_prompt`. Three rules the
existing ones follow:

- **Give it a crisp output contract.** Each specialist's first line is a single
  lowercase token (`credential`, `paypal`, `spf`, `none`) with reasoning after,
  so the verdict sub-agent can lift the value without parsing prose.
- **Paste the material in.** Sub-agents are stateless — they see only the task
  text. The orchestrator prompt tells it to inline the full email on every
  delegation; keep that if you add specialists.
- **Repeat the untrusted-data guardrail** in every specialist prompt. Email
  content is attacker-controlled; each prompt says to treat it as evidence, never
  as instructions.

Then wire it into the orchestrator's numbered steps and, if it produces a field
you want in the output, add that key to the verdict schema in both the
orchestrator prompt and the verdict sub-agent's prompt.

A specialist that has no data to read will invent one. `header-auth-analyst` is
gated on the email actually containing `Authentication-Results:`/`Received:`
headers for exactly that reason — and the scored dataset deliberately has none,
since synthesizing them would leak the label into the input.

## Steps

1. **Copy** this directory to `nemo-agent-config/<your-agent>/` — a working starting point.
2. **Rename** the identifiers above (`pyproject.toml`, `agent.yaml`, the module) — keep the console name in sync.
3. **Register:** add your directory to the root `pyproject.toml` `members`, then `uv sync --all-packages` — the console lands on `PATH`.
4. **Swap the tool** in `mcps/<module>.py` and update `tests/` — your logic runs.
5. **Swap the brains:** the orchestrator `instructions.system` and the sub-agent `system_prompt` / `model` — your domain.
6. **Swap the data** and the eval keys — your evaluation set.

Re-run the [README.md](README.md) tutorial against your agent name to validate.

## Related

- **Config reference:** the `nemo-agent-config` skill (authoring + validation for `nemo-agents-spec-v1`).
- **Deploy options:** [docs/agents/deploy-agents.mdx](../../../../../docs/agents/deploy-agents.mdx).
