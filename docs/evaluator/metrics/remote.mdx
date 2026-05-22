<a id="eval-metrics-remote"></a>
# Bring Your Own Metric

{{platform_name}} offers [built-in metrics](index.md) that can be configured to evaluate on your custom data. Remote metrics let you bring your own metric logic into the {{platform_name}} evaluation workflow by serving that logic from a REST API.

A remote metric gives you control over the evaluation logic, request payload, and reported scores while the Evaluator plugin SDK handles dataset iteration, result aggregation, retries, and job execution.

## Overview

Remote metrics support two types:

| Type | Use Case | Payload Structure |
|------|----------|-------------------|
| **Generic Remote** (`remote`) | Custom endpoints with configurable request body and score extraction | User-defined Jinja template |
| **NeMo Agent Toolkit Remote** (`nemo-agent-toolkit-remote`) | NeMo Agent Toolkit evaluator endpoints | Fixed: `{evaluator_name, item}` |

{{nem_short_name}} supports two execution modes through the Evaluator plugin SDK:

| Mode | Use Case | SDK Call |
|------|----------|----------|
| **Local execution** | Rapid prototyping and synchronous workflows | `evaluator.run(metric=metric, dataset=dataset)` |
| **Durable remote job** | Production workloads that should run as platform jobs | `evaluator.submit(metric=metric, dataset=dataset)` |

## Prerequisites

Before running remote metric evaluations:

1. **Workspace**: Have a workspace created.
2. **Remote endpoint**: Have your evaluation endpoint running and accessible.
3. **API key (if required)**: If your endpoint requires authentication, [create a secret](#using-api-key-secrets) to store the API key.
4. **Initialize the SDK**:

```python
import os

from nemo_evaluator.sdk import Evaluator
from nemo_platform import NeMoPlatform


from nemo_evaluator_sdk import (
    NemoAgentToolkitRemoteMetric,
    RemoteMetric,
)
sdk = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
evaluator: Evaluator = sdk.evaluator  # this object is an Evaluator resource
```

---

## Local Execution

Local execution provides immediate results for rapid iteration when developing and testing your metrics.

### Generic Remote Metric

Use a generic remote metric when you need full control over the request payload and score extraction:

{% raw %}
```python
from nemo_evaluator_sdk import JSONScoreParser, RemoteScore, RemoteMetric

metric = RemoteMetric(
    url="https://my-evaluation-server.test/evaluate",
    body={
        "reference": "{{item.reference}}",
        "response": "{{item.output}}",
    },
    scores=[
        RemoteScore(
            name="accuracy",
            parser=JSONScoreParser(json_path="$.result.accuracy"),
            description="Measures response accuracy against the reference",
            minimum=0.0,
            maximum=1.0,
        )
    ],
    timeout_seconds=30.0,
    max_retries=3,
)


result = evaluator.run(
    metric=metric,
    dataset=[
        {"reference": "The capital is Paris", "output": "Paris is the capital"},
        {"reference": "2", "output": "2"},
    ],
)

for score in result.aggregate_scores.scores:
    print(f"{score.name}: mean={score.mean}, count={score.count}")
```
{% endraw %}

**Key configuration:**
- `body`: Jinja template for the request payload. Use `{% raw %}{{ item.<column> }}{% endraw %}` to access dataset columns.
- `scores`: List of score definitions with a `parser` object containing [JSONPath](https://datatracker.ietf.org/doc/html/rfc9535) expression for extracting values from the response.

### NeMo Agent Toolkit Remote Metric

Use the NAT remote metric type when integrating with NeMo Agent Toolkit evaluator endpoints:

```python
from nemo_evaluator_sdk import NemoAgentToolkitRemoteMetric

metric = NemoAgentToolkitRemoteMetric(
    url="http://localhost:8001/evaluate_item",
    evaluator_name="similarity_eval",
    timeout_seconds=30.0,
    max_retries=3,
)


result = evaluator.run(
    metric=metric,
    dataset=[
        {
            "id": "item_1",
            "input_obj": "What is the capital of France?",
            "expected_output_obj": "The capital of France is Paris.",
            "output_obj": "Paris is the capital of France.",
            "trajectory": [],
            "expected_trajectory": [],
            "full_dataset_entry": {},
        }
    ],
)

for score in result.aggregate_scores.scores:
    print(f"{score.name}: mean={score.mean}")
```

The NAT metric automatically:

- Sends payload: `{"evaluator_name": "<name>", "item": <row_data>}`.
- Extracts the score from: `$.result.score`.

---

## Durable Remote Jobs

For production workloads, submit the same metric and dataset as a durable platform job. The returned job resource can wait for completion and download the final `EvaluationResult`.

<!-- markdownlint-disable MD046 -->

=== "Generic Remote Metric"

    {% raw %}
    ```python
    from nemo_evaluator_sdk import RunConfig, JSONScoreParser, RemoteScore, RemoteMetric

    metric = RemoteMetric(
        url="https://my-evaluation-server.test/evaluate",
        body={
            "reference": "{{item.reference}}",
            "response": "{{item.output}}",
        },
        scores=[
            RemoteScore(
                name="accuracy",
                parser=JSONScoreParser(json_path="$.result.accuracy"),
                minimum=0.0,
                maximum=1.0,
            )
        ],
        timeout_seconds=30.0,
        max_retries=3,
    )


    job = evaluator.submit(
        metric=metric,
        dataset=[
            {"reference": "Paris", "output": "Paris"},
            {"reference": "2", "output": "2"},
        ],
        config=RunConfig(parallelism=8),
    )
    print("Submitted job:", job.name)

    job.wait_until_done()
    result = job.get_result()

    for score in result.aggregate_scores.scores:
        print(f"{score.name}: mean={score.mean}, count={score.count}")
    ```
    {% endraw %}

=== "NAT Remote Metric"

    ```python
    from nemo_evaluator_sdk import RunConfig, NemoAgentToolkitRemoteMetric

    metric = NemoAgentToolkitRemoteMetric(
        url="http://localhost:8001/evaluate_item",
        evaluator_name="similarity_eval",
        timeout_seconds=30.0,
        max_retries=3,
    )


    job = evaluator.submit(
        metric=metric,
        dataset=[
            {
                "id": "item_1",
                "input_obj": "What is the capital of France?",
                "expected_output_obj": "The capital of France is Paris.",
                "output_obj": "Paris is the capital.",
                "trajectory": [],
                "expected_trajectory": [],
                "full_dataset_entry": {},
            }
        ],
        config=RunConfig(parallelism=4),
    )
    job.wait_until_done()
    result = job.get_result()
    ```

<!-- markdownlint-enable MD046 -->

---

## Using API Key Secrets

If your remote endpoint requires authentication, store the API key as a platform secret and reference it from your metric:

For local `run` versus remote `submit` behavior of `api_key_secret`, see [Model API Authentication](model-configuration.md#model-api-authentication).

{% raw %}
```python
from nemo_evaluator_sdk import JSONScoreParser, RemoteScore, SecretRef, RemoteMetric

metric = RemoteMetric(
    url="https://my-authenticated-endpoint.test/evaluate",
    body={"input": "{{item.input}}"},
    scores=[RemoteScore(name="score", parser=JSONScoreParser(json_path="$.score"))],
    api_key_secret=SecretRef(root="my-remote-api-key"),
)

result = evaluator.run(metric=metric, dataset=[{"input": "test"}])
```
{% endraw %}

The API key is sent in the `Authorization: Bearer <key>` header. For local execution, the SDK resolves the key according to the local `api_key_secret` behavior. For durable remote jobs, the job runtime receives the secret securely.

---

## Endpoint Requirements

Your remote endpoint must:

1. Accept `POST` requests with `Content-Type: application/json`.
2. Return a JSON response containing the score values.

### Example Endpoint (FastAPI)

```python
from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI()


class MetricRequest(BaseModel):
    reference: str
    response: str


class MetricResponse(BaseModel):
    result: dict[str, float]


@app.post("/evaluate")
async def evaluate(request: MetricRequest) -> MetricResponse:
    accuracy = 1.0 if request.reference == request.response else 0.0
    return MetricResponse(result={"accuracy": accuracy})
```

### NAT Endpoint Format

NAT endpoints receive:

```json
{
  "evaluator_name": "similarity_eval",
  "item": {
    "id": "item_1",
    "input_obj": "What is the capital of France?",
    "expected_output_obj": "The capital of France is Paris.",
    "output_obj": "Paris is the capital.",
    "trajectory": [],
    "expected_trajectory": [],
    "full_dataset_entry": {}
  }
}
```

And must return:

```json
{
  "success": true,
  "result": {
    "id": "item_1",
    "score": 0.85,
    "reasoning": {
      "method": "cosine_similarity"
    }
  },
  "error": null
}
```

---

## Configuration Options

### Metric Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | `"remote"` or `"nemo-agent-toolkit-remote"` |
| `url` | string | Endpoint URL |
| `body` | dict | (Generic only) Jinja template for request payload |
| `scores` | list | (Generic only) List of score configuration objects (refer to Score Configuration section) |
| `evaluator_name` | string | (NAT only) Name of the NAT evaluator |
| `api_key_secret` | `SecretRef` | Optional API key reference. See [Model API Authentication](model-configuration.md#model-api-authentication) |
| `timeout_seconds` | float | Request timeout (default: 30.0) |
| `max_retries` | int | Max retry attempts (default: 3) |

### Score Configuration (Generic Remote Only)

Each `RemoteScore` supports:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Score identifier (lowercase, numbers, underscores only) |
| `parser` | object | Yes | Parser configuration for extracting the score value (refer to Parser configuration section) |
| `description` | string | No | Human-readable description of the score |
| `minimum` | float | No | Minimum expected value for the score range (default: None = no bound) |
| `maximum` | float | No | Maximum expected value for the score range (default: None = no bound) |

**Parser configuration:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Parser type, must be `"json"` |
| `json_path` | string | Yes | [JSONPath](https://datatracker.ietf.org/doc/html/rfc9535) expression to extract the score value |

**Example with all fields:**

```python
from nemo_evaluator_sdk import JSONScoreParser, RemoteScore

RemoteScore(
    name="accuracy",
    parser=JSONScoreParser(json_path="$.result.accuracy"),
    description="Measures response accuracy against reference",
    minimum=0.0,
    maximum=1.0,
)
```

---

## Limitations

1. **Network access**: For job-based evaluation, remote metric endpoints must be reachable from the local platform runtime. Use a host or service URL that the platform can access.

2. **Response format**: Scores must be extractable using JSONPath from the response. Ensure your endpoint returns properly structured JSON.

3. **Live evaluation limits**: Live evaluations are limited to 10 rows. Use job-based evaluation for larger datasets.

!!! info
    - [Evaluation Results](results.md) - Understanding and downloading results
    - [LLM-as-a-Judge](llm-as-a-judge.md) - Use an LLM to evaluate outputs
    - [Agentic Evaluation](agentic.md) - Evaluate agent workflows
