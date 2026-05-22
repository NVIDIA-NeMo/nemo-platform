<a id="eval-benchmark-results"></a>
# Benchmark Results

When a benchmark job completes, the platform automatically creates a **benchmark job result** — a persistent, queryable entity that captures the outcome of that run. Each result is created exactly once per completed job and shares the job's name.

A result contains:
- **Per-metric results**: for each metric in the benchmark, an entry with aggregate scores (mean, min, max, std dev, count, NaN count, etc.) computed across all dataset rows.
- **References**: the benchmark definition, dataset, and model used in the job, enabling cross-job filtering and comparison.

Results are stored independently of the job so you can list, filter, and compare them at any time without re-running evaluations. Use the SDK to:
- [`aggregate_scores`](#get-aggregate-scores): view aggregated statistics for each metric in the benchmark.
- [`row_scores`](#get-row-level-scores): download scores computed per dataset row (JSONL).
- [`benchmark_job_results`](#list-results): list, filter, and compare aggregated results across different evaluation jobs.

## Get Aggregate Scores

Retrieve aggregate score and statistics for all metrics in your benchmark evaluation:

```python
aggregate = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
    job="my-job-name",
)

for score in aggregate.scores:
    print(f"{score.name}: mean={score.mean} type={score.score_type}")
```

The benchmark aggregate payload contains:
- `results[].scores[]`: aggregated score objects across all metrics in the benchmark
- Range scores: `score_type="range"` with percentiles and histogram
- Rubric scores: `score_type="rubric"` with rubric distribution and mode category
- Common stats: `count`, `nan_count`, `sum`, `mean`, `min`, `max`, `variance`, `std_dev`

## Get Row-Level Scores

Retrieve per-row scores for deeper analysis:

```python
row_scores = client.evaluation.benchmark_jobs.results.row_scores.download(
    job="my-job-name",
)

# Iterate through rows (JSONL format)
for row in row_scores:
    item = row.item  # Original dataset row
    sample = row.sample  # Model output payload (often empty for offline jobs)
    metrics = row.metrics  # Dict[str, List[MetricScore]] keyed by metric reference
    requests = row.requests  # Request/response logs captured during evaluation

    for metric_ref, scores in metrics.items():
        for score in scores:
            print(f"{metric_ref}:{score.name}={score.value}")
```

Each JSONL row contains:
- `item`: The original dataset row
- `sample`: Model output payload
- `metrics`: Scores for each metric, keyed by metric reference
- `requests`: Captured request logs

## List Results

List all benchmark job results in a workspace:

```python
for benchmark_job in client.evaluation.benchmark_job_results.list():
    for metric_result in benchmark_job.results:
        print(
            f"{benchmark_job.name} / {metric_result.metric}: {[s.name for s in metric_result.scores]}"
        )
```

Unlike metric results, each benchmark result contains a `results` list — one entry per metric in the benchmark — where each entry holds the aggregate scores for that metric.

Filter by benchmark, dataset, or model using the `filter` parameter to compare scores across models for a given benchmark, or to isolate results from a specific dataset or model. Filter values expect references with the `workspace/name` format.

```python
results = client.evaluation.benchmark_job_results.list(
    filter={"benchmark": "my-workspace/my-benchmark"},
)
```

Select the score's aggregate fields to return in the payload:

```python
results = client.evaluation.benchmark_job_results.list(aggregate_fields=["mean"])
```

Sort results:

```python
# Sort by creation time (newest first):
results = client.evaluation.benchmark_job_results.list(sort="-created_at")
```

Use the `filter` parameter to query across result fields. Filterable fields are `name`, `benchmark`, `dataset`, `model`, and `created_at`. Bare string values default to an exact (`$eq`) match. Use the JSON operator syntax for more control:

| Operator | Meaning |
|----------|---------|
| `$eq` | Exact match |
| `$like` | Substring match |
| `$lt`, `$lte`, `$gt`, `$gte` | Numeric / date comparisons |
| `$in`, `$nin` | Match / exclude a list of values |
| `$and`, `$or`, `$not` | Logical operators |

```python
# Substring match on name:
results = client.evaluation.benchmark_job_results.list(
    filter={"name": {"$like": "llama"}}
)

# Exact match on name:
results = client.evaluation.benchmark_job_results.list(filter={"name": "llama"})

# Results created after a specific date:
results = client.evaluation.benchmark_job_results.list(
    filter={"created_at": {"$gt": "2025-01-01T00:00:00"}}
)
```

### Pagination

`list()` returns a paginated response. Iterating directly over the response automatically fetches subsequent pages:

```python
for result in client.evaluation.benchmark_job_results.list():
    print(result.name)
```

Control page size and page number explicitly with the `page` and `page_size` parameters:

```python
page = client.evaluation.benchmark_job_results.list(page=1, page_size=25)

print(f"Page {page.pagination.page} of {page.pagination.total_pages}")
print(f"{page.pagination.total_results} total results")

for result in page.data:
    print(result.name)
```

## Manage Results

### Get a Specific Result

Retrieve a single benchmark result by job name:

```python
result = client.evaluation.benchmark_job_results.retrieve("my-job-name")
```

### Delete a Result

A job result can be deleted. A deleted result will no longer appear when listing and comparing results. A result may be redundant, misleading, or erroneous — for example, a result with a high NaN count across metrics may not be suitable for comparison.

```python
client.evaluation.benchmark_job_results.delete("my-job-name")
```

## Parse Results

The examples below require pandas.

```shell
uv add pandas
```

### Using Pandas for Analysis

`BenchmarkJobResult.results` is a list of per-metric entries, each with a `metric` reference and its own `scores` list. Load aggregate scores into a single DataFrame:

```python
import pandas as pd

aggregate = client.evaluation.benchmark_job_results.retrieve("my-job-name")

rows = []
for metric_result in aggregate.results:
    for score in metric_result.scores:
        row = score.to_dict()
        row["metric_ref"] = metric_result.metric
        rows.append(row)

df_agg = pd.DataFrame(rows)
print(df_agg[["metric_ref", "name", "mean", "std_dev", "min", "max", "count"]])
```

Example output (range scores):

```output
 metric_ref name mean std_dev min max count
0 my-workspace/exact-match exact-match 0.6 0.49 0.0 1.0 5
1 my-workspace/string-check string-check 0.8 0.40 0.0 1.0 5
```

Load row-level scores for detailed analysis:

```python
import pandas as pd

row_scores = client.evaluation.benchmark_jobs.results.row_scores.download(
    job="my-job-name",
)

# Flatten row scores into a DataFrame
rows = []
for row in row_scores:
    flat_row = {**row.item}
    for metric_ref, scores in row.metrics.items():
        for score in scores:
            flat_row[f"{metric_ref}:{score.name}"] = score.value
    rows.append(flat_row)

df_rows = pd.DataFrame(rows)
print(df_rows)
```

Example output:

```output
 input output reference exact-match string-check
0 What is 2+2? The answer is 4 4 0.0 1.0
1 Capital of France? Paris is the capital Paris 0.0 1.0
2 Color of sky? Blue blue 1.0 0.0
3 Largest planet? Jupiter Jupiter 1.0 1.0
4 Water formula? H2O H2O 1.0 1.0
```

Identify low-scoring samples for review:

```python
# Find rows where any score is below threshold
score_cols = df_rows.select_dtypes(include="number").columns
low_scores = df_rows[df_rows[score_cols].min(axis=1) < 0.7]
print(f"Found {len(low_scores)} samples needing review")
```
