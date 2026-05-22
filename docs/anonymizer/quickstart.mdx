<a id="anonymizer-quickstart"></a>
# Quick Start

This guide walks through previewing and running an Anonymizer job on {{platform_name}}.

## Prerequisites

- Access to a {{platform_name}} deployment with the `anonymizer` plugin service enabled.
- An API key for a model provider used by the Anonymizer pipeline.

## Step 1: Install the Plugin

Follow the [Setup guide](../get-started/setup.md) to install {{platform_name}} and complete `nemo setup`. From a repo checkout, run `uv sync` at the repo root; the root workspace includes the Anonymizer plugin, so no separate editable plugin install step is needed. `nemo services run` then picks up the plugin automatically and mounts `/apis/anonymizer/...` on the gateway.

Verify the CLI is registered:

```bash
nemo anonymizer --help
```

You should see `validate`, `preview`, and `run` command groups.

## Step 2: Initialize the SDK

```python
import os
from nemo_platform import NeMoPlatform

base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
WORKSPACE = os.environ.get("NMP_WORKSPACE", "default")
sdk = NeMoPlatform(base_url=base_url, workspace=WORKSPACE)
anonymizer = sdk.anonymizer
```

## Step 3: Configure Inference

Anonymizer routes inference through the [Inference Gateway service](../run-inference/about.md). You need a model provider configured before running anything that uses `model_configs`.

`nemo setup` walks you through creating a provider secret and registering an Inference Gateway provider as part of the install flow. If you skipped that step or want to add another provider, re-run `nemo setup` — see the [Setup guide](../get-started/setup.md) for details.

--8<-- "_snippets/nvidia-build-model-provider.md"

## Step 4: Upload an Input Fileset

Create a small CSV containing PII and upload it to a fileset:

```python
import os
import tempfile
from pathlib import Path

from nemo_platform._exceptions import ConflictError

WORKSPACE = os.environ.get("NMP_WORKSPACE", "default")
FILESET = "anonymizer-inputs"
INPUT_FILENAME = "anonymizer-input.csv"

with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
    f.write(
        "id,biography\n"
        "1,Alice Johnson lives in Seattle and works at NVIDIA.\n"
        "2,Bob Smith can be reached at bob.smith@example.com.\n"
    )
    input_path = Path(f.name)

try:
    sdk.files.filesets.create(
        name=FILESET,
        workspace=WORKSPACE,
        description="Anonymizer input files",
    )
except ConflictError:
    pass  # already exists

sdk.files.upload(
    local_path=str(input_path),
    fileset=FILESET,
    workspace=WORKSPACE,
    remote_path=INPUT_FILENAME,
)
```

The plugin accepts three input source forms:

- Local path (local execution only): `/tmp/anonymizer-input.csv`
- HTTP(S) URL: `https://.../input.csv`
- Fileset reference: `anonymizer-inputs#anonymizer-input.csv`, `default/anonymizer-inputs#anonymizer-input.csv`, or `fileset://default/anonymizer-inputs#anonymizer-input.csv`

## Step 5: Preview Anonymization

Preview streams a small anonymized sample so you can iterate on the config without running a full job. Build a `PreviewRequest` and call `anonymizer.preview`:

```python
import os
from anonymizer.config.anonymizer_config import AnonymizerConfig
from anonymizer.config.replace_strategies import Redact
from data_designer.config import ModelConfig
from nemo_anonymizer_plugin.app.input import AnonymizerInputSpec
from nemo_anonymizer_plugin.app.task_config import PreviewRequest

MODEL_PROVIDER = os.environ.get("NMP_ANON_PROVIDER", "nvidia-build")

config = AnonymizerConfig(
    replace=Redact(format_template="[REDACTED_{label}]"),
)

model_configs = [
    ModelConfig(alias="gliner-pii-detector", provider=MODEL_PROVIDER, model="nvidia/gliner-pii"),
    ModelConfig(alias="gpt-oss-120b", provider=MODEL_PROVIDER, model="openai/gpt-oss-120b"),
    ModelConfig(alias="nemotron-30b-thinking", provider=MODEL_PROVIDER, model="nvidia/nemotron-3-nano-30b-a3b"),
]

request = PreviewRequest(
    config=config,
    data=AnonymizerInputSpec(
        source=f"fileset://{WORKSPACE}/{FILESET}#{INPUT_FILENAME}",
        text_column="biography",
        id_column="id",
    ),
    model_configs=model_configs,
    num_records=2,
)

preview = anonymizer.preview(request)

preview.dataset                   # pandas DataFrame of anonymized records
preview.trace_dataset             # detection trace
preview.failed_records            # list of per-record failures (usually empty)
preview.display_record(0)         # render a record with entity highlights
```

`preview.dataset` is a regular pandas DataFrame, so you can persist it with `to_csv` or `to_parquet`.

??? "Run preview from the CLI instead"
    The same flow is available from the CLI. Write the spec to YAML:

    ```python
    import yaml
    from pathlib import Path

    preview_spec_path = Path("/tmp/anonymizer-preview.yaml")
    preview_spec_path.write_text(yaml.safe_dump(request.model_dump(mode="json", exclude_none=True)))
    ```

    Then run either of:

    ```bash
    nemo anonymizer preview run \
      --spec-file /tmp/anonymizer-preview.yaml \
      --workspace "${NMP_WORKSPACE:-default}"

    nemo anonymizer preview submit \
      --spec-file /tmp/anonymizer-preview.yaml \
      --workspace "${NMP_WORKSPACE:-default}" \
      --base-url "${NMP_BASE_URL:-http://localhost:8080}"
    ```

    The CLI streams newline-delimited JSON frames (`preview_dataset`, `trace_dataset`, `failed_records`, ...) to stdout. See the [preview tutorial](tutorials/preview.md) for the frame schema and `jq` recipes.

!!! note
    `anonymizer.preview` calls the plugin service, so it rejects local file paths in `data.source` and requires `model_configs`. The fileset reference and `model_configs` in the example above satisfy both constraints.

## Step 6: Run a Full Job

When the preview looks correct, run the full pipeline. The `anonymizer.run` job can execute either locally in the CLI process (`run run`) or on the {{platform_name}} Jobs worker (`run submit` / `sdk.anonymizer.run()`).

Build an `AnonymizerRequest`:

```python
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest

run_request = AnonymizerRequest(
    config=config,
    data=AnonymizerInputSpec(
        source=f"fileset://{WORKSPACE}/{FILESET}#{INPUT_FILENAME}",
        text_column="biography",
        id_column="id",
    ),
    model_configs=model_configs,
)
```

**Option A — submit to the Jobs worker:**

```python
job = sdk.anonymizer.run(run_request, wait_until_done=True)
results = job.download_artifacts()

dataset = results.load_dataset()
print(dataset.head())
print(f"records={len(dataset)} failures={len(results.load_failed_records())}")
```

`sdk.anonymizer.run()` returns an `AnonymizerJobResource`. `wait_until_done=True` blocks until the job reaches a terminal state; `download_artifacts()` fetches the job artifacts and returns an `AnonymizerJobResults` for in-memory access. See [SDK Resources](sdk-resources.md) for the full surface.

The CLI equivalent submits the same spec. First write it to YAML:

```python
import yaml
from pathlib import Path

run_spec_path = Path("/tmp/anonymizer-run.yaml")
run_spec_path.write_text(yaml.safe_dump(run_request.model_dump(mode="json", exclude_none=True)))
```

Then submit it:

```bash
nemo anonymizer run submit \
  --spec-file /tmp/anonymizer-run.yaml \
  --workspace "${NMP_WORKSPACE:-default}" \
  --base-url "${NMP_BASE_URL:-http://localhost:8080}"
```

Track the submitted job with `nemo jobs get-status <job-name> --workspace "${NMP_WORKSPACE:-default}"` and `nemo jobs get-logs <job-name> --workspace "${NMP_WORKSPACE:-default}"`.

**Option B — run locally in the CLI process:**

```python
import yaml
from pathlib import Path

spec_path = Path("/tmp/anonymizer-run.yaml")
spec_path.write_text(yaml.safe_dump(run_request.model_dump(mode="json", exclude_none=True)))
```

```bash
nemo anonymizer run run --spec-file /tmp/anonymizer-run.yaml
```

The CLI prints `{"exit_code": 0}` on success and logs the artifact directory (`file://.../persistent/results/artifacts`) to stderr. The directory contains:

- `dataset.parquet`: anonymized output.
- `trace.parquet`: detection trace.
- `metadata.json`: run metadata.
- `failed_records.json`: per-record failures, only when there were failures.

!!! note "Differences between `run run` and `run submit`"
    `run submit` rejects local file paths in `data.source` (use a fileset reference or `http(s)` URL) and requires explicit `model_configs` referencing Inference Gateway providers. `run run` accepts local paths and can run without `model_configs` when the library defaults suffice.

## Step 7: Inspect Artifacts

For Option A (`run submit`), the `AnonymizerJobResults` returned by `download_artifacts()` already loads parquet files lazily — `results.load_dataset()`, `results.load_trace()`, and `results.load_failed_records()` return pandas DataFrames / lists.

For Option B (`run run`), load the parquet files directly from the local artifact directory:

```python
from pathlib import Path

import pandas as pd

ARTIFACTS_DIR = Path("/path/to/persistent/results/artifacts")  # from the stderr log

dataset = pd.read_parquet(ARTIFACTS_DIR / "dataset.parquet", dtype_backend="pyarrow")
trace   = pd.read_parquet(ARTIFACTS_DIR / "trace.parquet",   dtype_backend="pyarrow")

print(dataset.head())
```

The trace dataset (and the dataset itself for `annotate` / `substitute` strategies) contains pyarrow-backed `struct<entities: list<...>>` columns. Use `pyarrow.parquet.read_table(...).to_pylist()` if you need plain Python `dict`/`list` values for JSON output.

## Troubleshooting

| Problem                                            | Cause                                                       | Solution                                                                                                |
|----------------------------------------------------|-------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| `nemo anonymizer preview submit` returns 404       | The `anonymizer` plugin service isn't mounted on the gateway | Confirm `uv sync` ran successfully at the repo root and re-run `nemo services run` so the plugin is discovered. See [Step 1](#step-1-install-the-plugin). |
| `model_configs are required for remote execution`  | `anonymizer.preview` / `preview submit` requires explicit `model_configs` | Add `model_configs` referencing an Inference Gateway provider.                                |
| `Input source ... is a local path`                 | Plugin-service execution rejects local paths                 | Use an `http(s)` URL or a fileset reference.                                                            |
| `Fileset input ... must resolve to a .csv or .parquet file` | Fileset path is a directory or wrong extension      | Point the `#<path>` fragment at a single `.csv` or `.parquet` file.                                     |
| `provider not found`                               | Inference provider missing                                   | Inspect or create the provider using the inference/model-provider docs, then reference it in `model_configs`. |

## Next Steps

- **Tutorials:** Walk through preview and run flows in detail in the [tutorials](tutorials/index.md).
- **SDK reference:** See [SDK Resources](sdk-resources.md) for the `anonymizer` accessor, preview result, and job result types.
- **CLI reference:** See [CLI Reference](cli.md) for spec-file fields and command flags.
- **Library docs:** Detection, replacement strategy parameters, and rewrite mode are documented in the [open-source library](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs).
