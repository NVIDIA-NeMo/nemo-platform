# Discover the Standalone Evaluator SDK Surface

Use the `nemo-evaluator-plugin` skill to produce a runnable standalone Evaluator SDK example.
Read the skill before writing the solution.

Create `/workspace/output/solution.py`. The script must use the local standalone Evaluator SDK from
`packages/nemo_evaluator_sdk` in the checked-out repo context.

Use only `packages/nemo_evaluator_sdk` and SDK-level APIs in your answer. Do not propose the
`nemo` CLI, plugin SDK APIs, or any `services/*` implementation path.

`/workspace/output/solution.py` must include:

- The package/path `packages/nemo_evaluator_sdk`.
- The import or API symbols `Evaluator`, `ExactMatchMetric`, and either `run_sync` or `run`.
- A minimal Python snippet, not a shell command or prose outline, showing how an agent would run a two-row exact-match evaluation locally with the standalone SDK from the repo root.
- This exact two-row dataset:

```json
[
  {"question": "2+2?", "expected": "4", "prediction": "4"},
  {"question": "Capital of France?", "expected": "Paris", "prediction": "Lyon"}
]
```

- An `ExactMatchMetric` configured with `reference="{{item.expected}}"` and `candidate="{{item.prediction}}"`.
- Either a synchronous SDK call such as `Evaluator().run_sync(...)` or an async SDK flow using `await Evaluator().run(...)`.

Your final answer should be a short summary only.
