# Mock LLM configurations

These `.env` files configure the upstream `benchmark.mock_llm_server.run_server`
(from the `NeMo-Guardrails` checkout) for the IGW guardrails benchmark.

We keep our own copies (instead of pointing at the upstream checkout's
`benchmark/mock_llm_server/configs/`) so:

- We can change mock latency without touching the upstream repo. The original
  motivation was tuning `E2E_LATENCY_*` to isolate NMP+middleware overhead
  from mandatory NIM sleep (see the benchmark README for the full rationale).
- The exact mock behavior we benchmarked against is versioned alongside the
  results, so historical numbers stay reproducible even if upstream changes
  its defaults.

Initial contents are a verbatim copy of the upstream files:

- `app-llm.env`            ← upstream `meta-llama-3.3-70b-instruct.env`
- `content-safety-llm.env` ← upstream `nvidia-llama-3.1-nemoguard-8b-content-safety.env`

Update either file to change mock behavior for the next benchmark run.
