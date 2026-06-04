<a id="data-designer-cli"></a>
# Data Designer CLI

The NeMo Data Designer plugin adds the `nemo data-designer` command group. Use it to execute Data Designer workloads locally in the CLI process or submit them to NeMo Services.

## Configuration Sources

The `preview` and `create` commands accept a configuration source path. The most flexible form is a Python file that defines `load_config_builder()` and returns a configured `DataDesignerConfigBuilder` instance. This file can have any name; the examples below use `product_reviews.py`.

```python
import data_designer.config as dd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    model_configs = [
        dd.ModelConfig(
            provider="default/nvidia-build",
            model="nvidia/nemotron-3-nano-30b-a3b",
            alias="text",
        )
    ]

    config_builder = dd.DataDesignerConfigBuilder(model_configs)
    # Add columns, constraints, seed datasets, processors, and profilers here.
    return config_builder
```

The same configuration source can usually be used with `run` or `submit`. Resource choices determine whether it is compatible with NeMo Services execution; see [Execution Modes](execution-modes.md).

## Run Versus Submit

`run` executes the Data Designer workload locally, in the CLI process. This can be fully local, but it is not an offline-only mode. A local run can still use the Files API, Secrets API, and Inference Gateway API from a running NeMo Services cluster when the configuration references the corresponding resources.

`submit` sends the workload to NeMo Services. The Data Designer API and Jobs API coordinate execution, job lifecycle, logs, and artifact persistence. The NeMo Services deployment may itself be local or remote.

| Command | Workload execution | NeMo Services required? |
|---------|--------------------|-------------------------|
| `preview run` | Local CLI process | Optional |
| `create run` | Local CLI process | Optional |
| `preview submit` | Data Designer API | Yes |
| `create submit` | Jobs worker | Yes |

## Preview Locally

Use local preview for fast iteration:

```bash
nemo data-designer preview run product_reviews.py --num-records 5
```

The workload runs in your current Python environment. It can use local-only resources, NeMo resources, or both.

## Create Locally

Use local create when you want to generate a larger dataset without submitting work to NeMo Services:

```bash
nemo data-designer create run product_reviews.py --num-records 1000
```

This executes the plugin job locally. It is useful for development and for workloads that should stay in the local environment.

## Submit Preview to NeMo Services

Submit preview when you want to exercise the Data Designer API path:

```bash
nemo data-designer preview submit product_reviews.py --workspace default
```

Use this when your configuration should run against NeMo resources and service-side validation.

## Submit Create to NeMo Services

Submit create for service-managed dataset generation:

```bash
nemo data-designer create submit product_reviews.py --workspace default --profile default
```

NeMo Services creates and runs a job. Job logs, status, and artifacts are managed by the Jobs API.

## Personas

The plugin also provides commands for Nemotron Personas datasets.

Install personas locally for local execution:

```bash
nemo data-designer personas download --list
nemo data-designer personas download --locale en_US
```

Create a Files API Fileset for a persona locale so submit and SDK execution can read it:

```bash
nemo data-designer personas make-fileset \
  --locale en_US \
  --api-key-secret system/ngc-api-key
```

If you need to create the secret during the same command, set an environment variable with the NGC API key and pass `--api-key-env-var`:

```bash
nemo data-designer personas make-fileset \
  --locale en_US \
  --api-key-secret system/ngc-api-key \
  --api-key-env-var NGC_API_KEY
```

## SDK Relationship

The SDK currently executes through the Data Designer API. If you need local in-process execution today, use `nemo data-designer ... run`.
