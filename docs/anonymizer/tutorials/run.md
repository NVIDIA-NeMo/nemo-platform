<a id="anonymizer-tutorials-run"></a>
# Run an Anonymizer Job

This tutorial walks through the `anonymizer.run` job: defining a run spec, submitting it to the {{platform_name}} Jobs worker, and loading the parquet artifacts it produces.

For detection, rewrite, and replacement strategy details, see the [open-source library documentation](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs).

## Prerequisites

- The Anonymizer plugin installed and the `nemo anonymizer` CLI available. See the [Quick Start](../quickstart.md).
- An inference provider configured (default examples use `nvidia-build`).
- A fileset named `anonymizer-inputs` with `anonymizer-input.csv` uploaded (created in the Quick Start).

## What `run` Does

`anonymizer.run` executes the full Anonymizer pipeline on every record of an input file and writes the output as job artifacts.

There are two run commands:

| Command                       | Where it runs                                | Local paths | `model_configs` required | Artifacts                                              |
|-------------------------------|----------------------------------------------|-------------|--------------------------|--------------------------------------------------------|
| `nemo anonymizer run submit`  | {{platform_name}} Jobs worker                | Rejected    | Required                 | Stored in {{platform_name}} job artifact storage; pull with `download_artifacts()` |
| `nemo anonymizer run explain` | Local schema introspection                   | n/a         | n/a                      | Prints job key, submit endpoint, and input/spec schemas |

Job artifacts (under the `artifacts/` directory):

| File                  | Description                                                         |
|-----------------------|---------------------------------------------------------------------|
| `dataset.parquet`     | User-facing anonymized dataframe (replace/rewrite output).          |
| `trace.parquet`       | Internal trace dataframe with detection details.                    |
| `metadata.json`       | Run metadata (includes the original text column name).              |
| `failed_records.json` | Per-record failures with reasons. Only written when records failed. |

## Step 1: Build an `AnonymizerRequest`

`AnonymizerRequest` contains the execution fields shared by preview and run (`config`, `data`, `model_configs`, and `selected_models`). A run processes the full input file, so it does not include `num_records`:

```python
import os
from anonymizer.config.anonymizer_config import AnonymizerConfig
from anonymizer.config.replace_strategies import Redact
from data_designer.config import ModelConfig
from nemo_anonymizer_plugin.app.input import AnonymizerInputSpec
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest

WORKSPACE = os.environ.get("NMP_WORKSPACE", "default")
MODEL_PROVIDER = os.environ.get("NMP_ANON_PROVIDER", "nvidia-build")

config = AnonymizerConfig(
    replace=Redact(format_template="[REDACTED_{label}]"),
)

model_configs = [
    ModelConfig(alias="gliner-pii-detector", provider=MODEL_PROVIDER, model="nvidia/gliner-pii"),
    ModelConfig(alias="gpt-oss-120b", provider=MODEL_PROVIDER, model="openai/gpt-oss-120b"),
    ModelConfig(alias="nemotron-30b-thinking", provider=MODEL_PROVIDER, model="nvidia/nemotron-3-nano-30b-a3b"),
]

request = AnonymizerRequest(
    config=config,
    data=AnonymizerInputSpec(
        source=f"fileset://{WORKSPACE}/anonymizer-inputs#anonymizer-input.csv",
        text_column="biography",
        id_column="id",
    ),
    model_configs=model_configs,
)
```

## Step 2: Write the Spec to YAML

The CLI run commands read a YAML spec file. Serialize the `AnonymizerRequest` directly:

```python
import yaml
from pathlib import Path

spec_path = Path("/tmp/anonymizer-run.yaml")
spec_path.write_text(yaml.safe_dump(request.model_dump(mode="json", exclude_none=True)))
```

## Step 3: Submit the Job

Submit the spec to the {{platform_name}} Jobs worker:

```bash
nemo anonymizer run submit \
  --spec-file /tmp/anonymizer-run.yaml \
  --workspace "${NMP_WORKSPACE:-default}" \
  --base-url "${NMP_BASE_URL:-http://localhost:8080}"
```

The command prints the assigned job name. You need that name to poll status and download artifacts in Step 4.

The SDK equivalent is `sdk.anonymizer.run(request)`. It posts the request to the plugin's `/jobs/run` endpoint and returns an `AnonymizerJobResource`:

```python
import os
from nemo_platform import NeMoPlatform

sdk = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace=WORKSPACE,
)
job = sdk.anonymizer.run(request)
```

The submit path rejects local file paths in `data.source` — use a fileset reference (`<fileset>#<path>`) or `http(s)` URL. It also requires explicit `model_configs` referencing Inference Gateway providers.

## Step 4: Get Results

### Submitted Job Results

For `run submit`, track the platform job first. The job is ready for artifact download when its status is `completed`:

```bash
# Replace with the job name printed by `run submit`.
nemo jobs get-status <job-name> --workspace "${NMP_WORKSPACE:-default}"
nemo jobs get-logs <job-name> --workspace "${NMP_WORKSPACE:-default}"
```

To download from the CLI, fetch the `artifacts` result and extract it:

```bash
nemo jobs results download artifacts \
  --job <job-name> \
  --workspace "${NMP_WORKSPACE:-default}" \
  --output-file /tmp/anonymizer-artifacts.tar.gz

mkdir -p /tmp/anonymizer-artifacts
tar -xzf /tmp/anonymizer-artifacts.tar.gz -C /tmp/anonymizer-artifacts
ls /tmp/anonymizer-artifacts/artifacts
```

Then point `AnonymizerJobResults` at the extracted `artifacts` directory:

```python
from pathlib import Path

from nemo_anonymizer_plugin.sdk.job_results import AnonymizerJobResults

results = AnonymizerJobResults(Path("/tmp/anonymizer-artifacts/artifacts"))

dataset = results.load_dataset()
trace   = results.load_trace()
failed  = results.load_failed_records()
```

If you used the SDK, use the `AnonymizerJobResource` methods directly. `get_job_status()` reads the current status, `check_if_complete()` tests whether artifacts are ready, `wait_until_done()` blocks until a terminal state, and `download_artifacts()` downloads and extracts the result:

```python
job = sdk.anonymizer.run(request)

status = job.get_job_status()
is_done = job.check_if_complete()

job.wait_until_done()
results = job.download_artifacts()

dataset = results.load_dataset()
trace   = results.load_trace()
failed  = results.load_failed_records()
```

`AnonymizerJobResults` exposes `load_dataset()`, `load_trace()`, `load_failed_records()`, and `display_record()` over the same underlying files. See [SDK Resources](../sdk-resources.md#anonymizerjobresults).

## Inspect the Schema Without Running

`run explain` prints the job key, submit endpoint, and JSON schemas for `AnonymizerRequest` and the canonical `AnonymizerStepConfig`:

```bash
nemo anonymizer run explain
```

This is useful when authoring a spec programmatically or wiring the job into another tool.


## How the Job Compiles

For each request, the plugin:

1. Validates the Anonymizer library `AnonymizerConfig`.
2. Validates the input source (rejects local paths; checks fileset refs).
3. Validates that `selected_models` overrides also have `model_configs`.
4. Resolves `model_configs` providers through the Inference Gateway.
5. Renders a unified `model_configs` YAML body for the library.
6. Stores the resolved providers and YAML in the internal `AnonymizerStepConfig` consumed by the Jobs worker.

For `run submit`, provider endpoints are re-resolved at runtime so the job uses the in-cluster Inference Gateway address rather than the address captured at submission time.

## Next Steps

- Iterate faster with [preview](preview.md) before scaling to a full job.
- Refer to [SDK Resources](../sdk-resources.md) for `AnonymizerJobResource` and `AnonymizerJobResults` details.
- Replacement strategy parameters and rewrite mode are documented in the [library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs).
