# ProfBench Agent-Eval Example

Run the example from the repository root:

```bash
python -m packages.nemo_evaluator_sdk.examples.profbench.runner --output-dir env/profbench-results --limit=1
```

Each invocation creates one run directory under `--output-dir`, then writes each enabled runner mode under that run:

```text
env/profbench-results/
  20260604_161501_61063_eb0cf0/
    baseline/
      evidence/
        profbench-dataset.jsonl
      report.html
      sdk-report.html
    live-judge/
      evidence/
        profbench-dataset.jsonl
        judge-*.json
      report.html
      sdk-report.html
    live-candidate/
      evidence/
        profbench-dataset.jsonl
        judge-*.json
      report.html
      sdk-report.html
```

Live paths are enabled by default and require API access through the configured model settings. Pass `--no-run-live-judge` or `--no-run-live-candidate` to skip either live path.

## Runner Types

`run_examples` always runs the **baseline** path; the other two run by default and can be disabled with `--no-run-live-judge` and `--no-run-live-candidate`. They differ along two axes: **whose answers are scored** and **how rubrics are decided**.

## Comparison

| | **Baseline** | **Live judge** | **Live candidate** |
|---|---|---|---|
| **Answers** | Pre-recorded in the dataset (`o3`, `r1-0528`, `grok4`) | Same pre-recorded answers | **New** answers from `_evaluated_model()` |
| **Rubric scoring** | Dataset labels (`{model}_fulfilment` in JSONL) | Live LLM judge per criterion | Live LLM judge per criterion |
| **API / cost** | None (offline) | Judge calls only | Inference + judge calls |
| **Default in `run_examples`** | Always | Enabled by default (`--no-run-live-judge` disables) | Enabled by default (`--no-run-live-candidate` disables) |

## 1. `run_profbench_baseline_example` - reproduce published scores

```python
async def run_profbench_baseline_example(
    *,
    limit: int | None,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
) -> None:
    """Score the ProfBench baseline model responses bundled in the dataset."""
    ...
    output_dir = _profbench_output_dir(output_root, run_instance_id, "baseline")
    benchmark = load_profbench(_profbench_source(), limit=limit, evidence_dir=output_dir / "evidence")
    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        attempts=benchmark.attempts,
        ...
    )
```

- `load_profbench` with **no judge** and `include_cached_fulfilments=True` (default).
- Each attempt gets `profbench_fulfilments` from the dataset; `ProfBenchRubricMetric` uses those (`score_source: "dataset_label"`) and never calls a judge.
- Fast, deterministic check that loading and scoring work without credentials.

## 2. `run_profbench_live_judge_example` - same text, new judge

```python
benchmark = load_profbench(
    _profbench_source(),
    limit=limit,
    judge=ProfBenchModelJudge(model=judge_model),
    evidence_dir=output_dir / "evidence",
    include_cached_fulfilments=False,
)

result = await AgentEvaluator().run(
    tasks=benchmark.tasks,
    attempts=benchmark.attempts,
    ...
)
```

- Still scores the **bundled** baseline responses via `attempts=benchmark.attempts`.
- `include_cached_fulfilments=False` drops precomputed labels so every criterion goes through `ProfBenchModelJudge` (`score_source: "judge"`).
- Useful to validate your judge model/setup against fixed candidate outputs, without running the candidate model.

## 3. `run_profbench_live_candidate_example` - generate + judge

```python
evaluated_model = _evaluated_model()
params = RunConfigOnlineModel(
    parallelism=2,
    inference=InferenceParams(temperature=0.0, max_tokens=4096),
)
result = await AgentEvaluator().run(
    tasks=benchmark.tasks,
    target=evaluated_model,
    config=AgentEvalRunConfig(
        output_dir=output_dir,
        params=params,
        benchmark={**benchmark.metadata, "score_source": "fresh_candidate_and_live_judge"},
        ...
    ),
)
```

- **No** `attempts=` - the evaluator calls the **target** model (`RunConfigOnlineModel`, parallelism 2, `temperature=0`, `max_tokens=4096`) to produce answers, then scores them with the same live judge.
- Full "evaluate my model on ProfBench" path: new responses + live rubric judging.
- Most expensive; needs inference and judge API access.

## Scoring Logic

All three use `ProfBenchRubricMetric`. Cached labels win when present; otherwise a judge is required:

```python
if criterion.id in fulfilments:
    fulfilled = fulfilments[criterion.id]
else:
    if self.judge is None:
        raise ValueError("ProfBench candidate scoring requires a judge when dataset labels are absent")
    score_source = "judge"
```

- **Baseline**: fulfilments always present, so it uses dataset labels only.
- **Live judge / live candidate**: fulfilments are stripped, so the judge runs on every criterion; candidate path additionally supplies fresh `output_text` from the target model instead of dataset response fields.
