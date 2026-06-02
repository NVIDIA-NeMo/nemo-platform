---
name: nemo-evaluator
description: >
  NeMo Evaluator SDK-first rubric-to-eval guide for BYOB (Bring Your Own
  Benchmark): parse domain expert rubrics, choose composable evaluation
  primitives, generate human-reviewable eval configs/artifacts, and run
  reproducible exact, numeric, LLM-as-judge, code/custom, composite,
  RAG/agentic, and tool-calling evaluations. Use when a task involves
  questions/rubrics/responses files, rubric criteria, benchmark scoring,
  evaluator primitive selection, or reusable evaluation artifacts.
compatibility: Designed for use inside the NeMo Platform repository; SDK reference paths are repo-root relative.
metadata:
  user-invocable: "true"
---

# NeMo Evaluator

Use this skill to turn a domain-specific benchmark and expert-written rubric
into a reproducible evaluation. The agent should parse the rubric, choose the
cheapest correct composable primitive for each criterion, generate
human-reviewable config/artifacts, run the evaluation, and explain both scores
and reasoning.

Use the NeMo Evaluator SDK as the source of truth for metric names, fields,
templates, execution modes, result shapes, and failure behavior. Keep this skill
focused on SDK guidance. Use CLI commands only when the user explicitly needs a
remote platform job or an existing platform resource.

## SDK Reference Points

Read these files before guessing a metric schema or execution parameter. 
> Note: paths are relative to the `nemo-platform` repo root installation. In case this is run in the nemo docker container, check /app dir.

- Metric config schemas: `packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/values/metrics.py`
- Metric type names: `packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/enums.py`
- Runtime metric behavior: `packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/metrics/`
- RAGAS runtime metrics: `packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/metrics/ragas/metrics.py`
- Execution API: `packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/execution/evaluator.py`
- Run config types: `packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/values/params.py`
- Request config normalization: `packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/execution/config.py`
- Public examples: `packages/nemo_evaluator_sdk/examples/examples.py`

Prefer the SDK class field names. For example, `StringCheckMetric` uses
`operation`, `left_template`, and `right_template`; do not invent `field` or
`expected_field`.

## Default Loop

1. Identify the BYOB inputs: questions, rubric criteria, responses or live
   model endpoints, weights, pass threshold, and desired summary breakdowns.
2. Clarify the evaluation target: model output quality, judge quality, RAG
   quality, tool use, benchmark regression, or bring-your-own benchmark
   reproduction.
   - Judge-quality evaluation checks whether a judge agrees with labels for
     existing responses.
   - Generator-quality evaluation creates fresh responses and scores those
     responses with a fixed judge or deterministic checker.
3. Choose the cheapest correct SDK metric class or composed set of classes for
   each criterion.
4. Generate a small, human-reviewable config or code artifact instead of
   burying criterion logic in one-off scripts.
5. Build a tiny inline dataset with at least one expected pass and one expected
   fail.
6. Run locally with `Evaluator().run_sync(...)` or `await Evaluator().run(...)`.
7. Inspect `result.print_summary()`, `row_scores`, and `aggregate_scores`.
8. Fix dataset shape, Jinja templates, parser paths, prompts, model config, or
   secrets.
9. Move to remote platform jobs only after the local SDK run behaves as
   expected.

Do not stop at "the score is bad." Explain what failed and what evidence
supports that conclusion.

## Choosing The Right Metric

| Evaluation goal | Prefer | SDK class | Watch for |
| --- | --- | --- | --- |
| Exact label, enum, or string regression | `exact-match` or `string-check` | `ExactMatchMetric`, `StringCheckMetric` | Normalize whitespace/case with Jinja filters if needed |
| Numeric correctness or thresholds | `number-check` | `NumberCheckMetric` | Non-numeric values score `NaN` |
| Reference text similarity | `f1`, `bleu`, or `rouge` | `F1Metric`, `BLEUMetric`, `ROUGEMetric` | Similarity is not factual correctness |
| Flexible semantic quality | `llm-judge` | `LLMJudgeMetric` | Use explicit rubrics and parser-compatible judge output |
| Zero-config semantic quality | `llm-judge` without custom prompt/parsers | `LLMJudgeMetric` with score definitions only | Validate default prompt and parser behavior on tiny data |
| RAG retrieval coverage | `context_recall`, `context_precision`, `context_relevance`, `context_entity_recall` | RAGAS metric classes | Required columns differ by metric |
| RAG grounding or hallucination | `faithfulness`, `response_groundedness`, `noise_sensitivity` | RAGAS metric classes | Requires judge model config |
| RAG answer relevance | `response_relevancy` | `ResponseRelevancyMetric` | Requires judge and embeddings model config |
| Agent final outcome | `agent_goal_accuracy`, `answer_accuracy`, `topic_adherence` | RAGAS agentic metric classes | Most require a judge model |
| Agent tool/function calls | `tool_call_accuracy` or `tool-calling` | `ToolCallAccuracyMetric`, `ToolCallingMetric` | Ground truth and response shape must match the metric |
| Custom business scoring | `remote` or `nemo-agent-toolkit-remote` | `RemoteMetric`, `NemoAgentToolkitRemoteMetric` | Smoke test endpoint auth, payload, timeout, and parser path |
| Repeatable model comparison | Multi-metric SDK run or platform benchmark job | `Evaluator.run(metrics=[...])` or benchmark APIs | Record metric list, dataset, model config, params, and results |
| Bring-your-own benchmark reproduction | Fixed judge plus explicit artifact protocol | SDK harness around generation, judge predictions, and aggregation | Keep generation quality separate from judge-quality evaluation |

## Composable Primitive Mapping

When converting rubric criteria into an eval, use the PRD's primitive mindset
and map it onto the current SDK surface:

| PRD primitive | Use when | Current SDK surface |
| --- | --- | --- |
| `exact` | Criterion checks for a term, phrase, regex-like pattern, or exact output | `ExactMatchMetric`, `StringCheckMetric` |
| `numeric` | Criterion expects a calculated value, threshold, tolerance, or count | `NumberCheckMetric` |
| `llm` | Criterion needs semantic reasoning, style judgment, communication quality, or subjective quality | `LLMJudgeMetric` with `RangeScore` or `RubricScore` |
| `code` | Criterion needs domain-specific computation or validation logic | Custom harness code, `RemoteMetric`, or a reviewed Python checker around SDK results |
| `composite` | One criterion benefits from deterministic checks plus an LLM fallback or weighted subchecks | Multiple SDK metrics plus agent-owned aggregation, or a custom wrapper until a native composite primitive exists |

Prefer deterministic primitives before LLM calls. Use LLM judges for nuance,
not for checks that can be expressed as exact, string, numeric, or code logic.

## SDK Execution Patterns

Use `Evaluator` directly for local, completed-result evaluation. It accepts one
metric or a sequence of metrics and returns either `EvaluationResult` or a
multi-metric benchmark result.

```python
from nemo_evaluator_sdk import Evaluator, RunConfig, StringCheckMetric


metric = StringCheckMetric(
    operation="equals",
    left_template="{{item.output | trim}}",
    right_template="{{item.expected | trim}}",
)

result = Evaluator().run_sync(
    metrics=metric,
    dataset=[
        {"output": "hello", "expected": "hello"},
        {"output": "foo", "expected": "bar"},
    ],
    config=RunConfig(parallelism=4),
)

result.print_summary()
print(result.aggregate_scores)
print(result.row_scores)
```

Run multiple metrics together when evaluating a benchmark-like dataset:

```python
from nemo_evaluator_sdk import Evaluator, ExactMatchMetric, StringCheckMetric


metrics = [
    ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}"),
    StringCheckMetric(
        operation="contains",
        left_template="{{item.output}}",
        right_template="{{item.required_phrase}}",
    ),
]

result = Evaluator().run_sync(metrics=metrics, dataset=rows)
result.print_summary()
print(result.per_metric)
```

Use online generation only when the evaluator should call a model or agent
before scoring. Pass `target=Model(...)` or `target=Agent(...)` and a
`prompt_template`; otherwise keep evaluation offline and put outputs in the
dataset rows.

```python
from nemo_evaluator_sdk import (
    Evaluator,
    ExactMatchMetric,
    InferenceParams,
    Model,
    RunConfigOnlineModel,
)


metric = ExactMatchMetric(reference="{{item.expected}}")
target = Model(
    url="https://provider.example/v1",
    name="<model-id>",
    format="openai",
    api_key_secret="<secret-or-env-name>",
)

config = RunConfigOnlineModel(
        parallelism=1,
        ignore_request_failure=False,
        max_retries=1,
        request_timeout=600,
        inference=InferenceParams(max_tokens=32768, temperature=0.0),
)

result = Evaluator().run_sync(
    metrics=metric,
    target=target,
    dataset=[{"prompt": "What is 2+2?", "expected": "4"}],
    prompt_template={"messages": [{"role": "user", "content": "{{item.prompt}}"}]},
    config=config,
)
```



## LLM Judge Pattern

Use `LLMJudgeMetric` when deterministic metrics cannot capture the behavior.
Define score names, descriptions, ranges or rubrics, parser behavior, judge
model, and prompt template. Score names must use lowercase letters, numbers,
and underscores.

```python
from nemo_evaluator_sdk import Evaluator, JSONScoreParser, LLMJudgeMetric, Model, RangeScore


judge_model = Model(
    url="https://provider.example/v1",
    name="<judge-model-id>",
    format="openai",
    api_key_secret="<secret-or-env-name>",
)

metric = LLMJudgeMetric(
    model=judge_model,
    scores=[
        RangeScore(
            name="quality",
            description="Overall response quality from 1 to 5",
            minimum=1,
            maximum=5,
            parser=JSONScoreParser(json_path="quality"),
        )
    ],
    prompt_template={
        "messages": [
            {
                "role": "system",
                "content": 'Rate response quality from 1 to 5. Return JSON: {"quality": <score>}',
            },
            {
                "role": "user",
                "content": "Input: {{item.input}}\nResponse: {{item.output}}",
            },
        ]
    },
)

result = Evaluator().run_sync(
    metrics=metric,
    dataset=[
        {"input": "Explain photosynthesis.", "output": "Plants use sunlight to make sugars."},
        {"input": "Explain photosynthesis.", "output": "I cannot help."},
    ],
    config=RunConfigOnlineModel(
        parallelism=1,
        inference=InferenceParams(max_tokens=32768),
    ),
)
```

For zero-config judge metrics, provide `model` and rubric/range `scores`, then
omit `prompt_template` and explicit parsers. Run a tiny local evaluation before
using a full dataset.

## Tool Calling Pattern

Use `ToolCallingMetric` when rows contain OpenAI-style tool responses and
ground truth tool calls. It emits:

- `function_name_accuracy`
- `function_name_and_args_accuracy`

```python
from nemo_evaluator_sdk import Evaluator, ToolCallingMetric


metric = ToolCallingMetric(reference="{{item.expected_tool_calls}}")
result = Evaluator().run_sync(metrics=metric, dataset=rows)
```

Each row should include a `response` object shaped like an OpenAI chat
completion with `choices[0].message.tool_calls`. Ground truth should be a list
of OpenAI-style tool call objects with `function.name` and
`function.arguments`. The runtime is case sensitive, order insensitive for
parallel calls, and expects function arguments to be valid JSON strings in the
predicted response.

## RAG And Agentic Metrics

Use RAGAS-backed metric classes from `nemo_evaluator_sdk.metrics.ragas` when the
task is about retrieval, grounding, or agent behavior. Keep dataset columns
aligned with the metric:

| Metric family | Common required fields |
| --- | --- |
| Retrieval quality | `user_input`, `retrieved_contexts`, often `reference` |
| Grounding/hallucination | `user_input`, `response`, `retrieved_contexts`, sometimes `reference` |
| Response relevancy | `user_input`, `response`, `retrieved_contexts` plus embeddings model config |
| Tool call accuracy | `user_input`, `reference_tool_calls` or metric-specific tool-call fields |
| Agent goal/answer/topic | Conversation or final response fields plus judge model config |

When unsure, read the SDK metric class and its tests before creating a large
run.

## Dataset And Template Checks

- Templates read dataset columns through `item`, for example
  `{{item.expected}}`.
- Online evaluations can read generated output through `sample.output_text`.
- Offline evaluations need response/output fields already present in each row.
- Keep field names identical between dataset rows and templates.
- Include at least one expected pass and one expected fail in smoke data.
- If a row fails to render a template, fix the dataset shape before changing
  the metric.

## Bring Your Own Benchmark

For external, custom, or bring-your-own benchmarks, keep the protocol explicit
and reproducible.

- Separate judge-quality evaluation from generation-quality evaluation. If the
  target is report generation, generate fresh model responses, score them with
  a fixed judge, and aggregate fulfilment. Do not treat human labels for
  existing baseline responses as labels for new model outputs.
- Use provider-agnostic configuration. Require users or harness config to
  provide generator and judge base URLs, model IDs, and secret references.
- Validate model IDs with a `/v1/models`-style endpoint when the provider
  supports it. Do not assume a web catalog equals runnable API model IDs.
- Run a tiny smoke prompt before the full benchmark to confirm authentication,
  response shape, parser behavior, and unsupported generation parameters.
- Record artifacts that make the run replayable: `README.md`, `manifest.yaml`,
  `scoring_protocol.md`, `results_report.md`, `generations.jsonl`,
  `judge_predictions.jsonl`, and `scores.json`.
- Store secret variable names or secret file paths in manifests, never secret
  values.
- Report calibration deltas transparently. Do not apply hidden correction
  factors; inspect endpoint/model ID, generation params, sampling plan, judge
  prompt, reasoning policy, parser, and aggregation if deltas are large.

## Long-Running Benchmark Reproduction

Use this pattern when a BYOB run is too large for a single in-memory SDK
example.

1. Freeze the dataset, rubric, sample plan, generator parameters, judge
   parameters, and aggregation weights before starting the full run.
2. Smoke-test one or two rows end to end: generate, judge, parse, aggregate,
   and write artifacts.
3. Use one run directory per generator model or model configuration. Do not mix
   outputs from different generator settings in the same checkpoint files.
4. Checkpoint generation and judging separately so either stage can resume.
   Prefer append-only JSONL with stable row IDs, criterion IDs, status, parsed
   values, and error fields.
5. Retry failed rows individually with bounded attempts. Fail closed on missing
   rows, missing criteria, or unparsable judge outputs; do not silently drop
   them from denominators.
6. Write final task, domain, and overall scores only after every required
   criterion row is present and parseable, or after failures are explicitly
   counted according to the scoring protocol.
7. Report progress periodically by stage: generated rows, judged criterion
   rows, parse failures, retry queue, rate-limit sleeps, and estimated
   remaining work.

ProfBench-style rubric-to-leaderboard shape:

```text
dataset rows
-> generated responses per model
-> criterion-level judge rows per response
-> fixed binary judge with parser-compatible yes/no output
-> weighted criterion fulfilment
-> task, domain, and overall scores
```

Keep the fixed judge, rubric text, parser, and weights constant when comparing
generator models. If the judge itself is being evaluated, run a separate
judge-quality experiment against labeled existing responses.

## Failure Modes

- Empty completions: record the raw provider response, prompt, params, token
  usage, and finish reason; retry only if the provider response indicates a
  transient failure.
- All-reasoning outputs: inspect completion token use and final-answer length;
  record token budget and reasoning settings separately from benchmark
  semantics.
- Unparsable judge rows: store raw judge text, parser error, row ID, criterion
  ID, and retry count; count unresolved rows as failures unless the protocol
  defines a different fail-closed policy.
- Provider timeouts and rate limits: use bounded retries with backoff, persist
  the retry queue, and keep progress artifacts valid after interruption.
- Partial JSONL recovery: recover by stable IDs, validate each line before
  reuse, rewrite a clean compacted file after recovery, and keep the corrupted
  fragment for audit.
- Failed-row retries: retry the smallest failed unit, usually one generation
  row or one criterion judge row, rather than rerunning completed work.

## Artifact Contract

For a handoff-ready benchmark reproduction, produce artifacts that another
human can inspect and rerun:

- `manifest.yaml`: dataset version, rubric version, sample plan, model aliases,
  parameter summaries, scoring protocol, and artifact paths.
- `expanded_dataset.jsonl`: immutable rows after sampling and task expansion.
- `generations.jsonl`: generator outputs with row IDs, model alias, params
  summary, status, output text, and errors.
- `criterion_rows.jsonl`: one row per generated response and rubric criterion.
- `judge_predictions.jsonl`: raw and parsed judge outputs with retry metadata.
- `failure_log.jsonl`: failures, skipped rows, parser errors, and retry
  exhaustion.
- `scores.json`: task, domain, and overall aggregates with denominators.
- `results_report.md`: concise explanation of setup, scores, caveats, and
  interpretation.

## External-Safe Outputs

For public or broadly shared skills and reports, avoid internal endpoint names,
internal model IDs, authentication details, and secret paths. Use placeholders
such as `<provider-base-url>`, `<generator-model-id>`, `<judge-model-id>`, and
`<secret-reference>`. Report parameter categories and aliases instead of
revealing private infrastructure.

## Debugging Checklist

- Wrong schema: compare the metric constructor fields against
  `values/metrics.py`.
- Missing field: compare dataset row keys with Jinja templates.
- Bad parser: make the judge return exactly the JSON or regex format the parser
  expects.
- Judge produced reasoning but no final answer: increase final-answer token
  budget or adjust reasoning params if the provider supports them.
- Secret error: for local SDK runs, ensure the environment variable resolved
  from `api_key_secret` exists; for remote platform jobs, create the platform
  secret in the job workspace.
- Unsupported provider parameter: remove optional params first, then add them
  back one at a time.
- Tool-calling mismatch: check case sensitivity, function name normalization,
  argument JSON validity, and response shape.
- SDK mismatch: verify the request/config payload uses current SDK metric
  fields.

## Completion Criteria

A good evaluator answer includes:

- The evaluation goal and chosen SDK metric class or benchmark shape.
- The dataset shape and any templates or parser paths.
- The exact SDK snippet or evaluation spec used.
- Row-level and aggregate evidence for local runs, or job status/result
  evidence for remote runs.
- Any caveats about reproducibility, provider config, or calibration.