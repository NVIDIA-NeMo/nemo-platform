<a id="eval-metrics-llm-as-a-judge"></a>
# Evaluate with LLM-as-a-Judge

Use another LLM to evaluate outputs from your model or dataset with flexible scoring criteria. LLM-as-a-Judge is useful for creative, complex, or domain-specific tasks where traditional metrics do not capture the behavior you care about.

## Overview

LLM-as-a-Judge evaluation sends each dataset row to a judge LLM and parses the judge response into score values that you define. You can evaluate:

- **Model outputs**: Score responses generated during an online evaluation.
- **Pre-generated data**: Score existing question-answer pairs or conversations.
- **Custom criteria**: Define range scores, rubric scores, prompt templates, and parser behavior.

{{nem_short_name}} supports two execution modes through the Evaluator plugin SDK:

| Mode | Use Case | SDK Call |
|------|----------|----------|
| **Local execution** | Rapid prototyping, metric development, and synchronous workflows | `evaluator.run(metric=metric, dataset=dataset)` |
| **Durable remote job** | Production workloads that should run as platform jobs | `evaluator.submit(metric=metric, dataset=dataset)` |

## Prerequisites

Before running LLM-as-a-Judge evaluations:

1. **Workspace**: Have a workspace created. Platform resources such as secrets and jobs are scoped to a workspace.
2. **Judge LLM endpoint**: Have access to an LLM that will serve as your judge, such as a NIM endpoint or OpenAI-compatible API.
3. **API key (if required)**: If your judge endpoint requires authentication, create a platform secret in the same workspace and reference it from the judge model.
4. **Initialize the SDK**:

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

---

## Local Execution

!!! tip
    The `model` field accepts both inline model definitions and model references (for example, `"my-workspace/my-model"`). Refer to [Model Configuration](model-configuration.md) for details.

Live evaluation is designed for rapid iteration when developing and refining your evaluation metrics. Use it to quickly test different judge prompts, scoring criteria, and data formats before committing to a full evaluation job. Results return immediately, making it easy to experiment and debug.

### Basic Example with Range Scores

Evaluate responses using numerical range scores, such as a 1-5 scale:

{% raw %}
```python
from nemo_evaluator_sdk import (
    InferenceParams,
    JSONScoreParser,
    Model,
    RangeScore,
    RunConfig,
    LLMJudgeMetric
)


metric = LLMJudgeMetric(
    model=Model(
        url="<judge-nim-url>/v1",
        name="meta/llama-3.1-70b-instruct",
        format="nim",
    ),
    scores=[
        RangeScore(
            name="helpfulness",
            description="How helpful is the response (1=not helpful, 5=extremely helpful)",
            minimum=1,
            maximum=5,
            parser=JSONScoreParser(json_path="helpfulness"),
        ),
        RangeScore(
            name="accuracy",
            description="How accurate is the response (1=incorrect, 5=completely accurate)",
            minimum=1,
            maximum=5,
            parser=JSONScoreParser(json_path="accuracy"),
        ),
    ],
    inference=InferenceParams(temperature=0.0, max_tokens=1024),
    prompt_template={
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert judge. Rate each response on two dimensions "
                    "(1-5 scale): helpfulness and accuracy. Respond with JSON: "
                    '{"helpfulness": <1-5>, "accuracy": <1-5>}'
                ),
            },
            {
                "role": "user",
                "content": "Question: {{item.input}}\n\nResponse: {{item.output}}\n\nRate this response.",
            },
        ]
    },
)


result = evaluator.run(
    metric=metric,
    dataset=[
        {
            "input": "What is the capital of France?",
            "output": "The capital of France is Paris.",
        },
        {
            "input": "How do I make coffee?",
            "output": "Boil water, add grounds to a filter, pour water over the grounds, and let it drip.",
        },
    ],
)

for score in result.aggregate_scores.scores:
    print(f"{score.name}: mean={score.mean:.2f}, count={score.count}")

for row in result.row_scores:
    print(row.row_index, row.item, row.metrics)
```
{% endraw %}

The result includes aggregate scores and row scores. Row scores are useful when you are debugging the prompt or parser because they show how each individual row was scored.

??? "Example Response"
    :icon: code-square

    ```python
    {
        "aggregate_scores": {
            "scores": [
                {"name": "helpfulness", "count": 2, "mean": 4.5, "min": 4.0, "max": 5.0},
                {"name": "accuracy", "count": 2, "mean": 4.0, "min": 3.0, "max": 5.0},
            ]
        },
        "row_scores": [
            {
                "row_index": 0,
                "item": {
                    "input": "What is the capital of France?",
                    "output": "The capital of France is Paris.",
                },
                "metrics": {
                    "llm-judge": {"scores": [{"name": "helpfulness", "value": 5.0}]}
                },
            }
        ],
    }
    ```

### Example with Rubric Scores

Use rubric scores when you want categorical labels with explicit descriptions:

{% raw %}
```python
from nemo_evaluator_sdk import JSONScoreParser, Model, RubricScore, LLMJudgeMetric

metric = LLMJudgeMetric(
    model=Model(
        url="<judge-nim-url>/v1",
        name="meta/llama-3.1-70b-instruct",
        format="nim",
    ),
    scores=[
        RubricScore(
            name="quality",
            description="Overall quality of the response",
            rubric=[
                {
                    "label": "poor",
                    "value": 0,
                    "description": "Response is unhelpful or incorrect",
                },
                {
                    "label": "acceptable",
                    "value": 1,
                    "description": "Response is partially correct",
                },
                {
                    "label": "good",
                    "value": 2,
                    "description": "Response is correct and helpful",
                },
                {
                    "label": "excellent",
                    "value": 3,
                    "description": "Response is comprehensive and insightful",
                },
            ],
            parser=JSONScoreParser(json_path="quality"),
        ),
        RubricScore(
            name="completeness",
            description="How complete the answer is",
            rubric=[
                {
                    "label": "incomplete",
                    "value": 0,
                    "description": "Missing key information",
                },
                {
                    "label": "partial",
                    "value": 1,
                    "description": "Covers main points but lacks detail",
                },
                {
                    "label": "complete",
                    "value": 2,
                    "description": "Fully addresses the question",
                },
            ],
            parser=JSONScoreParser(json_path="completeness"),
        ),
    ],
    prompt_template={
        "messages": [
            {
                "role": "system",
                "content": (
                    "Rate each response:\n"
                    "- quality: poor | acceptable | good | excellent\n"
                    "- completeness: incomplete | partial | complete\n\n"
                    'Respond with JSON: {"quality": "<label>", "completeness": "<label>"}'
                ),
            },
            {
                "role": "user",
                "content": "Question: {{item.input}}\n\nResponse: {{item.output}}\n\nRate this response.",
            },
        ]
    },
)

result = evaluator.run(
    metric=metric,
    dataset=[
        {
            "input": "Tell me a joke",
            "output": "Why did the chicken cross the road? To get to the other side!",
        },
        {"input": "Explain quantum physics", "output": "I don't know."},
    ],
    aggregate_fields=("rubric_distribution", "mode_category"),
)

print(result.aggregate_scores.model_dump(exclude_none=True))
```
{% endraw %}

### Custom Aggregate Fields

By default, aggregate scores include `count`, `mean`, `min`, and `max`. Request additional statistics with `aggregate_fields`:

{% raw %}
```python

result = evaluator.run(
    metric=metric,
    dataset=[
        {"input": "What is the capital of France?", "output": "Paris."},
        {"input": "What is 2 + 2?", "output": "4."},
    ],
    aggregate_fields=("std_dev", "variance", "percentiles", "histogram"),
)

for score in result.aggregate_scores.scores:
    print(f"{score.name}:")
    print(f" mean: {score.mean:.3f}")
    print(f" std_dev: {score.std_dev:.3f}")
    if score.percentiles:
        print(f" p50: {score.percentiles.p50:.3f}")
        print(f" p90: {score.percentiles.p90:.3f}")
```
{% endraw %}

---

## Durable Remote Jobs

For production workloads, submit the same metric and dataset as a durable platform job. The SDK returns a job resource that can wait for completion and download the final `EvaluationResult`.

{% raw %}
```python
from nemo_evaluator_sdk import RunConfig, JSONScoreParser, Model, RubricScore, LLMJudgeMetric

metric = LLMJudgeMetric(
    model=Model(
        url="<judge-nim-url>/v1",
        name="meta/llama-3.1-70b-instruct",
        format="nim",
    ),
    scores=[
        RubricScore(
            name="quality",
            description="Overall quality of the response",
            rubric=[
                {"label": "poor", "value": 0, "description": "Response is unhelpful"},
                {"label": "good", "value": 1, "description": "Response is helpful"},
                {
                    "label": "excellent",
                    "value": 2,
                    "description": "Response is exceptional",
                },
            ],
            parser=JSONScoreParser(json_path="quality"),
        )
    ],
    prompt_template={
        "messages": [
            {
                "role": "system",
                "content": 'Rate response quality as poor, good, or excellent. Respond with JSON: {"quality": "<label>"}',
            },
            {
                "role": "user",
                "content": "Question: {{item.input}}\n\nResponse: {{item.output}}",
            },
        ]
    },
)


job = evaluator.submit(
    metric=metric,
    dataset=[
        {
            "input": "What is the capital of France?",
            "output": "Paris is the capital of France.",
        },
        {"input": "What is 2 + 2?", "output": "4"},
    ],
    config=RunConfig(parallelism=8, limit_samples=100),
)
print("Submitted job:", job.name)

job.wait_until_done()
result = job.get_result()

for score in result.aggregate_scores.scores:
    print(f"{score.name}: mean={score.mean}, count={score.count}")
```
{% endraw %}

---

## Score Configuration

LLM-as-a-Judge supports two types of scores: **range scores** (numerical ratings) and **rubric scores** (categorical classifications).

### Choosing Between Range and Rubric Scores

**We recommend using rubric scores over range scores for most evaluation tasks.** Classification-based rubrics (for example, pass/fail, safe/unsafe, poor/good/excellent) typically outperform numerical scoring (1-10) because:

- **Reduces ambiguity**: Categorical labels with explicit descriptions are easier for judge models to apply consistently than numerical scales
- **Aligns with human reasoning**: People naturally think in categories rather than precise numerical gradations
- **Avoids calibration issues**: Numerical scores suffer from inconsistent calibration—one judge's "7" may be another's "5"
- **Provides actionable insights**: Clear categories (for example, "needs_improvement", "acceptable", "excellent") are more actionable than abstract numbers
- **More reliable metrics**: Classification tasks produce more consistent and reproducible results across different judge models

**Use range scores when:**

- You need fine-grained distinctions that do not map well to categories
- You are measuring continuous quantities (for example, latency, word count)
- Downstream analysis requires numerical operations on scores

**Use rubric scores when:**

- You are evaluating quality dimensions (helpfulness, accuracy, safety)
- Clear decision boundaries exist (pass/fail, compliant/non-compliant)
- Results will guide human decisions or workflows

### Range Scores

Use range scores for numerical ratings on a continuous scale:

```python
{
    "name": "relevance",
    "description": "How relevant is the response (1=irrelevant, 5=highly relevant)",
    "minimum": 1,
    "maximum": 5,
    "parser": {"type": "json", "json_path": "relevance"},
}
```

### Rubric Scores

Use rubric scores for categorical evaluations with explicit criteria:

```python
{
    "name": "sentiment",
    "description": "Sentiment of the response",
    "rubric": [
        {"label": "negative", "value": -1, "description": "Response has negative tone"},
        {"label": "neutral", "value": 0, "description": "Response is neutral"},
        {"label": "positive", "value": 1, "description": "Response has positive tone"},
    ],
    "parser": {"type": "json", "json_path": "sentiment"},
}
```

!!! tip
    Rubric scores use [structured outputs](https://docs.nvidia.com/nim/large-language-models/latest/structured-generation.html) by default, which constrains the judge model to output valid JSON. This significantly reduces parsing errors.

### Score Parsers

Configure how scores are extracted from judge responses:

| Parser Type | Use Case | Example Pattern |
|-------------|----------|-----------------|
| `json` | Judge outputs JSON (default) | `{"type": "json", "json_path": "score_name"}` |
| `regex` | Extract from free-form text | `{"type": "regex", "pattern": "SCORE: (\\d+)"}` |

By default, the JSON parser is used for range and rubric scores, with the score name as the `json_path` to extract the value from.

```python
# JSON parser (default)
"parser": {"type": "json", "json_path": "quality"}

# Regex parser (for models that do not support structured output)
"parser": {"type": "regex", "pattern": "QUALITY: (\\w+)"}

# Regex parser with method='search' (finds pattern anywhere in text)
"parser": {"type": "regex", "pattern": "SCORE: (\\d+)", "method": "search"}
```

!!! tip
    **Regex method options:**

    - `match` (default): Matches the pattern only at the **beginning** of the text. Use when your prompt instructs the judge to output the score first.
    - `search`: Finds the pattern **anywhere** in the text. Uses the first match of the regex found in the judge output.

    For example, with `method: "search"` and pattern `SCORE: (\d+)`, the parser can extract the score from:

    ```text
    The response is accurate and well-written. SCORE: 5
    ```

    This would fail with the default `match` method since "SCORE:" is not at the beginning. If multiple matches exist, `search` returns the first occurrence.

---

## Custom Judge Prompts

Customize the judge prompt to match your evaluation criteria. Use Jinja2 templating to access data fields and score definitions.

### Template Variables

| Variable | Description |
|----------|-------------|
| `{%raw%}{{input}}{%endraw%}` | Input field from dataset row |
| `{%raw%}{{output}}{%endraw%}` | Output field from dataset row |
| `{%raw%}{{context}}{%endraw%}`, `{%raw%}{{reference}}{%endraw%}`, `{%raw%}{{messages}}{%endraw%}`, `{%raw%}{{tool_calls}}{%endraw%}`, `{%raw%}{{tools}}{%endraw%}` | Other canonical evaluator fields |
| `item.<field>` | Any field from the dataset row |
| `sample.output_text` | Model-generated response (when evaluating a model) |
| `scores` | Dictionary of score definitions (typically used in expressions/loops, for example `{% raw %}{{ scores.keys() | join(", ") }}{% endraw %}`) |

### Canonical vs Legacy Prompt Variables

LLM judge prompt variables define the fields required from the evaluation context:

{% raw %}
- Prefer canonical evaluator variables such as `{{input}}`, `{{output}}`, `{{context}}`, and `{{reference}}` for reusable metrics.
- Raw dataset variables such as `{{item.question}}`, `{{item.response}}`, `{{question}}`, or `{{sample.output_text}}` continue to work for backward compatibility.
{% endraw %}

When your dataset uses different field names, keep the metric prompt stable and map dataset columns at job or benchmark submission time with `field_mapping`:

```python
metric = {
    "type": "llm-judge",
    "model": {...},
    "scores": [...],
    "prompt_template": {
        "messages": [
            {"role": "system", "content": "Return JSON with {'score': <1-5>}"},
            {"role": "user", "content": "Question: {{input}}\nResponse: {{output}}"},
        ]
    },
}

job = {"field_mapping": {"input": "question", "output": "response"}}
```

With the mapping above, a dataset row like this:

```json
{
  "question": "What is the capital of France?",
  "response": "Paris"
}
```

renders the prompt template variables as:

{% raw %}
- `{{input}}` -> `question` -> `"What is the capital of France?"`
- `{{output}}` -> `response` -> `"Paris"`

Custom prompt variables are also allowed. For example, `{{input}} {{output}} {{custom_value}}` produces a required schema with all three fields, and `field_mapping.custom.custom_value` can bind that prompt variable to a dataset column when needed.

When no `field_mapping` is provided, prompt variable names are matched directly against dataset columns. That means a prompt using `{{question}}` and `{{response}}` expects dataset rows with `question` and `response` fields unless you remap them explicitly.
{% endraw %}

If a prompt field should be available when present but not required in every row, add it to `optional_fields` on the metric. This is useful for prompts that can use `reference` when available but should still validate against datasets that only provide `input` and `output`.

```python
metric = {
    "type": "llm-judge",
    "model": {...},
    "scores": [...],
    "optional_fields": ["reference"],
    "prompt_template": {
        "messages": [
            {
                "role": "user",
                "content": "Question: {{input}}\nResponse: {{output}}\nReference: {{reference}}",
            }
        ]
    },
}
```

`optional_fields` keeps the field in the inferred input schema but removes it from the required field list. If the field is present in the dataset, the prompt can still use it.

### Schema-Aware Validation

{{nem_short_name}} derives the required prompt fields directly from the prompt variables used by the metric and validates them against dataset metadata during benchmark and job creation.

- Add fileset metadata `dataset.schema` for a default row schema.
- Add `dataset.schemas_by_path` when different files in the same fileset have different row shapes.
- Use benchmark or job `field_mapping` to map prompt variables such as `input`, `output`, or custom names onto dataset columns.
- Use `optional_fields` when a prompt variable may be absent from some datasets but should still be available when provided.
- Required fields mean the key must be present in each dataset row selected for evaluation.
- Nullable fields use JSON Schema types such as `["integer", "null"]`, which means the key is still expected but the value may be `null`.

Benchmark-level `field_mapping` is shared by every metric in that benchmark. If two metrics need different bindings for the same prompt variable, either give the metrics different prompt variable names or split them into separate benchmarks.

### Example: Custom Judge Template

```python
{% raw %}
JUDGE_TEMPLATE = """You are an expert evaluator assessing AI assistant responses.

Evaluate the response on these criteria:
{% for score_name, score in scores.items() %}
- {{ score_name }}{% if score.description %}: {{ score.description }}{% endif %}
{% if score.rubric %}
 Options: {% for r in score.rubric %}{{ r.name }}{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}
{% endfor %}

Respond with JSON containing your ratings.
"""

metric = {
 "type": "llm-judge",
 "model": {
 "url": "<judge-url>/v1",
 "name": "meta/llama-3.1-70b-instruct",
 "format": "nim"
 },
 "scores": [
 {
 "name": "clarity",
 "description": "How clear and understandable is the response",
 "rubric": [
 {"label": "confusing", "value": 0, "description": "Hard to understand"},
 {"label": "clear", "value": 1, "description": "Easy to understand"},
 {"label": "crystal_clear", "value": 2, "description": "Exceptionally well explained"}
 ],
 "parser": {"type": "json", "json_path": "clarity"}
 }
 ],
 "prompt_template": {
 "messages": [
 {"role": "system", "content": JUDGE_TEMPLATE},
 {"role": "user", "content": "Question: {{input}}\n\nResponse: {{output}}"}
 ]
 }
}
{% endraw %}
```

---

## Managing Secrets for Authenticated Endpoints

If your judge model endpoint requires an API key, store it as a secret. The secret is automatically resolved from the same workspace as your evaluation.

For local `run` versus remote `submit` behavior of `api_key_secret`, see [Model API Authentication](model-configuration.md#model-api-authentication).

### Create a Secret

```python
# Create a secret with your API key
client.secrets.create(name="judge-api-key", value="your-api-key-here")
```

### Reference the Secret in Your Metric

```python
metric = {
    "type": "llm-judge",
    "model": {
        "url": "https://api.example.com/v1",
        "name": "gpt-4",
        "format": "openai",
        "api_key_secret": "judge-api-key",
    },
    # ... scores and prompt_template
}
```

---

## Inference Parameters

Control judge model behavior with inference parameters:

```python
{% raw %}
"prompt_template": {
    "messages": [...],
    "temperature": 0.1, # Lower for more consistent scoring
    "max_tokens": 1024, # Increase if judge needs more space
    "timeout": 30, # Request timeout in seconds
    "stop": ["<{{ end_of_text }}>"] # Stop sequences
}
{% endraw %}
```

!!! note "The default value for `max_tokens` for judge models is set to `1024`. It is highly recommended to set an appropriate value for your judge model based on the expected outputs (for example, `structured_output` is used by default to format model output, ensure your `max_tokens` is set to accommodate the full JSON output). Incomplete JSON outputs will cause parsing errors and result in NaN score values."

### Reasoning Model Configuration

For reasoning-enabled models (like Nemotron), configure reasoning parameters:

```python
metric = {
    "type": "llm-judge",
    "model": {
        "url": "<nim-url>/v1",
        "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "format": "nim",
    },
    # ... scores ...
    "system_prompt": "'detailed thinking on'",
    "reasoning": {"end_token": "</think>"},
    "prompt_template": {"messages": [...], "temperature": 0.1, "max_tokens": 4096},
}
```

---

<a id="eval-flows-llm-as-a-judge-limitations"></a>
## Limitations

1. **Judge Model Quality**: Evaluation quality depends on the judge model's ability to follow instructions. Larger models (70B+) typically produce more consistent results.

2. **NaN Scores**: If the judge output cannot be parsed, the score is marked as `NaN`. Common causes:
 - Insufficient `max_tokens` (check for `"finish_reason": "length"` in results)
 - Judge model not following output format instructions
 - Use structured outputs or explicit format instructions to reduce NaN rates

3. **Structured Output Requirement**: Rubric scores require the judge model to support [guided decoding](https://docs.nvidia.com/nim/large-language-models/latest/structured-generation.html). If your judge does not support this, use regex parsers with explicit format instructions.

4. **Live Evaluation Limits**: Live evaluations are limited to 10 rows. Use job-based evaluation for larger datasets.

!!! info

    - [Model Configuration](model-configuration.md) - Inline models vs model references
    - [Evaluation Results](results.md) - Understanding and downloading results
    - [Agentic Evaluation](agentic.md) - Evaluate agent workflows
    - [RAG Evaluation](rag.md) - Evaluate retrieval-augmented generation
