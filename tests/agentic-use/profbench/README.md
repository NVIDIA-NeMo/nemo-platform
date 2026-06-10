# ProfBench Agent-Eval Task

This task lets the runtime PoC evaluate a selected backend on ProfBench through
the SDK benchmark adapter.

Run a one-row workflow smoke from the repository root:

```bash
NVIDIA_API_KEY=... \
uv run python tests/agentic-use/runtimes/run_agent_eval.py \
  --task profbench \
  --backend workflow \
  --allow-dirty \
  --model nvidia/nemotron-3-nano-30b-a3b \
  --limit 1
```

`--task profbench` is special: ProfBench rows come from
`ProfBenchAgentEvalBenchmark`, not from `instruction.md`. With
`--backend workflow`, candidate answers are generated through the SDK `Model`
target using `--model`/`--agent-model`; this intentionally avoids binding NeMo
MCP tools to pure ProfBench prompts. ProfBench scoring uses the live judge
configured by `--judge-model-*` flags.
