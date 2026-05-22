<a id="nemo-ms-evaluator-about"></a>
# About Evaluating

Evaluation is powered by {{platform_name}}, a cloud-native platform for evaluating large language models (LLMs), RAG pipelines, and AI agents at enterprise scale. The evaluation API provides automated workflows for over 100 industry benchmarks, LLM-as-a-judge scoring, and specialized metrics for RAG and agent systems.

{{platform_name}} enables real-time evaluations of your LLM application through APIs, guiding you in refining and optimizing LLMs for enhanced performance and real-world applicability. The {{nem_short_name}} APIs can be seamlessly automated within development pipelines, enabling faster iterations without the need for live data. It is cost-effective and suitable for pre-deployment checks and regression testing.

[**Tutorials**](tutorials/index.md){ .md-button }
[**Open Source SDK**](https://github.com/NVIDIA-NeMo/evaluator){ .md-button }

---

## How It Works: Library + Platform

Evaluator separates **evaluation definition** from **execution**.

!!! note
    The code snippets below are for conceptual demonstration purposes only.
    For runnable examples see the [tutorials](tutorials/index.md) and [SDK resources](sdk-resources.md).

### 1. Build RunConfig with the Library

Use the `nemo_evaluator_sdk` package to define your metric, dataset rows, runtime configuration, and optional model or agent target:

{% raw %}

```python
from nemo_evaluator_sdk import RunConfig, ExactMatchMetric


# Define metric logic
metric = ExactMatchMetric(
    reference="{{item.expected}}",
    candidate="{{item.output}}",
)

# Build evaluation input
dataset = [
    {"expected": "Paris", "output": "Paris"},
    {"expected": "Berlin", "output": "Munich"},
]
config = RunConfig(limit_samples=100, parallelism=8)
```

{% endraw %}

**The library handles:** Metric definitions, dataset row schemas, prompt templates, model and agent targets, runtime parameters, retries, aggregation, and typed result objects.


### 2. Execute on the Platform

Submit your evaluation to the Evaluator service using the {{platform_name}} SDK:

```python
from nemo_evaluator.sdk import Evaluator
from nemo_platform import NeMoPlatform


sdk = NeMoPlatform(base_url="...", workspace="default")
evaluator: Evaluator = sdk.evaluator

# Fast local iteration through the plugin runtime
local_result = evaluator.run(metric=metric, dataset=dataset, config=config)

# Production evaluation as a durable platform job
job = evaluator.submit(metric=metric, dataset=dataset, config=config)
job.wait_until_done()
result = job.get_result()
```

**The platform handles:** Job orchestration, inference routing through {{platform_name}}'s Inference Gateway, Fileset-based datasets, distributed execution, artifact storage, status monitoring, and result download.

## Key Differences from Standalone Library

When using Evaluator as a {{platform_name}} plugin :

| Feature | Standalone Library | {{platform_name}} Plugin |
|---------|-------------------|-------------|
| **Execution** | Local Python process | Local plugin runs for local experimentation and durable platform jobs for production |
| **Inference** | Direct model or agent endpoint calls | The same as standalone and can also route through {{platform_name}} Inference Gateway and platform-managed endpoints |
| **Datasets** | Inline rows and local files | Inline rows, local paths resolved at submission time, and {{platform_name}} [Filesets](../get-started/concepts/manage-files.md) |
| **Results Artifacts** | Results stored in memory  | {{platform_name}} artifact storage with typed result download |
| **Authentication** | Local environment variables | Local environment variables for local runs and {{platform_name}} Secrets service for remote jobs |

---

## Evaluation Concepts

{{platform_name}} supports two core evaluation primitives:

-   **Metrics**: Scoring logic that evaluates model outputs. Use metrics when you need flexible, reusable scoring for your own datasets and task-specific criteria.

There are two execution modes and two evaluation patterns:

-   **Live evaluation (synchronous)**: Submit a request and get results immediately. Best for fast iteration, metric development, and small payloads.
-   **Jobs (asynchronous)**: Submit work, monitor status, and fetch results when complete. Best for production workloads, larger datasets, and recurring regression checks.

-   **Offline evaluation**: Score existing dataset rows (for example, model outputs already generated).
-   **Online evaluation**: Generate outputs from a model as part of evaluation, then score them.

For deeper details, see [Evaluation Metrics](metrics/index.md).

---

## Tutorials

After [setting up a local instance of the platform](../get-started/setup.md), use the following tutorials to learn how to accomplish common evaluation tasks. These step-by-step guides help you evaluate models using different benchmarks and metrics.

<div class="grid cards" markdown>

-   **[Run an LLM Judge Eval](tutorials/run-llm-judge-evaluation.md)**

    ---

    Learn how to evaluate a fine-tuned model using the LLM Judge metric with a custom dataset.

    <small><span class="md-tag">custom-dataset</span></small>

</div>

---

## Recommended Evaluation Journey

Most teams get the best results by starting metric-first, then moving to benchmarks:

1. **Develop and validate your metrics first**
 - Start with [Metrics](metrics/index.md) to define how quality should be scored for your use case.
 - Use live evaluation (`POST /v2/workspaces/{workspace}/evaluation/metric-evaluate`) with small `DatasetRows` payloads to iterate quickly.

1. **Scale metric evaluation to jobs**
 - When metrics are validated, run async metric jobs (`/evaluation/metric-jobs`) on larger datasets.
 - Use filesets for production-scale inputs. See [Manage Files](../get-started/concepts/manage-files.md).

1. **Monitor and analyze results**
 - Track job status and progress with job management APIs.
 - Retrieve results and artifacts for analysis, reporting, and regression tracking.

---

## Where to Go Next

- For metric workflows, see [Metric Jobs](metrics/index.md) and [Metric Results](metrics/results.md).
- For full endpoint details, see the [Evaluator API Reference](../api/index.md#tag-evaluator).

---

### Available Evaluations

Review configurations, data formats, and result examples for each evaluation.

-   **Retrieval** — Evaluate document retrieval pipelines on standard or custom datasets.
-   **RAG** — Evaluate Retrieval Augmented Generation pipelines (retrieval plus generation).
-   **Agentic** — Assess agent-based and multi-step reasoning models, including topic adherence and tool use.
-   **LLM-as-a-Judge** — Use another LLM to evaluate outputs with flexible scoring criteria. Define custom rubrics or numerical ranges.
-   **Similarity Metrics** — Create metrics for text similarity, exact matching, and standard NLP evaluations using Jinja2 templating.
