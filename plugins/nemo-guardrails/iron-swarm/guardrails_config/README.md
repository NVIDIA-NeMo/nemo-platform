# `guardrails_config/` — the NeMo Guardrails config (you author this)

What the built-in `nemo_guardrails` plugin's worker runs. This directory is Iron
Swarm's actual deliverable.

- **`prompts.yml`** — **your per-tool policy.** One `guardrail__<tool>__<check>` task
  per check; `actions.py` runs *every* check for a tool and blocks if any fires
  (NAT's block-if-any chain). This is the file you edit as your research evolves.
- **`actions.py`** — write-once boilerplate: the judge action that renders the
  matching prompt, calls the model, and parses ALLOW/BLOCK.
- **`config.yml`** — the judge model; **`rails.co`** — the single `tool call gate` flow.
