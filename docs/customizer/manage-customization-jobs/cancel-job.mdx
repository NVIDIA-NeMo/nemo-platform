# Cancel Job

<a id="ft-cancel-customization-job"></a>
## Prerequisites

Before you can cancel a customization job, make sure that you have:

- Obtained the base URL of your {{platform_name}}.
- Set the `NMP_BASE_URL` environment variable to your {{platform_name}} endpoint

```bash
export NMP_BASE_URL="https://your-nmp-base-url"
```

---

## To Cancel a Customization Job

Running jobs may be cancelled. A cancelled job does not upload checkpoints. You need the job's name and workspace; you can get these from [List Active Jobs](list-active-jobs.md).

Use the SDK to cancel a customization job:

```python
import os
from nemo_platform import NeMoPlatform

# Initialize the client
client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Cancel a customization job (use the job name and workspace from List Active Jobs)
job_name = "my-sft-job"
workspace = "default"
cancelled_job = client.customization.jobs.cancel(name=job_name, workspace=workspace)

print(f"Job {cancelled_job.name} has been cancelled")
print(f"Current status: {cancelled_job.status}")
print(f"Updated at: {cancelled_job.updated_at}")
```

??? "Example Response"
    :icon: code-square
    :open:

    ```json
    {
      "name": "my-sft-job",
      "workspace": "default",
      "id": "job-abc123def456",
      "status": "cancelled",
      "spec": {
        "model": "default/llama-3-2-1b",
        "dataset": "fileset://default/my-training-dataset",
        "training": {
          "type": "sft",
          "batch_size": 16,
          "epochs": 3,
          "learning_rate": 1e-05,
          "max_seq_length": 4096,
          "parallelism": {
            "num_gpus_per_node": 2,
            "tensor_parallel_size": 2
          }
        },
        "output": {
          "name": "my-finetuned-llama",
          "type": "model",
          "fileset": "my-finetuned-llama-a1b2c3d4e5f6"
        }
      },
      "created_at": "2026-02-09T10:30:00.000Z",
      "updated_at": "2026-02-09T10:35:00.000Z"
    }
    ```
