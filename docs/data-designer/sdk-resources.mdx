<a id="data-designer-nmp-sdk-resources"></a>

# Data Designer SDK Resources

The `data_designer.config` module provides a consistent, context-agnostic experience for building Data Designer configs.
Once you are ready to execute that config through NeMo Services APIs, you use objects from the `nemo_platform` SDK.
This page explains the SDK objects used for Data Designer API execution.

!!! note
    The SDK currently executes Data Designer workloads through the Data Designer API. Local SDK execution is planned, but not available yet. Use `nemo data-designer ... run` for local in-process execution today.


## DataDesignerResource

The `DataDesignerResource` is the initial SDK object for working with Data Designer through the SDK.
It provides Data Designer API preview and create operations for Data Designer configurations.

A `DataDesignerResource` is accessed directly from a `NeMoPlatform` instance:

```python
import os
from nemo_platform import NeMoPlatform


client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
data_designer = client.data_designer  # this object is a DataDesignerResource
```

The `DataDesignerResource` is primarily used to make Data Designer API preview requests (`preview`) and create jobs (`create`),
but exposes some additional useful methods:

| Method | Description |
|--------|-------------|
| `get_default_model_providers()` | Returns a list of model providers registered with the Models API and Inference Gateway API that can be used in your Data Designer config. |
| `get_job_resource(job_name: str)` | Returns a `DataDesignerJobResource` for interacting with a job (see below). |

## DataDesignerJobResource

The `DataDesignerJobResource` provides several helper methods for working with a job.
It is returned by the `DataDesignerResource.create()` method when you create a job;
you can also use `DataDesignerResource.get_job_resource()` to get an instance of this object for an existing job.

Some of the most useful methods are described below.

| Method | Description |
|--------|-------------|
| `wait_until_done()` | Polls the job service until the job reaches a terminal state. Prints job logs along the way. |
| `get_logs()` | Returns logs from the job as a list of dicts. Handles pagination automatically. |
| `download_artifacts()` | Downloads the job results as a tar archive. Returns a `DataDesignerJobResults` object (see below). |


## DataDesignerJobResults

The `DataDesignerJobResults` object simplifies loading downloaded job results into memory.

| Method | Description |
|--------|-------------|
| `load_analysis()` | Returns a `DatasetProfilerResults` object (from the library) with an analysis of the dataset. |
| `load_dataset()` | Returns the output dataset as a Pandas DataFrame. |
| `load_processor_dataset(processor_name: str)` | Returns the named processor dataset as a Pandas DataFrame. |
