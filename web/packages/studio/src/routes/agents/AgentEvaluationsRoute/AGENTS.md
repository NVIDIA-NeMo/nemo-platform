# Agent Evaluation

How Studio runs agent evaluations.

## Overview

- **Runner:** nemo-evaluator's **`agent-evaluate/jobs`** endpoint (task-based, `AgentEvalJob`),
  with an **agent** target. This is the canonical path for Studio agent evaluation, per the
  nemo-evaluator team — it is purpose-built for agent tasks with extensive artifact + trace
  collection. (A legacy row-based `evaluate/jobs` endpoint also exists — see the bottom.)
- **Sample agents:** `public/sample-agents/<agent>/` is the seed repository (agent config +
  an `eval-config.json`). Studio reads these for the "use example" flow.
- **Metrics:** Studio creates metrics **only** as `InlineMetricPayload` — a built-in metric
  serialized to JSON, reconstructed at runtime. No `CloudPickleMetricPayload` (no Python, no
  pickled code).

## Tasks, metrics, scores

Three levels, don't conflate them:

- **task** — one input case = one agent call (the "unit of work being evaluated"). The sample
  has 5 tasks (5 emails).
- **metric** — a scorer applied to a task's output; a task can carry more than one.
- **score** — a value a metric emits; one metric can emit many (a judge can rate several
  dimensions from one call).

The evaluation loop is `task × trial × metric → score`.

## Reusable eval configs (Filesets)

nemo-evaluator has no "eval config" entity, so a reusable config is stored as an
**`eval-config.json`** file in a named **Fileset**. The tasks are stored **inline** in the
config (the `agent-evaluate` spec takes inline `tasks[]`; a Task/Taskset _reference_ is planned
but not yet implemented, so large datasets are inlined for now).

`eval-config.json` shape (shared-metric layout):

```json
{
  "tasks": [
    {
      "id": "Claim Your Free iPhone Now!",
      "intent": "Classify this email as phishing or benign",
      "inputs": { "instruction": "<email body>" },
      "reference": { "label": "phishing" }
    }
  ],
  "metric": {
    /* one shared inline metric — see Payloads; NO judge_model */
  },
  "max_concurrent_tasks": 1
}
```

**One-click reuse:** the user selects a Fileset **by name**. Studio reads its
`eval-config.json`, **fans the shared `metric` onto each task**, injects the judge_model +
agent target, and submits. Everything defining the eval (tasks, metric) lives in the config;
only env/user-specific bits are injected at submit.

Injected by Studio **at submit** (never stored in the config): the agent **target**, the
metric's **judge_model** (from JudgeModelSelect + the workspace IGW base), and
**`max_concurrent_tasks`** (Studio default; the config value is a hint).

**`max_concurrent_tasks` defaults to `1` (serial).** This is a conservative default for local NAT
deployments. NAT currently maps workflow failures, including output truncation, to `422`; a single
failure aborts the job. Concurrency was ruled out as the root cause, but serial execution avoids
adding load while this upstream error classification remains. To tolerate failures instead, set
`target.params.ignore_request_failure: true` (failed trials score `NaN`). See Gotchas.

## Endpoints

| Purpose     | Method + path (`/apis/evaluator/v2/workspaces/{ws}`) |
| ----------- | ---------------------------------------------------- |
| List jobs   | `GET .../agent-evaluate/jobs`                        |
| Submit      | `POST .../agent-evaluate/jobs`                       |
| Get job     | `GET .../agent-evaluate/jobs/{name}`                 |
| Poll status | `GET .../agent-evaluate/jobs/{name}/status`          |
| Cancel      | `POST .../agent-evaluate/jobs/{name}/cancel`         |
| Logs        | `GET .../agent-evaluate/jobs/{name}/logs`            |
| Results     | `GET .../agent-eval-results/{name}`                  |

Fileset create/upload (Files service), for seeding a config into a new Fileset:

| Purpose        | Method + path                                                 |
| -------------- | ------------------------------------------------------------- |
| Create fileset | `POST /apis/files/v2/workspaces/{ws}/filesets`                |
| Upload file    | `PUT /apis/files/v2/workspaces/{ws}/filesets/{name}/-/{path}` |

Submit body is wrapped: `{"spec": { ...AgentEvalInputSpec }}`.

## Payloads

### Job spec

```json
{
  "spec": {
    "tasks": [
      /* each with metrics[] after Studio fans the shared metric on */
    ],
    "target": {
      "kind": "agent",
      "agent": {
        /* see below */
      }
    },
    "max_concurrent_tasks": 1
  }
}
```

### Target (generic agent)

```json
{
  "kind": "agent",
  "agent": {
    "format": "generic",
    "url": ".../agents/<agent>/-/generate",
    "name": "<agent>",
    "body": { "input_message": "{{ instruction }}" },
    "response_path": "$.value",
    "stream": false
  }
}
```

Use the non-streaming `/generate` endpoint. Do **not** use `/generate/full` — its per-token
SSE stream leaves only the last token in the captured output and every score collapses to 0.

**`body` renders against the task inputs directly.** A generic agent's request is a passthrough
of the task row, so `body` references task input fields by name — `{{ instruction }}` — not a
chat wrapper. `instruction` is the single canonical task input.

### Task

```json
{
  "id": "Claim Your Free iPhone Now!",
  "intent": "Classify this email as phishing or benign",
  "inputs": { "instruction": "<prompt sent to the agent>" },
  "reference": { "label": "phishing" },
  "metrics": [
    /* inline metric bundle, fanned on at submit */
  ]
}
```

`inputs.instruction` is the prompt (falls back to `intent`). `reference` is grader-only ground
truth, never shown to the agent.

### Inline metric (llm-judge)

```json
{
  "bundle_kind": "metric-bundle",
  "bundle_format_version": "v1",
  "metric_type": "llm-judge",
  "metadata": { "description": null, "labels": {} },
  "outputs": [
    {
      "name": "accuracy",
      "description": null,
      "value_json_schema": {
        "description": "Continuous numeric metric value.",
        "title": "ContinuousScore",
        "type": "number"
      }
    }
  ],
  "secrets": {},
  "payload": {
    "kind": "inline",
    "metric": {
      "type": "llm-judge",
      "model": {
        /* judge_model — injected at submit */
      },
      "prompt_template": {
        "messages": [
          {
            "role": "user",
            "content": "... Expected label: \"{{ item.reference.label }}\" ... {{ sample.output_text }} ... respond {\"accuracy\": 0|1}"
          }
        ]
      },
      "scores": [{ "name": "accuracy", "minimum": 0, "maximum": 1 }],
      "inference": {
        "max_tokens": 1024,
        "extra_body": { "nvext": { "max_thinking_tokens": 256 } }
      },
      "reasoning": { "end_token": "</think>" }
    }
  }
}
```

Notes on `llm-judge`:

- `type` is `"llm-judge"` (hyphen). Enum values are inconsistent — some metrics use
  underscores (`answer_accuracy`), llm-judge uses a hyphen.
- `prompt_template` must be the **messages-object** form. A bare string routes to the dead
  `/completions` endpoint (502). The object form routes to `/chat/completions`.
- `reasoning.end_token: "</think>"` strips a reasoning model's (e.g. Nemotron) thinking trace
  before the JSON parser runs; without it the score is `NaN`.
- Bound `inference.extra_body.nvext.max_thinking_tokens` for NIM reasoning models. The total
  `max_tokens` budget includes reasoning; without a thinking cap the judge can consume the entire
  budget before emitting its structured JSON, producing a `NaN` score.
- In `agent-evaluate` the judge prompt references `{{ item.reference.label }}` /
  `{{ item.inputs.instruction }}` and the agent output as `{{ sample.output_text }}`.

### Multiple scores / multiple metrics

A metric can emit **many scores** from one judge call — `scores` is a list. Use it when the
dimensions are genuinely distinct (e.g. `coverage`, `correctness`, `relevance`):

```json
"scores": [
  { "name": "coverage",    "minimum": 0, "maximum": 1 },
  { "name": "correctness", "minimum": 0, "maximum": 1 },
  { "name": "relevance",   "minimum": 0, "maximum": 1 }
]
```

A task can also carry **multiple metrics** — `metrics` is a list; each runs independently. The
phishing sample uses one metric with one `accuracy` score because that is what a binary
classifier measures.

## Result

`GET .../agent-eval-results/{name}` returns aggregate scores per metric-score:

```json
{
  "scores": {
    "scores": [
      {
        "name": "llm-judge.accuracy",
        "count": 5,
        "nan_count": 0,
        "mean": 0.8,
        "min": 0.0,
        "max": 1.0,
        "std_dev": 0.4,
        "score_type": "range"
      }
    ]
  }
}
```

`score_type` is `range` (numeric aggregate) or `rubric` (category distribution). The full
per-task bundle (trials, evidence, traces) lives in the fileset referenced by `bundle_ref`.

## Gotchas

- **Dataset is inline.** The `agent-evaluate` spec takes inline `tasks[]`; there is no
  dataset/fileset/taskset reference yet (planned). Large datasets must be inlined for now.
- **Agent must be deployed and running before submit** — a not-yet-ready agent connection
  fails the job.
- **Use `/generate`, not `/generate/full`** (per-token SSE zeroes the score).
- **Run tasks serially (`max_concurrent_tasks: 1`) by default.** NAT currently reports workflow
  failures such as output truncation as **422**; `422` is not retried, so one failure kills the
  whole job. Serial execution is conservative but does not fix truncation. Configure an adequate
  agent output budget, or set `target.params.ignore_request_failure: true` to accept `NaN` trials.
- **`body` uses `{{ instruction }}`, not a `messages` wrapper** — a generic agent's request is a
  task-row passthrough with no `messages` key to index.

---

## Legacy: `evaluate/jobs` (row-based, not for agent eval)

nemo-evaluator also exposes a row-based `evaluate/jobs` endpoint (`EvaluateJob`). It predates
the agent path and serves **prompt/completion-style datasets**. It _can_ take an agent target
and a `dataset` that is a **`FilesetRef`** (a CSV/JSONL file in a Fileset, no row inlining) —
attractive for large datasets — but its agent-eval functionality is limited compared to
`agent-evaluate` (no per-task structure, traces, or artifact aggregation). **Do not use it for
Studio agent evaluation.** Recorded here only so the two endpoints are not confused.

Shape (reference only):

```json
{
  "spec": {
    "dataset": "default/<fileset>#data.csv",
    "metrics": [
      /* one shared inline metric */
    ],
    "target": {
      "format": "generic",
      "url": ".../-/generate",
      "response_path": "$.value",
      "stream": false
    },
    "prompt_template": { "messages": [{ "role": "user", "content": "{{ item.<col> }}" }] },
    "params": {
      /* full RunConfigOnline: parallelism, limit_samples, ignore_request_failure, request_timeout, max_retries */
    }
  }
}
```

Results come from `GET .../eval-results/{name}` (note: `eval-results`, not `agent-eval-results`)
and include percentiles + histogram. Gotcha: an agent target requires `params` typed exactly as
`RunConfigOnline` (full shape) — a bare `{ "parallelism": N }` parses as plain `RunConfig` and
the job 500s.
