# Run a Simple Exact-Match Evaluation

Use the `nemo-evaluator-plugin` skill to produce a runnable standalone Evaluator SDK example.
Read the skill before writing the solution.

Create `/workspace/output/solution.py`. The script must use the local standalone Evaluator SDK from
`packages/nemo_evaluator_sdk` in the checked-out repo context.

Evaluate this exact dataset:

```json
[
  {"question": "2+2?", "expected": "4", "prediction": "4"},
  {"question": "Capital of France?", "expected": "Paris", "prediction": "Lyon"}
]
```

`/workspace/output/solution.py` must:

- Use the local standalone Evaluator SDK from `packages/nemo_evaluator_sdk`.
- Select the appropriate SDK metric for exact-match scoring.
- Use `Evaluator().run_sync(...)` to evaluate both rows.
- Use `ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.prediction}}")`.
- Call `print_summary()` on the evaluation result.
- Ensure the printed SDK summary shows one matching row, one mismatching row, and an aggregate exact-match score of `0.5`.

Do not use the `nemo` CLI, plugin SDK APIs, `services/*` implementation paths, or the legacy `nemo evaluation` command group.

Your final answer should be a short summary only.
