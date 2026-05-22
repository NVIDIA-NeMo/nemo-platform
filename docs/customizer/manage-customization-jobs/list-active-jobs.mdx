# List Active Jobs

<a id="ft-list-active-customization-jobs"></a>
List all customization jobs and their high-level status. This returns job definitions including the model, dataset, training configuration, and overall status.

!!! tip
    To get **detailed execution progress** (step-by-step status, training metrics like loss/epoch/step), use [Get Job Status](get-job-status.md) instead.

## Prerequisites

Before you can list active customization jobs, make sure that you have:

- Obtained the base URL of your {{platform_name}}.
- Set the `NMP_BASE_URL` environment variable to your {{platform_name}} endpoint

```bash
export NMP_BASE_URL="https://your-nmp-base-url"
```

---

## To List Active Customization Jobs

Use the SDK to list customization jobs:

```python
import os
from nemo_platform import NeMoPlatform

# Initialize the client
client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# List all customization jobs
jobs = client.customization.jobs.list(
    workspace="default", page=1, page_size=10, sort="created_at"
)

print(f"Found {len(jobs.data)} jobs")
for job in jobs.data:
    print(f"Job {job.name}: {job.status}")

# List jobs with filters (optional)
# Valid filter fields: name, status, project, workspace, created_at, updated_at
filtered_jobs = client.customization.jobs.list(
    workspace="default",
    filter={
        "status": "active",  # Filter by job status
        "name": "my-sft-job",  # Filter by job name
    },
    sort="-created_at",  # Sort by created_at descending
)

print(f"Found {len(filtered_jobs.data)} jobs")
for job in filtered_jobs.data:
    print(f"Job {job.name}: {job.status}")
```

??? "Example Response"
    :icon: code-square
    :open:

    ```json
    {
      "data": [
        {
          "id": "platform-job-QtyhRY5ub4t4tTLPY4sTkz",
          "name": "my-sft-job-99da",
          "workspace": "default",
          "created_at": "2026-02-09T22:12:45",
          "updated_at": "2026-02-09T22:12:45",
          "status": "active",
          "status_details": {
            "message": "Job is running"
          },
          "spec": {
            "model": "default/llama-3-2-1b",
            "dataset": "fileset://default/sft-dataset",
            "training": {
              "type": "sft",
              "batch_size": 64,
              "epochs": 2,
              "learning_rate": 5e-05,
              "weight_decay": 0.01,
              "max_seq_length": 2048,
              "parallelism": {
                "num_gpus_per_node": 1,
                "num_nodes": 1,
                "tensor_parallel_size": 1,
                "pipeline_parallel_size": 1,
                "context_parallel_size": 1
              }
            },
            "output": {
              "name": "customization-407790d32cfb",
              "type": "model",
              "fileset": "customization-407790d32cfb"
            },
            "custom_fields": {}
          }
        }
      ],
      "pagination": {
        "page": 1,
        "page_size": 10,
        "current_page_size": 1,
        "total_pages": 1,
        "total_results": 1
      },
      "sort": "created_at",
      "filter": {},
      "search": {}
    }
    ```
