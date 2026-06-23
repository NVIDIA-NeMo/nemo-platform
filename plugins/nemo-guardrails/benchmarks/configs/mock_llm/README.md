# Mock LLM configurations

These `.env` files configure the behavior of the mock LLMs, used by the upstream
`nemo-guardrails` library's `benchmark.mock_llm_server.run_server`.

The library stores these files, but we keep our own copies so:

- We can change mock latency without touching the upstream repo.
- The exact mock behavior we benchmarked against is versioned alongside the
  results, so historical numbers stay reproducible even if upstream changes
  its defaults.

Mapping to upstream files:
- `app-llm.env`            ← upstream `meta-llama-3.3-70b-instruct.env`
- `content-safety-llm.env` ← upstream `nvidia-llama-3.1-nemoguard-8b-content-safety.env`
