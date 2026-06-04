<a id="data-designer-tutorials"></a>
# Tutorials

These tutorials demonstrate how to build Data Designer configurations and execute them through the NeMo Data Designer plugin.

!!! note
    The code snippets on this page are for conceptual demonstration purposes only.
    For runnable examples, jump ahead to the [Basics](basics.md) or [Seeding](seeding.md) tutorial.

## Configuration and Execution

Data Designer separates **configuration** (building dataset schemas) from **execution** (generating the data).

**Part 1: Build Configs (Library)**

Use `data_designer.config` to define your dataset. See the [library documentation](https://docs.nvidia.com/nemo/datadesigner/v0.6.0/getting-started/welcome) for comprehensive guides on column types, constraints, and processors.

```python
import data_designer.config as dd

config_builder = dd.DataDesignerConfigBuilder(model_configs)
config_builder.add_column(dd.SamplerColumnConfig(...))
config_builder.add_column(dd.LLMTextColumnConfig(...))
```

**Part 2: Execute (Plugin)**

Submit the configuration to NeMo Services with the CLI or call the Data Designer API from the SDK:

```bash
nemo data-designer preview submit product_reviews.py --workspace default --num-records 5
nemo data-designer create submit product_reviews.py --workspace default --num-records 30
```

SDK execution uses the Data Designer API today:

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
data_designer = client.data_designer
preview = data_designer.preview(config_builder)
job = data_designer.create(config_builder, num_records=1000)
```

## Execution-Specific Considerations

When running through the plugin, use resources that NeMo Services can resolve:

| Feature | CLI `submit` / SDK |
|---------|--------------------|
| **Inference** | Inference Gateway providers |
| **Seed data** | HuggingFace or Files API Filesets |
| **Secrets** | Secrets API secrets |
| **Artifacts** | Job artifact storage |

## Prerequisites

These tutorials use an [Inference Gateway](../../run-inference/about.md) provider for model calls, so a NeMo Services cluster must be running before you preview or create data.
Complete [Setup](../../get-started/setup.md) to ensure you have the NeMo Services running locally and an inference provider available.
These tutorials reference the default NVIDIA Build model provider, which is created as `default/nvidia-build` during setup.

## Tutorials

<div class="grid cards" markdown>

-   **[The Basics](basics.md)**

    ---

    Generate a product review dataset using samplers and LLM-generated text. Learn the fundamentals of building configurations and executing jobs.

    <small><span class="md-tag">beginner</span> <span class="md-tag">data-designer</span></small>

-   **[Seeding](seeding.md)**

    ---

    Use external datasets to ground synthetic data generation. Generate realistic patient medical notes from symptom-to-diagnosis data.

    <small><span class="md-tag">intermediate</span> <span class="md-tag">data-designer</span></small>

</div>
