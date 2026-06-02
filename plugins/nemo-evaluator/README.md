# NeMo Evaluator Plugin

A NeMo Platform plugin that brings Evaluator SDK metric execution into the
platform.

The plugin exposes an `evaluator` service, CLI commands under `nemo evaluator`,
an SDK accessor on `NeMoPlatform.evaluator`, and an `evaluator.run/evaluator.submit` for
local plugin runs and durable platform submissions.

## What it provides

- **CLI** commands for plugin status, job schema inspection, local runs, and
  job submissions.
- **Service** routes for evaluator job management.
- **SDK accessor** at `client.evaluator` for status checks, local runs, job
  submission, status polling, result retrieval, and artifact download.
- **Evaluator job** support for inline SDK metric specs, inline rows, and
  Fileset-backed datasets.
- **Docs and skills** that are published through the plugin entry points for
  evaluator-specific reference and troubleshooting.

## Installation (developer)

Prerequisites:

- Python and `uv` are available.
- Commands run from the repo root.
- `NVIDIA_API_KEY` is exported when running online or model-backed metrics.

This plugin is a `uv` workspace member. From the repo root:

```bash
uv sync
```

For local platform testing, start the platform after syncing:

```bash
nemo services run
```

The root workspace also includes this plugin in the enabled plugin set, so the
`nemo evaluator` CLI group should be available in the synced environment.

## CLI quickstart

Check that the plugin is installed:

```bash
nemo evaluator info
```

Inspect the registered job contract:

```bash
nemo evaluator evaluate explain
```

Run a minimal exact-match metric from the bundled example spec:

```bash
nemo evaluator evaluate run \
  --spec-file plugins/nemo-evaluator/src/nemo_evaluator/docs/data/exact_match_metric.json
```

Submit the same spec as a platform durable job:

```bash
nemo evaluator evaluate submit \
  --spec-file plugins/nemo-evaluator/src/nemo_evaluator/docs/data/exact_match_metric.json
```

The submit response includes a generated job name, for example `nemo-evaluator-zlhn1ecd`. Wait for the job to complete, then list and download its results:

```bash
nemo jobs get <job-name>
nemo jobs results list <job-name>
nemo jobs results download aggregate-scores --job <job-name> --output-file aggregate-scores.json
nemo jobs results download row-scores --job <job-name> --output-file row-scores.jsonl
```

## Python SDK quickstart

Use the mounted platform SDK accessor, `client.evaluator`:

```python
from nemo_evaluator_sdk import ExactMatchMetric, RunConfig
from nemo_platform import NeMoPlatform


client = NeMoPlatform(base_url="http://localhost:8080", workspace="default")
status = client.evaluator.plugin_status()

metric = ExactMatchMetric(
    reference="{{item.expected}}",
    candidate="{{item.model_output}}",
)
dataset = [
    {"expected": "blue", "model_output": "Blue"},
    {"expected": "Jupiter", "model_output": "Saturn"},
]

local_result = client.evaluator.run(
    metric=metric,
    dataset=dataset,
    config=RunConfig(parallelism=2),
)

job = client.evaluator.submit(
    metric=metric,
    dataset=dataset,
    config=RunConfig(parallelism=2),
)
job.wait_until_done()
submitted_result = job.get_result()
artifact_dir = job.download_artifacts(path="evaluation-artifacts")
```

## Local and remote inputs

### Dataset support

- Local runs support local dataset paths, inline rows, and Fileset references.
- Jobs support inline rows and Fileset references.

### Model/Agent Auth

For online evaluation or LLM-as-judge evaluations, authentication depends on the
execution mode:

- Local `nemo evaluator evaluate run` resolves `api_key_secret` as a local
  environment variable name, such as `NVIDIA_API_KEY`.
- Remote `nemo evaluator evaluate submit` resolves `api_key_secret` as a NeMo
  Platform secret in the target workspace.

## Next steps

- [Evaluator plugin reference](src/nemo_evaluator/docs/index.md)
- [Evaluator platform docs](../../docs/evaluator/index.md)
- [Evaluator plugin skill](src/nemo_evaluator/skills/evaluator-plugin/SKILL.md)
- [Evaluator API auth](../../skills/nemo-evaluator-plugin/references/api-auth.md)
- [Evaluation troubleshooting](../../skills/nemo-evaluator-plugin/references/troubleshooting.md)
