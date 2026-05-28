<a id="eval-benchmarks-index"></a>
# Evaluation Benchmarks

A benchmark is a reusable evaluation suite: one or more metrics paired with a dataset. Instead of redefining metrics and data inputs for every run, you define the benchmark once and run it repeatedly.

Use benchmarks when you want to:

- Standardize model quality measurement across teams and releases
- Run consistent regression checks after model, prompt, or pipeline updates
- Compare multiple model versions using the same scoring criteria and dataset
- Package validated metrics with domain-specific test data for repeatable evaluation

{{platform_name}} supports custom benchmarks: user-defined evaluation suites that combine your choice of metrics with domain-specific datasets.

Custom benchmarks are valuable when standard metrics alone do not capture the nuances of your application, such as legal document analysis, medical terminology accuracy, or enterprise-specific terminology adherence.

## Create Custom Benchmarks

Create a custom benchmark by combining metrics with your dataset. Before creating a benchmark, you will need to [create the metrics](../metrics/index.md) that define how to score your model's outputs.

```python
benchmark = client.evaluation.benchmarks.create(
    workspace="my-workspace",
    name="my-qa-benchmark",
    description="Evaluates question-answering quality",
    metrics=["my-workspace/answer-relevancy", "my-workspace/faithfulness"],
    dataset="my-workspace/qa-test-dataset",
    labels={
        "my-label": "label-value"
    },  # optional user-input labels to apply to the benchmark
)
```

Refer to [Manage Benchmarks](manage-benchmarks.md) for listing and managing custom benchmarks.

## Run Benchmark Jobs

Create a benchmark evaluation job to run the benchmark against your data.

### Offline Job (Dataset Evaluation)

Evaluate a pre-generated dataset:

```python
from nemo_platform.types.evaluation import BenchmarkOfflineJobParam

job = client.evaluation.benchmark_jobs.create(
    workspace="my-workspace",
    spec=BenchmarkOfflineJobParam(
        benchmark="my-workspace/my-qa-benchmark",
    ),
)

print(f"Job created: {job.name}")
```

### Online Job (Model Evaluation)

Evaluate a model directly by generating outputs during the benchmark:

```python
from nemo_platform.types.evaluation import BenchmarkOnlineJobParam

job = client.evaluation.benchmark_jobs.create(
    workspace="my-workspace",
    spec=BenchmarkOnlineJobParam(
        benchmark="my-workspace/my-qa-benchmark",
        model={
            "url": "<your-nim-url>/v1/completions",
            "name": "meta/llama-3.1-8b-instruct",
        },
    ),
)

print(f"Job created: {job.name}")
```

## Manage Benchmarks

List, retrieve, and delete evaluation benchmarks using the Python SDK. You can list custom benchmarks in your workspace, retrieve detailed benchmark configurations, and delete custom benchmarks when no longer needed.

Refer to [Manage Benchmarks](manage-benchmarks.md) for complete SDK examples including pagination, sorting, filtering, and extended response options.

## Job Management

After successfully creating a job, refer to [Benchmark Job Management](job-management.md) to oversee its execution and monitor progress.

## Benchmark Categories

<div class="grid cards" markdown>

-   **[Custom Benchmarks](custom.md)**

    ---

    Compose a custom benchmark with a collection of metrics to evaluate tasks bespoke to your needs.

    <small><span class="md-tag">RAGAS</span> <span class="md-tag">LLM-as-a-Judge</span></small>

</div>
