<!-- @nemo-nb: process -->
<!-- @nemo-nb: download -->
<a id="data-designer-tutorials-seeding"></a>
# Seeding with External Datasets

This tutorial demonstrates how to use external datasets as seed data for synthetic data generation in Data Designer.

For more detail about seed dataset behavior, see the [open-source library's version](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/tutorials/seeding-with-an-external-dataset) of this tutorial.

## Seed Sources by Execution Mode

Seed source support depends on where the workload executes:

| Seed source | CLI `run` | CLI `submit` / SDK today | Use case |
|-------------|-----------|--------------------------|----------|
| **Local files or DataFrames** | Supported | Not supported | Fast local iteration with files available to the CLI process. |
| **HuggingFace** | Supported | Supported | Publicly available datasets or private HuggingFace datasets. |
| **Files API Filesets** | Supported when NeMo Services access is configured | Supported | Shared seed data stored through the Files API. |

!!! note
    `run` versus `submit` controls where the workload executes. A local `run` can still read Files API Filesets if the configuration references them and NeMo Services access is configured.

### HuggingFace Datasets

Use `HuggingFaceSeedSource` to load data from HuggingFace:

```python
import data_designer.config as dd

# Public dataset
dd.HuggingFaceSeedSource(path="datasets/username/dataset/data/*.parquet")

# Private dataset (requires token)
dd.HuggingFaceSeedSource(
    path="datasets/username/dataset/data/*.parquet",
    token="default/hf-token",  # Reference to a Secrets API secret
)
```

### Files API Filesets

Use `FilesetFileSeedSource` to load data through the Files API. This works in CLI `run`, CLI `submit`, and SDK execution when NeMo Services access is configured:

```python
from data_designer_nemo.fileset_file_seed_source import FilesetFileSeedSource

FilesetFileSeedSource(
    path="default/my-fileset#data.parquet"  # Format: workspace/fileset#file-path
)
```

**Path format:**
- Fully qualified: `workspace/fileset-name#file-path` (recommended)
- Implicit workspace: `fileset-name#file-path` (uses client's workspace)

## Prerequisites

Ensure you have completed the [tutorials prerequisites](index.md#prerequisites). This tutorial uses an Inference Gateway provider, so local CLI `run` and NeMo Services execution both need access to the Inference Gateway API in a running NeMo Services cluster.

## Example: Medical Notes from Symptom Data

This example generates realistic patient medical notes by seeding with publicly available symptom-to-diagnosis data. It uploads the seed data to a Files API Fileset so the same configuration can run locally through CLI `run` or through NeMo Services execution.

### Step 1: Upload Seed Data

Upload the symptom-to-diagnosis dataset to a Files API Fileset:

```python
import os
import tempfile
import urllib.request
from nemo_platform import NeMoPlatform

WORKSPACE = "default"
FILESET_NAME = "seed-data"
FILE_PATH = "symptom_to_diagnosis.csv"

base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
client = NeMoPlatform(base_url=base_url, workspace=WORKSPACE)

# Create fileset
client.files.filesets.create(name=FILESET_NAME)

# Download and upload seed data
with tempfile.NamedTemporaryFile(suffix=".csv") as tmpfile:
    url = "https://raw.githubusercontent.com/NVIDIA/GenerativeAIExamples/refs/heads/main/nemo/NeMo-Data-Designer/data/gretelai_symptom_to_diagnosis.csv"
    urllib.request.urlretrieve(url, tmpfile.name)

    client.files.upload(
        fileset=FILESET_NAME,
        local_path=tmpfile.name,
        remote_path=FILE_PATH,
    )
```

### Step 2: Build Configuration

Define your models and create a config builder:

```python
import data_designer.config as dd

MODEL_ALIAS = "text"

model_configs = [
    dd.ModelConfig(
        provider="default/nvidia-build",
        model="nvidia/nemotron-3-nano-30b-a3b",  # Use the `served_model_name` from the provider
        alias=MODEL_ALIAS,
        inference_parameters=dd.ChatCompletionInferenceParams(
            temperature=1.0,
            top_p=1.0,
        ),
    )
]

config_builder = dd.DataDesignerConfigBuilder(model_configs)
```

### Step 3: Configure Seed Dataset

Add the seed data to your configuration:

```python
from data_designer_nemo.fileset_file_seed_source import FilesetFileSeedSource

config_builder.with_seed_dataset(
    FilesetFileSeedSource(path=f"{WORKSPACE}/{FILESET_NAME}#{FILE_PATH}")
)
```

**What this does:** The seed dataset's columns (`diagnosis`, `patient_summary`, etc.) are automatically added to your dataset and available for use in other columns.

### Step 4: Add Synthetic Columns

Add columns that reference and extend the seed data:

{% raw %}
```python
# Patient details
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="patient_sampler",
        sampler_type=dd.SamplerType.PERSON_FROM_FAKER,
        params=dd.PersonFromFakerSamplerParams(),
    )
)

# Doctor details
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="doctor_sampler",
        sampler_type=dd.SamplerType.PERSON_FROM_FAKER,
        params=dd.PersonFromFakerSamplerParams(),
    )
)

# Patient ID
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="patient_id",
        sampler_type=dd.SamplerType.UUID,
        params=dd.UUIDSamplerParams(
            prefix="PT-",
            short_form=True,
            uppercase=True,
        ),
    )
)

# Extract patient name from sampler
config_builder.add_column(
    dd.ExpressionColumnConfig(
        name="first_name",
        expr="{{ patient_sampler.first_name }}",
    )
)

config_builder.add_column(
    dd.ExpressionColumnConfig(
        name="last_name",
        expr="{{ patient_sampler.last_name }}",
    )
)

config_builder.add_column(
    dd.ExpressionColumnConfig(
        name="dob",
        expr="{{ patient_sampler.birth_date }}",
    )
)

# Symptom onset date
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="symptom_onset_date",
        sampler_type=dd.SamplerType.DATETIME,
        params=dd.DatetimeSamplerParams(start="2024-01-01", end="2024-12-31"),
    )
)

# Visit date (1-30 days after symptom onset)
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="date_of_visit",
        sampler_type=dd.SamplerType.TIMEDELTA,
        params=dd.TimeDeltaSamplerParams(
            dt_min=1,
            dt_max=30,
            reference_column_name="symptom_onset_date",
        ),
    )
)

# Physician name
config_builder.add_column(
    dd.ExpressionColumnConfig(
        name="physician",
        expr="Dr. {{ doctor_sampler.last_name }}",
    )
)

# LLM-generated physician notes
config_builder.add_column(
    dd.LLMTextColumnConfig(
        name="physician_notes",
        prompt="""\
You are a primary-care physician who just had an appointment with {{ first_name }} {{ last_name }},
who has been struggling with symptoms from {{ diagnosis }} since {{ symptom_onset_date }}.
The date of today's visit is {{ date_of_visit }}.

{{ patient_summary }}

Write careful notes about your visit with {{ first_name }},
as Dr. {{ doctor_sampler.first_name }} {{ doctor_sampler.last_name }}.

Format the notes as a busy doctor might.
Respond with only the notes, no other text.
""",
        model_alias=MODEL_ALIAS,
    )
)
```
{% endraw %}

**Note:** The `diagnosis` and `patient_summary` variables come from the seed dataset columns.

### Step 5: Execute

Because this example uses a Files API Fileset and an Inference Gateway provider, even local CLI execution communicates with NeMo Services APIs.

For CLI execution, save the configuration in `medical_notes.py` and expose a `load_config_builder()` function that returns the `config_builder`.

```python
def load_config_builder() -> dd.DataDesignerConfigBuilder:
    return config_builder
```

Preview locally:

```bash
nemo data-designer preview run medical_notes.py --num-records 5
```

Generate a larger dataset locally:

```bash
nemo data-designer create run medical_notes.py --num-records 30
```

Submit to NeMo Services:

```bash
nemo data-designer preview submit medical_notes.py --workspace default --num-records 5
nemo data-designer create submit medical_notes.py --workspace default --profile default --num-records 30
```

You can also execute through the SDK service path.

Create a client:

```python
# Using the client instance from Step 1
data_designer = client.data_designer
```

### Previewing the Dataset

Use the `preview` method for rapid iteration:

```python
preview = data_designer.preview(config_builder)

# Display a random sample record
preview.display_sample_record()

# Access the full preview dataset as a pandas DataFrame
df = preview.dataset
print(df.head())

# View statistical analysis
preview.analysis.to_report()
```

--8<-- "data-designer/_snippets/preview-results.md"

### Generating the Full Dataset

When you're satisfied with the preview, submit a larger generation job:

```python
# Defaulting to 30 for demo speed purposes. Happy with the output? Scale it up!
job = data_designer.create(config_builder, num_records=30)

# Block until the job completes
job.wait_until_done()

# Download the generated artifacts
results = job.download_artifacts()

# Load the dataset as a pandas DataFrame
dataset = results.load_dataset()
print(dataset.head())

# Load the full analysis report
analysis = results.load_analysis()
analysis.to_report()
```

--8<-- "data-designer/_snippets/job-results.md"

## How Seeding Works

When you configure a seed dataset:

1. **Automatic Column Addition:** All columns from the seed data are automatically added to your dataset schema
2. **Dependency Resolution:** Data Designer resolves dependencies between seed columns and synthetic columns
3. **Execution Order:** Seed data is loaded first, then synthetic columns are generated row-by-row
4. **Row Alignment:** Each generated row corresponds to one row from the seed dataset

**Example:** If your seed data has 100 rows with columns `diagnosis` and `patient_summary`, and you request 100 records, each generated record will include the seed columns plus any synthetic columns you defined.

## Next Steps

- **Execution modes:** Learn more about local and NeMo Services execution in [Execution Modes](../execution-modes.md)
- **Column types:** Explore all available column types in the [library documentation](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/concepts/columns)
- **Processors:** Transform your data with processors in the [library documentation](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/concepts/processors)
