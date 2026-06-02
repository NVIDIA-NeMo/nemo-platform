# NeMo Evaluator SDK

## Quickstart

```python
from nemo_evaluator_sdk import Evaluator, ExactMatchMetric, RunConfig

dataset = [
    {"reference": "Paris", "actual": "Paris"},
    {"reference": "London", "actual": "Berlin"},
]

evaluator = Evaluator()
exact_match = ExactMatchMetric(reference="{{item.reference}}", candidate="{{item.actual}}")

result = evaluator.run_sync(
    metrics=exact_match,
    dataset=dataset,
    config=RunConfig(parallelism=4),
)

result.print_summary()
rows_df = result.to_pandas()
aggregate_df = result.to_pandas(view="aggregate")
```

`await Evaluator.run(...)` and `Evaluator.run_sync(...)` are the recommended product-level APIs for scripts and notebooks. They accept:
- inline rows
- `DatasetRows`
- `pyarrow.Table`
- a local file path
- a local directory path plus an optional `dataset_glob_pattern`

The returned `EvaluationResult` supports:
- `print_summary()`
- `format_summary()`
- `to_records()`
- `to_table()`
- `to_pandas()`

Pandas conversion is optional. Install `nemo-evaluator-sdk[pandas]` to use `to_pandas()`.

Offline evaluation uses each dataset row as both `item` and `sample`. In practice,
that means templates should usually read directly from the row, for example
`{{item.answer}}` and `{{item.model_output}}`.

## Running in Async Context

For async execution, use `run(...)` from an async context:

```python
from nemo_evaluator_sdk import Evaluator, ExactMatchMetric, RunConfig

evaluator = Evaluator()
exact_match = ExactMatchMetric(
    reference="{{item.reference}}",
    candidate="{{item.actual}}",
)

result = await evaluator.run(
    metrics=exact_match,
    dataset=[{"reference": "4", "actual": "4"}],
    config=RunConfig(parallelism=1),
)
```
