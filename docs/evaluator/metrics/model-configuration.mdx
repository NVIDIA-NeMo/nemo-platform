<a id="eval-metrics-model-configuration"></a>
# Model Configuration

Online evaluations use `Model` objects for model endpoints. A model can be the evaluation target that produces outputs, or it can be part of a judge-style metric such as LLM-as-a-Judge, RAG, or agentic metrics.

The Evaluator plugin SDK uses inline model objects from `nemo_evaluator_sdk`. Pass the model either as `target=...` or as a field on the metric class that needs a judge or embeddings model.

## Initialize the SDK

```python
import os

from nemo_evaluator.sdk import Evaluator
from nemo_platform import NeMoPlatform


client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
evaluator: Evaluator = client.evaluator  # this object is an Evaluator resource
```

## Inline Model

Define the endpoint URL and model name directly:

```python
from nemo_evaluator_sdk import Model


model = Model(
    url="https://integrate.api.nvidia.com/v1",
    name="meta/llama-3.1-70b-instruct",
    format="nim",
    api_key_secret="NVIDIA_API_KEY",
)
```

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | Base URL of the inference endpoint. |
| `name` | Yes | Model name to send in inference requests. |
| `format` | No | API format: `"nim"`, `"openai"`, or `"llama_stack"`. Defaults to `"nim"`. |
| `api_key_secret` | No | Model API key reference. See [Model API Authentication](#model-api-authentication). |

<a id="model-api-authentication"></a>

## Model API Authentication

`api_key_secret` is an optional property on the `Model` object. Omit it when the endpoint does not require API-key authentication.

For local `evaluator.run(...)` calls, `api_key_secret` must name an environment variable available to the local Python process. For example, `api_key_secret="NVIDIA_API_KEY"` reads `os.environ["NVIDIA_API_KEY"]`.

For remote `evaluator.submit(...)` jobs, `api_key_secret` must name a NeMo platform secret in the target workspace. Create the secret before submitting the job:

```python
client.secrets.create(
    name="nvidia-api-key",
    value=os.environ["NVIDIA_API_KEY"],
)
```

## Model as the Evaluation Target

Use `target=model` when the evaluator should call the model to generate the sample output before scoring.

{% raw %}

```python
from nemo_evaluator_sdk import (
    RunConfigOnlineModel,
    ExactMatchMetric,
    InferenceParams,
    Model,
)


model = Model(
    url="https://integrate.api.nvidia.com/v1",
    name="meta/llama-3.1-70b-instruct",
    format="nim",
    api_key_secret="NVIDIA_API_KEY",
)

metric = ExactMatchMetric(reference="{{item.expected_answer}}")

result = evaluator.run(
    metric=metric,
    dataset=[
        {"question": "What is the capital of France?", "expected_answer": "Paris"},
    ],
    config=RunConfigOnlineModel(
        parallelism=4,
        inference=InferenceParams(temperature=0.1, max_tokens=64),
    ),
    target=model,
    prompt_template="Answer this question concisely: {{item.question}}",
)
```

{% endraw %}

## Model on a Judge Metric

Use a model field on the metric when the metric itself calls an LLM to score existing outputs.

{% raw %}

```python
from nemo_evaluator_sdk import Model, RangeScore, LLMJudgeMetric

judge_model = Model(
    url="https://integrate.api.nvidia.com/v1",
    name="meta/llama-3.1-70b-instruct",
    format="nim",
    api_key_secret="NVIDIA_API_KEY",
)
metric = LLMJudgeMetric(
    model=judge_model,
    scores=[
        RangeScore(
            name="correctness",
            description="Correctness from 1 to 5.",
            minimum=1,
            maximum=5,
        ),
    ],
    prompt_template={
        "messages": [
            {
                "role": "system",
                "content": "Return JSON with a correctness score from 1 to 5.",
            },
            {
                "role": "user",
                "content": "Question: {{item.question}}\nAnswer: {{item.output}}\nExpected: {{item.expected_answer}}",
            },
        ],
    },
)

result = evaluator.run(
    metric=metric,
    dataset=[
        {
            "question": "What is the capital of France?",
            "output": "Paris",
            "expected_answer": "Paris",
        },
    ],
)
```

{% endraw %}

## Runtime Parameters

Use `RunConfigOnlineModel` for model-target evaluations:

```python
from nemo_evaluator_sdk import (
    RunConfigOnlineModel,
    InferenceParams,
    ReasoningParams,
)


params = RunConfigOnlineModel(
    parallelism=4,
    request_timeout=60,
    max_retries=2,
    ignore_request_failure=False,
    inference=InferenceParams(temperature=0.2, max_tokens=256),
    reasoning=ReasoningParams(end_token="</think>"),
)
```

Use plain `RunConfig` for offline evaluations where the dataset already contains the output to score.

## Model References

The plugin SDK examples on this page use inline `Model` objects. If your deployment resolves platform model entities into model endpoint details, perform that lookup before constructing the `Model`, then pass the resulting inline model to the metric or request.

!!! info
    For evaluating agentic systems, use an `Agent` request target instead of a `Model`. See [Agent Configuration](agent-configuration.md).
