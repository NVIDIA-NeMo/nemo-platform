# Evaluator Plugin Reference

The evaluator plugin is a first-party for evaluator functionality. It keeps the plugin identity separate from the legacy `/apis/evaluation` service while proving the basic surfaces needed for SDK-backed jobs.

## Registered Surfaces

| Surface | Entry point | Current behavior |
|---|---|---|
| CLI | `nemo.cli:evaluator` | Adds `nemo evaluator info` and hosts evaluator job commands. |
| Service | `nemo.services:evaluator` | `evaluate/jobs` lifecycle, `metrics` CRUD, the read-only metric-type catalog + `evaluate/schema`, the synchronous `evaluate` route, and `healthz`. |
| SDK | `nemo.sdk:evaluator` | Adds `client.evaluator.plugin_status() and run(), submit() interfaces`. |
| Job | `nemo.jobs:evaluator.evaluate` | Backs local `run` through in-process execution and `submit` through durable platform job submission. |
| Docs | `nemo.docs:evaluator` | Publishes this reference page. |
| Skills | `nemo.skills:evaluator` | Publishes the evaluator plugin development skill. |

## REST API

All routes are under `/apis/evaluator`. Several map directly to CLI commands so non-Python clients (e.g. Studio) can reach the same functionality.

| Method + path | Purpose | CLI equivalent |
|---|---|---|
| `GET /v2/metric-types` | List built-in metric types and descriptions | `nemo evaluator metric-types` |
| `GET /v2/metric-types/{metric_type}` | JSON schema for one metric type | `nemo evaluator metric-types <name>` |
| `GET /v2/evaluate/schema` | JSON schema for the **synchronous** evaluate request body | — |
| `GET /v2/evaluate/jobs/schema` | JSON schema for the evaluate **job** input spec | `nemo evaluator evaluate explain` |
| `POST /v2/workspaces/{workspace}/evaluate` | Run a bounded evaluation **synchronously** and return the result inline | `nemo evaluator evaluate run` |
| `POST /v2/workspaces/{workspace}/evaluate/jobs` (+ lifecycle) | Submit a durable evaluation job | `nemo evaluator evaluate submit` |
| `GET/POST/DELETE /v2/workspaces/{workspace}/metrics[/{name}]` | Stored-metric CRUD (create/list/get/delete; immutable) | — |

### Synchronous evaluate constraints

`POST .../evaluate` is the "test a metric" path. It runs **in the long-lived API process**, so it
is deliberately bounded to what is safe there (anything else goes to the durable `/evaluate/jobs`
API, which runs in an isolated container). It returns `422` for:

- **Non-inline metric payloads** (allow-list on `payload.kind == "inline"`) — arbitrary code
  (e.g. cloudpickle) is never executed in the API process, and future payload kinds fail closed.
- **Network (remote) metric types** (`remote`, `nemo-agent-toolkit-remote`) — they call a
  user-supplied URL (SSRF).
- **Metrics with secret references** — the in-process backend resolves secrets from the API
  process environment, so request-supplied secrets are refused (exfiltration guard).
- **Inline model definitions** — any model a metric uses (e.g. an LLM-judge's judge model) must
  be a platform **`ModelRef`** (`workspace/model`). Refs resolve to the inference gateway with no
  secret, and the in-process call carries the **caller's** request-scoped headers (principal +
  trace), so it runs as the caller — not an elevated service principal — and leaks no secret.
  Inline models carry an arbitrary URL and are rejected.
- **Online targets** — generation against a model/agent target is not supported here; submit a job.

So **LLM-judge and other model-backed metrics are supported** as long as their models are
`ModelRef`s. The dataset must be **inline rows** (no `FilesetRef`), capped at `MAX_SYNC_ROWS` (10),
and the metrics list is capped at `MAX_SYNC_METRICS` (10).

Execution runs on bounded daemon worker threads (`_SYNC_EVAL_MAX_WORKERS`, 4 concurrent slots)
under a wall-clock timeout (`SYNC_EVALUATE_TIMEOUT_SECONDS`, 60s) → `504` on expiry. When all
slots are busy the endpoint returns `503` rather than queueing. A timed-out evaluation keeps
holding its slot until its underlying calls return, but each metric's model calls are bounded to
the same 60s budget (with retries capped at 1), so worst-case slot occupancy stays near the
request timeout. For anything heavier, use the durable job API.

Authz: read routes require `evaluator:read`; the synchronous evaluate route requires the
`evaluator.evaluate.exec` permission (`evaluator:write`).

## Current Job

`evaluator.evaluate` is a `NemoJob` that calls `packages/nemo_evaluator_sdk.Evaluator` directly. It currently supports inline datasets with `exact-match` and `string-check` metric configs.


## CLI Examples

### Prerequisite for online evaluation and model-backed metrics

#### Set API key

Online evaluation examples call [NVIDIA-hosted models](https://build.nvidia.com/models) through the API key referenced by each spec's `api_key_secret`.

To generate an API key on the NVIDIA Build hub:

1. Sign in to your NVIDIA account at <https://build.nvidia.com>.
2. Open [API Keys](https://build.nvidia.com/settings/api-keys) and click **Generate API Key**.
3. Export the key before running the CLI: `export NVIDIA_API_KEY=<YOUR_KEY>`.

#### How to use API key

For evaluator API key auth, see [Evaluator API Auth](../../../../../skills/nemo-evaluator-plugin/references/api-auth.md)

### Examples

Check that the plugin is installed and reports the registered job key:

```bash
nemo evaluator info
```

Inspect the generated job metadata:

```bash
nemo evaluator evaluate explain
```

Run an inline exact-match metric:

```bash
nemo evaluator evaluate run --spec '{"metric":{"type":"exact-match","reference":"{{item.expected}}","candidate":"{{item.model_output}}"},"dataset":[{"expected":"blue","model_output":"Blue"},{"expected":"Jupiter","model_output":"Saturn"}],"params":{"parallelism":2}}'
```

Run an online llm-as-judge metric from a spec file (requires `NVIDIA_API_KEY`, see the [prerequisite](#prerequisite-for-online-evaluation-and-model-backed-metrics) above):

```bash
nemo evaluator evaluate run --spec-file plugins/nemo-evaluator/src/nemo_evaluator/docs/data/llm_as_judge.json
```

Run a benchmark metric from spec file example:

```bash
nemo evaluator evaluate run --spec-file plugins/nemo-evaluator/src/nemo_evaluator/docs/data/exact_match_benchmark.json
```

## Python Examples

Read the plugin service status through the platform SDK namespace:

```python
from nemo_platform import NeMoPlatform

client = NeMoPlatform(base_url="http://localhost:8080")
status = client.evaluator.plugin_status()
```

Use the evaluator SDK directly, matching the job's current execution path:

```python
from nemo_evaluator_sdk import Evaluator
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric

metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.model_output}}")
result = Evaluator().run_sync(
    metrics=metric,
    dataset=[{"expected": "blue", "model_output": "Blue"}],
)
```
