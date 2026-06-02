FROM nmp-agentic-base:latest

# Keep this eval CLI-only; agents must use /app/.venv/bin/nemo.
RUN rm -f /app/.mcp.json

SKILL_EVAL_JUDGE_MODEL=openai/openai/gpt-5.5 \
ASTRA_SKILL_EVAL_DEBUG=1 \
uv run astra-skill-eval evaluate /Users/ngoncharenko/code/microservices/nemo-platform/plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin \
  --deep --agent-eval -a codex \
  --agent-model codex=openai/openai/gpt-5.5 \
  --results-dir env/astra-results \
  --harbor-keep-jobs
  