<a id="eval-benchmarks-custom"></a>
# Custom Benchmarks

Custom benchmarks allow you to create reusable evaluation suites tailored to your specific use case. A benchmark combines one or more [metrics](../metrics/index.md) with a dataset, enabling consistent evaluation across multiple models or pipeline versions.

!!! note
    Custom benchmarks can only include custom metrics that you create in your workspace. System metrics (in the `system` workspace) cannot be included in custom benchmarks at this time. To use system metrics, refer to [Industry Benchmarks](industry.md).

## Prerequisites

Before creating a custom benchmark, ensure you have:

- A [workspace](../../get-started/concepts/workspaces.md) created for your project
- One or more [custom metrics](../metrics/index.md) defined in your workspace
- A dataset uploaded as a [fileset](../../get-started/concepts/manage-files.md)

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
```

!!! tip
    Set `NMP_BASE_URL` to your {{nem_short_name}} deployment endpoint. See [CLI and SDK initialization](../../get-started/setup.md#setup-init) for the full convention.

## Dataset Requirements

Your dataset must be compatible with all metrics in the benchmark. Each metric defines input templates (like `{%raw%}{{output}}{%endraw%}` and `{%raw%}{{reference}}{%endraw%}`) that map to columns in your dataset.

For **offline evaluation**, your dataset should contain pre-generated model outputs as a JSON array:

```json
[
  {
    "input": "What is the capital of France?",
    "output": "Paris",
    "reference": "Paris"
  },
  {
    "input": "What is 2+2?",
    "output": "4",
    "reference": "4"
  }
]
```

For **online evaluation**, your dataset contains inputs that will be sent to the model. The `prompt_template` you provide must reference columns in your dataset:

```json
[
  {
    "question": "What is the capital of France?",
    "expected_answer": "Paris"
  },
  {
    "question": "What is 2+2?",
    "expected_answer": "4"
  }
]
```

!!! note
    Upload your dataset to a fileset in any [supported format](../metrics/similarity.md). You can select specific files using a `#` fragment pattern (for example, `my-workspace/my-fileset#data.csv`). If no pattern is specified, all parsable files in the fileset are loaded.

!!! info
    Ensure your dataset columns match both:

    1. The input templates defined in your metrics (for example, `{%raw%}{{output}}{%endraw%}`, `{%raw%}{{reference}}{%endraw%}`)
    2. The `prompt_template` used in online evaluation jobs (for example, `{%raw%}{{question}}{%endraw%}`)

For schema-aware validation, prefer canonical evaluator fields in metric prompts and online job prompts:

- use `{{input}}`, `{{output}}`, `{{reference}}`, and `{{context}}` in prompts
- use benchmark or job `field_mapping` to connect those prompt fields to dataset columns such as `question`, `answer`, or `ground_truth`
- use `optional_fields` on metrics or online job requests when a prompt field like `reference` should be available when present but not required in every dataset row
- add fileset metadata such as `dataset.schema` and `dataset.schemas_by_path` when you want benchmark creation and job submission to validate dataset compatibility before a run starts
- remember that benchmark-level `field_mapping` applies to every metric in the benchmark

Legacy raw dataset variables such as `{% raw %}{{question}}{% endraw %}`, `{% raw %}{{item.question}}{% endraw %}`, or `{% raw %}{{item.response}}{% endraw %}` still work. In that case, prompt variable names are matched directly against dataset columns unless `field_mapping.custom` remaps them.

## Create a Custom Benchmark

A benchmark requires:

- **name**: Unique identifier within the workspace
- **description**: Human-readable description of what the benchmark evaluates
- **metrics**: List of metric references in `workspace/metric-name` format
- **dataset**: Fileset reference in `workspace/fileset-name` format

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

benchmark = client.evaluation.benchmarks.create(
    name="customer-support-quality",
    description="Evaluates response quality for customer support conversations",
    metrics=[
        "my-workspace/answer-relevancy",
        "my-workspace/response-helpfulness",
    ],
    dataset="my-workspace/support-test-cases",
    field_mapping={
        "input": "question",
        "reference": "expected_answer",
    },
)

print(f"Created benchmark: {benchmark.name}")
```

Refer to [Manage Benchmarks](manage-benchmarks.md) for listing and managing custom benchmarks.

## Run Benchmark Evaluation Jobs

After creating a benchmark, run evaluation jobs against it. There are two job types:

| Job Type | Use When | Dataset Contains |
|----------|----------|------------------|
| **Offline** | You have pre-generated model outputs to evaluate | Input, output, and reference columns |
| **Online** | You want to generate and evaluate responses in one job | Input and reference columns (model generates output) |

**Choose offline evaluation** for:

- Evaluating pre-generated model outputs (for example, from batch inference)
- Comparing multiple model versions on the same test set

**Choose online evaluation** for:

- Testing a model endpoint with live inference
- End-to-end evaluation that generates and scores outputs in a single job

### Offline Evaluation

Offline evaluation assesses pre-existing model outputs stored in your dataset. Use this when you have already generated responses and want to evaluate their quality.

```python
from nemo_platform.types.evaluation import BenchmarkOfflineJobParam

job = client.evaluation.benchmark_jobs.create(
    spec=BenchmarkOfflineJobParam(
        benchmark="my-workspace/customer-support-quality",
    ),
)

print(f"Job created: {job.name}")
print(f"Status: {job.status}")
```

#### With Execution Parameters

Control job execution with optional parameters:

```python
from nemo_platform.types.evaluation import (
    BenchmarkOfflineJobParam,
    RunConfigParam,
)

job = client.evaluation.benchmark_jobs.create(
    spec=BenchmarkOfflineJobParam(
        benchmark="my-workspace/customer-support-quality",
        params=RunConfigParam(
            parallelism=8,
            limit_samples=100,  # Evaluate only first 100 samples
        ),
    ),
)
```

### Online Evaluation

Online evaluation generates model responses at runtime, then evaluates them against your metrics. Use this to evaluate a model's live performance.

The `model` field accepts either an inline model definition or a model reference. Refer to [Model Configuration](../metrics/model-configuration.md) for details on both formats.

#### With Inline Model

```python
{% raw %}
from nemo_platform.types.evaluation import (
    BenchmarkOnlineJobParam,
    ModelParam,
)

job = client.evaluation.benchmark_jobs.create(
    spec=BenchmarkOnlineJobParam(
        benchmark="my-workspace/customer-support-quality",
        model=ModelParam(
            url="https://integrate.api.nvidia.com/v1/chat/completions",
            name="meta/llama-3.1-8b-instruct",
            api_key_secret="nvidia-api-key",
        ),
        prompt_template="Answer the following customer question:\n\n{{input}}",
    ),
)
{% endraw %}
```

#### With Model Reference

```python
{% raw %}
from nemo_platform.types.evaluation import BenchmarkOnlineJobParam

job = client.evaluation.benchmark_jobs.create(
    spec=BenchmarkOnlineJobParam(
        benchmark="my-workspace/customer-support-quality",
        model="my-workspace/llama-3-1-8b-instruct",
        prompt_template="Answer the following customer question:\n\n{{input}}",
    ),
)
{% endraw %}
```

## Job Management

After successfully creating a job, navigate to [Benchmark Job Management](job-management.md) to oversee its execution and monitor progress.

## Retrieve Results

After the job completes, retrieve and analyze results. Refer to [Benchmark Results](results.md) for detailed examples of downloading aggregate scores, row-level scores, and analyzing results with Pandas.

## Complete Example

Here is a complete workflow for creating a benchmark and running an evaluation.

!!! note
    This example assumes you have already created the metrics (`exact-match`, `f1-score`) and uploaded your dataset (`qa-test-data`). Refer to [Evaluation Metrics](../metrics/index.md) for how to create custom metrics.

```python
import json
import time

import os
from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import (
    BenchmarkOfflineJobParam,
    RunConfigParam,
)

workspace = "default"
client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace=workspace,
)

# 1. Create a custom benchmark
benchmark = client.evaluation.benchmarks.create(
    name="qa-accuracy-benchmark",
    description="Measures answer accuracy for Q&A tasks",
    metrics=[f"{workspace}/exact-match", f"{workspace}/f1-score"],
    dataset=f"{workspace}/qa-test-data",
)
print(f"Created benchmark: {benchmark.name}")

# 2. Run an offline evaluation job
job = client.evaluation.benchmark_jobs.create(
    spec=BenchmarkOfflineJobParam(
        benchmark=f"{workspace}/{benchmark.name}",
        params=RunConfigParam(parallelism=16),
    ),
)
print(f"Started job: {job.name}")

# 3. Wait for completion
status = client.evaluation.benchmark_jobs.get_status(name=job.name)
while status.status in ("pending", "active", "created"):
    print(f"Status: {status.status}")
    time.sleep(10)
    status = client.evaluation.benchmark_jobs.get_status(name=job.name)

print(f"Job completed: {status.status}")

# 4. Get results
if status.status == "completed":
    results = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
        job=job.name,
    )
    print("Results:")
    print(results.to_json(indent=2))
```

## Troubleshooting

### Common Errors

**"Benchmark not found"**

- Verify the benchmark reference format: `workspace/benchmark-name`
- Ensure the benchmark was created in the correct workspace
- Check that the benchmark was not deleted

**"Metric not found"**

- Ensure all metrics referenced in the benchmark exist in your workspace
- Remember that system metrics (`system/...`) cannot be used in custom benchmarks
- Verify metric names match exactly (case-sensitive)

**"Fileset not found"**

- Verify the dataset fileset was uploaded to the correct workspace
- Check the fileset reference format: `workspace/fileset-name`
- Ensure at least one file was uploaded to the fileset

**Job status "error"**

- Check job logs using `client.evaluation.benchmark_jobs.get_logs(name=job.name)` for specific error messages
- Verify your dataset columns match the metric input templates
- For online jobs, verify the model endpoint is accessible and the API key is valid

**Dataset column mismatch**

- Ensure your dataset contains all columns referenced by your metrics
- For offline jobs: typically `input`, `output`, `reference`
- For online jobs: columns referenced in your `prompt_template`

### Debugging Tips

1. **Start small**: Test with `limit_samples=10` to quickly identify issues
2. **Check logs**: Always review job logs when a job fails
3. **Validate dataset**: Ensure your dataset files are valid and columns/keys are consistent across rows
4. **Test metrics first**: Run individual metric evaluations before combining into a benchmark

For additional help, refer to [Troubleshooting](../../troubleshooting/evaluator.md).
