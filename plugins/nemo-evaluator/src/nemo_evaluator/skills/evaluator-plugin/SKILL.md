---
name: evaluator-plugin
description: Use when working on evaluations of LLM output, static datasets, evaluation with llm-as-judge
metadata:
  owner: evaluator
  maturity: active
---

# Evaluator Plugin

Use this skill when the task is about Evaluator functionality on the plugin architecture. The plugin-backed CLI surface is `nemo evaluator`.

## CLI Commands

> **Prerequisite:** activate the Python virtual environment before invoking the `nemo` CLI: `source .venv/bin/activate`.

Check plugin status from the CLI:

```bash
nemo evaluator info
```


## Metric Types
### Explore available metrics
To view available metric names, run:
```bash
nemo evaluator metric-types
```

To view specific metric schema, use `metric.name` from the run above:
```bash
nemo evaluator metric-types <metric_name>
``` 

Inspect all the registered metric schemas contract. 
> Note: this represents schema for all supported metrics and may fill the context. Strongly prefer `nemo evaluator metric-types` instead.

```bash
nemo evaluator evaluate explain
```

### String-Check
Compares fields using an operation (equals, contains, etc.):
```json
{"type":"string-check","operation":"contains","left_template":"{{item.answer}}","right_template":"{{item.substring}}"}
```
Dataset rows need `answer` and `substring` fields

### LLM-Judge
Uses an LLM to score responses. See example under [assets](./assets/specs/llm_as_judge.json)


### Run evaluation using inline specs
#### Evaluate using `exact-match` metric

```bash
nemo evaluator evaluate run --spec '{"metric":{"type":"exact-match","reference":"{{item.expected}}","candidate":"{{item.model_output}}"},"dataset":[{"expected":"blue","model_output":"Blue"},{"expected":"Jupiter","model_output":"Saturn"}],"params":{"parallelism":2}}'
```

#### Evaluate using `string-check` metric

```bash
nemo evaluator evaluate run --spec '{"metric":{"type":"string-check","operation":"contains","left_template":"{{item.answer}}","right_template":"NeMo"},"dataset":[{"answer":"NeMo Platform supports evaluator plugins."}]}'
```

### Run evaluation with file spec
For non-trivial specs, prefer `--spec-file` named argument over inline shell JSON. 
Note: examples of various specs are provided in the `assets` directory.

```bash
nemo evaluator evaluate run --spec-file plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/assets/specs/exact_match_metric.json
```

### Run evaluation as durable job
Use `submit` command to create a durable evaluation job. The response of this command returns a job handler object instead of the evaluation result.

```bash
nemo evaluator evaluate submit \
  --spec-file plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/assets/specs/exact_match_metric.json \
  --workspace default \
  --profile default
```

The submit response includes the generated job's `name` field, for example `nemo-evaluator-zlhn1ecd`. Wait for the job to complete, then list and download the job results

```bash
nemo jobs get-status <job-name>
nemo jobs get <job-name>
nemo jobs results list <job-name>
nemo jobs results download aggregate-scores --job <job-name> --output-file aggregate-scores.json
nemo jobs results download row-scores --job <job-name> --output-file row-scores.jsonl
```

Use `nemo evaluator evaluate explain` as the source of truth for the current plugin job schema.

## Evaluation Specs

The current job accepts inline SDK-backed evaluation specs. At a high level, specs describe:

- `metric`: inline Evaluator SDK metric configuration or benchmark metrics
- `dataset`: inline rows to evaluate
- `params`: optional Evaluator SDK execution parameters
- `target`: optional model or agent target for online evaluation

For LLM-judge setup notes, see [LLM Judge Notes](resources/llm-judge.md).

For evaluator API key auth, see [Evaluator API Auth](resources/api-auth.md).

For local and cluster troubleshooting, see [Evaluation Troubleshooting](resources/troubleshooting.md).

Call the SDK-backed status route through the platform SDK:

```python
from nemo_platform import NeMoPlatform

client = NeMoPlatform(base_url="http://localhost:8000")
status = client.evaluator.plugin_status()
```
