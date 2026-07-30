---
name: benchmark-execution
description: "Benchmark task execution contract: complete every numbered requirement, execute tool calls directly (never plan-only), and verify final state with a direct retrieve/list before responding. Use for every agentic-use benchmark task."
---
# Benchmark execution contract

This skill defines the execution requirements that every nemo-agent run under
`tests/agentic-use/` must satisfy so the canonical gate
(`tests/agentic-use/passrate_token_policy_gate.py`) can score the run on
verifier pass-rate and token totals. See
[`tests/agentic-use/README.md`](../../../../../../tests/agentic-use/README.md)
for the full Run -> Gate -> Optimize loop these tasks plug into.

- Treat `instruction.md` as the task contract: finish all numbered requirements.
- Execute tool calls yourself; do not end with a plan-only response.
- Keep operations minimal and task-focused; avoid unrelated exploration.
- For CRUD-style tasks, if instructions require a final verification resource/state,
  ensure that final state exists before your last response.
- Before final response, run one direct verification call that checks the required
  end state from the instruction (for example: retrieve/list/get status).
