# Run a Simple Exact-Match Evaluation

Use the local standalone Evaluator SDK to run this exact-match evaluation:

```json
[
  {"question": "2+2?", "expected": "4", "prediction": "4"},
  {"question": "Capital of France?", "expected": "Paris", "prediction": "Lyon"}
]
```

Use only `packages/nemo_evaluator_sdk` and SDK-level APIs in your answer. Do not propose the `nemo` CLI, plugin SDK APIs, or any `services/*` implementation path.

Write your runnable solution to `workspace/solution.py` from the repo root. The shared task workspace is mounted at `/app/workspace`, so the required artifact path is `/app/workspace/solution.py`.

`workspace/solution.py` must:

- Use the local standalone Evaluator SDK from `packages/nemo_evaluator_sdk`.
- Select the appropriate SDK metric for exact-match scoring.
- Use `Evaluator().run_sync(...)` to evaluate both rows.
- Call `print_summary()` on the evaluation result.
- Ensure the printed SDK summary shows one matching row, one mismatching row, and an aggregate exact-match score of `0.5`.

Your final answer should be a short summary only.
