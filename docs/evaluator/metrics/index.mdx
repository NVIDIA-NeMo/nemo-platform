<a id="eval-metrics-index"></a>
# Evaluation Metrics

Metrics define how to score the outputs of your models, agents, or pipelines.

## What is a metric?

A metric is a scoring definition that evaluates model or agent outputs. In the Evaluator plugin SDK, metrics are inline Python objects passed directly to `evaluator.run(...)` or `evaluator.submit(...)`.

- **Inputs**: For custom metrics, inputs define scoring logic composed of dataset fields and model outputs; for judge-based custom metrics, this also includes judge-model inputs (for example, judge prompts/rubrics and configuration).
- **Outputs**: Row-level scores and aggregate statistics.
- **Execution**: Metric objects run with `dataset`, optional runtime configuration, and an optional model or agent target.

!!! note "Terminology on this page:"
    - **Metric definition**: The reusable scoring configuration.
    - **Metric type**: The metric family (for example exact-match, BLEU, LLM-as-a-judge).
    - **Metric score**: The numeric or rubric output produced at evaluation time.
## The Evaluation Workflow

```text
[1] Choose and configure a metric object
 |
 v
[2] Select a dataset and execution mode
 |
 v
[3] Create and run an evaluation job
 |
 v
[4] Review row-level and aggregate scores
```

## Quick Start

Minimal sync evaluation with a built-in metric:

{% raw %}
```python
import os

from nemo_evaluator.sdk import Evaluator
from nemo_platform import NeMoPlatform
from nemo_evaluator_sdk import ExactMatchMetric

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
evaluator: Evaluator = client.evaluator

metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")

result = evaluator.run(
    metric=metric,
    dataset=[
        {"expected": "Paris", "output": "Paris"},
        {"expected": "Berlin", "output": "Munich"},
    ],
)

print(result.aggregate_scores)
```
{% endraw %}

## Execution Modes

Metrics can be executed in two modes:

| Mode | Use Case | Response |
|------|----------|----------|
| **Live Evaluation** | Rapid prototyping, developing metrics, testing configurations. | Immediate (synchronous) |
| **Job Evaluation** | Production workloads, full datasets, durability, and persistence | Async (poll for completion) |

### Online Job Targets: Model or Agent

Online evaluation jobs can target either a **model** (an OpenAI-compatible chat completions endpoint) or an **agent** (any HTTP endpoint, including agentic systems with tool use and multi-step reasoning). Provide one or the other — the platform routes your request to the correct job type automatically.

| Target | When to use |
|--------|-------------|
| **Model** | Standalone LLM endpoints using a standard chat completions API. |
| **Agent** | Agentic systems, NeMo Agent Toolkit workflows, or custom HTTP endpoints with non-standard response formats. |

See [Model Configuration](model-configuration.md) and [Agent Configuration](agent-configuration.md) for setup details.

## Built-in vs. Custom Metrics

- **Built-in metrics**: Ready-to-use metrics provided by {{platform_name}} (for example `exact-match`, `bleu`, `rouge`).
- **Custom metrics**: Metrics you define for domain-specific evaluation needs.

To configure inline metric objects, see [Manage Metrics](manage-metrics.md).
For custom metric creation guides, start with [Similarity Metrics](similarity.md), [LLM-as-a-Judge](llm-as-a-judge.md), or [Bring Your Own Metric](remote.md).

## Datasets

Evaluation jobs need dataset input. You can provide data in two ways:

| Dataset Source | Description | Best For |
|------|-------------|----------|
| **DatasetRows** | Inline rows sent directly in the request | Quick testing and live evaluation |
| **FilesetRef** | Reference to a persisted [fileset](../../get-started/concepts/manage-files.md) (`workspace/fileset-name`) | Production jobs and reusable datasets |

Example of providing a `FilesetRef` to reference specific files or globs:

```python
# Include all files in subdirectory
dataset = "my-workspace/my-dataset#subdir/path"

# Single file
dataset = "my-workspace/my-dataset#file.jsonl"

# Single file in a subdirectory
dataset = "my-workspace/my-dataset#subdir/path/file.jsonl"

# Glob match files
dataset = "my-workspace/my-dataset#*.jsonl"

# Glob match files in subdirectory
dataset = "my-workspace/my-dataset#subdir/path/*.jsonl"
```

## Available Metric Types

Use the metric-type pages below to create and configure custom metrics.

<div class="grid cards" markdown>

-   **[LLM-as-a-Judge](llm-as-a-judge.md)**

    ---

    Use another LLM to evaluate outputs with flexible scoring criteria. Define custom rubrics or numerical ranges.

    <small><span class="md-tag">custom-scoring</span> <span class="md-tag">rubrics</span></small>

-   **[Agentic Metrics](agentic.md)**

    ---

    Evaluate agent workflows including tool calling accuracy, goal completion, and topic adherence.

    <small><span class="md-tag">RAGAS</span> <span class="md-tag">tool-calling</span></small>

-   **[RAG Metrics](rag.md)**

    ---

    Evaluate RAG pipelines for retrieval quality and answer generation using RAGAS metrics.

    <small><span class="md-tag">faithfulness</span> <span class="md-tag">relevancy</span></small>

-   **[Similarity Metrics](similarity.md)**

    ---

    Create metrics for text similarity, exact matching, and standard NLP evaluations using Jinja2 templating.

    <small><span class="md-tag">F1</span> <span class="md-tag">ROUGE</span> <span class="md-tag">BLEU</span></small>

-   **[Bring Your Own Metric](remote.md)**

    ---

    Integrate custom evaluation endpoints for domain-specific scoring.

    <small><span class="md-tag">remote</span> <span class="md-tag">custom</span></small>

-   **[Agent Configuration](agent-configuration.md)**

    ---

    Configure agent endpoints (generic or NeMo Agent Toolkit) as targets for online evaluation jobs.

    <small><span class="md-tag">agent</span> <span class="md-tag">NAT</span></small>

</div>

## Understanding Scores

Scores are the metric outputs produced during evaluation:

| Score Type | Meaning | Typical Use |
|------|---------|-------------|
| **Row scores** | Score(s) for each dataset row | Debugging failures and error analysis |
| **Aggregate scores** | Statistics computed over all rows | Tracking overall quality and regressions |

## Manage Metric Definitions

Create inline metric objects that can be reused from Python helpers or modules. See [Manage Metrics](manage-metrics.md) for SDK patterns.
