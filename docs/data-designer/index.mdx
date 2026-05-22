<a id="data-designer"></a>
# Data Designer

Data Designer on {{platform_name}} enables high-quality synthetic data generation through the NeMo Data Designer plugin. You can execute workloads locally from the CLI, submit them to a running NeMo Services cluster, or call the Data Designer API from the SDK.

## Overview

Data Designer is a framework for orchestrating complex synthetic data generation workflows. It coordinates LLM calls, manages dependencies between data fields, handles batching and parallelization, and validates generated data against specifications.

The plugin is built on the open-source [NVIDIA NeMo Data Designer library](https://nvidia-nemo.github.io/DataDesigner/0.5.7/) ([GitHub](https://github.com/NVIDIA-NeMo/DataDesigner)). The library provides the configuration and generation engine; the plugin provides CLI, SDK, Data Designer API, Jobs, Files API, Secrets API, and Inference Gateway API integration.

## How It Works

Data Designer separates **configuration** from **execution**.

!!! note
    The code snippets below are for conceptual demonstration purposes only.
    For runnable examples, see the [tutorials](tutorials/index.md).

### 1. Build Configurations

Use `data_designer.config` to define the dataset you want to generate:

```python
import data_designer.config as dd

# Define models
model_configs = [
    dd.ModelConfig(
        provider="default/nvidia-build",
        model="nvidia/nemotron-3-nano-30b-a3b",
        alias="text",
    )
]

# Build configuration
config_builder = dd.DataDesignerConfigBuilder(model_configs)
config_builder.add_column(dd.SamplerColumnConfig(...))
config_builder.add_column(dd.LLMTextColumnConfig(...))
```

Configuration code describes the dataset schema, columns, dependencies, constraints, seed data, processors, profilers, and inference settings.

**Learn more**: See the [library documentation](https://nvidia-nemo.github.io/DataDesigner/0.5.7/) for comprehensive guides on column types, samplers, constraints, and advanced features.

### 2. Choose Where to Execute

The same configuration can run through different plugin surfaces:

| Interface | Execution location | NeMo Services required? | Best for |
|-----------|--------------------|-------------------------|----------|
| `nemo data-designer ... run` | Local CLI process | Optional | Fast local iteration, local files, library-equivalent workload behavior. |
| `nemo data-designer ... submit` | Data Designer API or Jobs worker | Yes | Service-managed execution, logs, artifacts, and shared resources. |
| `client.data_designer.preview/create` | Data Designer API or Jobs worker | Yes | Application code that calls Data Designer programmatically. |

`run` versus `submit` primarily controls where the plugin workload execution happens. A local `run` can be fully local, but it is not an offline-only mode: it can still use the Files API, Secrets API, and Inference Gateway API from a running NeMo Services cluster when the configuration references the corresponding resources.

See [Execution Modes](execution-modes.md) for the full model.

## NeMo Services Integration

When you use CLI `submit`, SDK execution, or NeMo resources from a local `run`, the plugin integrates with these NeMo Services APIs:

| Integration | What it provides |
|-------------|------------------|
| **Inference Gateway API** | Centralized model providers and OpenAI-compatible inference routes. |
| **Files API** | Filesets for seed data and persona datasets. |
| **Secrets API** | API keys and tokens referenced from Data Designer configurations. |
| **Jobs API** | Service-managed create workloads, logs, status, and artifacts. |

These integrations are required for `submit` and SDK execution. They are optional for CLI `run` execution, depending on the resources your configuration references.

## Next Steps

<div class="grid cards" markdown>

-   **[Execution Modes](execution-modes.md)**

    ---

    Understand local execution, NeMo Services execution, and NeMo resources.

-   **[CLI](cli.md)**

    ---

    Run previews and create datasets with `nemo data-designer`.

-   **[Tutorials](tutorials/index.md)**

    ---

    Learn through examples: basics, seeding, and more.

-   **[Migration Guide](migration.md)**

    ---

    Move configurations between local CLI and NeMo Services execution.

-   **[Library Documentation](https://nvidia-nemo.github.io/DataDesigner/0.5.7/)**

    ---

    Comprehensive guides on column types, constraints, and advanced features.

</div>
