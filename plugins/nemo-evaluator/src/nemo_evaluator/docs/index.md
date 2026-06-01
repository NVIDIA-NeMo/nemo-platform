# Evaluator Plugin Reference

The evaluator plugin is a first-party for evaluator functionality. It keeps the plugin identity separate from the legacy `/apis/evaluation` service while proving the basic surfaces needed for SDK-backed jobs.

## Registered Surfaces

| Surface | Entry point | Current behavior |
|---|---|---|
| CLI | `nemo.cli:evaluator` | Adds `nemo evaluator info` and hosts evaluator job commands. |
| Service | `nemo.services:evaluator` | `jobs`, `healthz` paths. |
| SDK | `nemo.sdk:evaluator` | Adds `client.evaluator.plugin_status() and run(), submit() interfaces`. |
| Job | `nemo.jobs:evaluator.evaluate` | Backs local `run` through in-process execution and `submit` through durable platform job submission. |
| Docs | `nemo.docs:evaluator` | Publishes this reference page. |
| Skills | `nemo.skills:evaluator` | Publishes the evaluator plugin development skill. |

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
