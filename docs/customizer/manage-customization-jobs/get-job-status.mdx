# Get Job Status

<a id="ft-get-customization-job-status"></a>
Get detailed execution status for a customization job, including step-by-step progress and real-time training metrics.

!!! tip
    This endpoint provides granular execution details including:

    - **Step-level status**: `model-and-dataset-download` → `customization-training-job` → `model-upload` → `model-entity-creation`
    - **Training metrics**: `step`, `epoch`, `loss`, `lr` (learning rate), `grad_norm`, `val_loss`
    - **Progress tracking**: `downloaded_files`, `uploaded_bytes`, `progress_pct`

    To list jobs or get job definitions (model entity, hyperparameters, spec), use [List Active Jobs](list-active-jobs.md) instead.

## Prerequisites

Before you can get the status of a customization job, make sure that you have:

- Obtained the base URL of your {{platform_name}}.
- Set the `NMP_BASE_URL` environment variable to your {{platform_name}} endpoint

```bash
export NMP_BASE_URL="https://your-nmp-base-url"
```

---

## To Get the Status of a Customization Job

Use the SDK to get detailed job status:

```python
import os
from nemo_platform import NeMoPlatform

# Initialize the client
client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Get job status
job_name = "my-sft-job"
status = client.customization.jobs.get_status(name=job_name, workspace="default")

print(f"Job: {status.name}")
print(f"Status: {status.status}")

# Check step-level status and training progress
for step in status.steps or []:
    print(f"  Step '{step.name}': {step.status}")
    if step.name == "customization-training-job":
        for task in step.tasks or []:
            task_details = task.status_details or {}
            current_step = task_details.get("step")
            max_steps = task_details.get("max_steps")
            if current_step and max_steps:
                print(f"    Progress: {current_step}/{max_steps}")
```

???+ "Example Response"

 **Active Job (Training in Progress)**

 ```json
 {
   "id": "platform-job-2k8i3i1HqJHHPVB5M6Bk9Z",
   "error_details": null,
   "name": "my-sft-job",
   "status": "active",
   "status_details": {},
   "steps": [
     {
       "id": "platform-job-step-4RJTW5wSy4gHJ539EfTUif",
       "error_details": {},
       "name": "model-and-dataset-download",
       "status": "completed",
       "status_details": {
         "message": "Job completed successfully with exit code 0"
       },
       "tasks": [
         {
           "id": "platform-job-task-MBC2vcDEyv6Jw7RtFs5JDd",
           "error_details": {},
           "error_stack": "",
           "name": "task-5969b01a4b5a4bb181ba530ff51dafa6",
           "status": "completed",
           "status_details": {
             "message": "Job completed successfully with exit code 0",
             "phase": "completed",
             "total_filesets": 2,
             "completed_filesets": 1,
             "current_fileset": "default/sft-dataset",
             "fileset": "default/sft-dataset",
             "total_files": 2,
             "total_size": 2984632,
             "downloaded_files": 2,
             "downloaded_bytes": 2984632,
             "current_file": "validation.jsonl",
             "progress_pct": 100
           }
         }
       ]
     },
     {
       "id": "platform-job-step-9kme8ibxDGES4t9TZvLp4X",
       "error_details": {},
       "name": "customization-training-job",
       "status": "active",
       "status_details": {
         "message": "Job is running"
       },
       "tasks": [
         {
           "id": "platform-job-task-SawMB6ssVZd7NCiruFVJn8",
           "error_details": {},
           "error_stack": "",
           "name": "task-2249da790a574388ba02fcabd06cd338",
           "status": "active",
           "status_details": {
             "message": "Job is running",
             "phase": "training",
             "backend": "automodel",
             "max_steps": 94,
             "num_epochs": 2,
             "step": 8,
             "epoch": 1,
             "loss": 2.8918895721435547,
             "lr": 4.9101714686276044e-05,
             "grad_norm": 26.0
           }
         }
       ]
     }
   ]
 }
 ```

 **Completed Job (All Steps Finished)**

 ```json
 {
   "id": "platform-job-2k8i3i1HqJHHPVB5M6Bk9Z",
   "error_details": null,
   "name": "my-sft-job",
   "status": "completed",
   "status_details": {},
   "steps": [
     {
       "id": "platform-job-step-4RJTW5wSy4gHJ539EfTUif",
       "error_details": {},
       "name": "model-and-dataset-download",
       "status": "completed",
       "status_details": {
         "message": "Job completed successfully with exit code 0"
       },
       "tasks": [
         {
           "id": "platform-job-task-MBC2vcDEyv6Jw7RtFs5JDd",
           "error_details": {},
           "error_stack": "",
           "name": "task-5969b01a4b5a4bb181ba530ff51dafa6",
           "status": "completed",
           "status_details": {
             "message": "Job completed successfully with exit code 0",
             "phase": "completed",
             "total_filesets": 2,
             "completed_filesets": 1,
             "current_fileset": "default/sft-dataset",
             "fileset": "default/sft-dataset",
             "total_files": 2,
             "total_size": 2984632,
             "downloaded_files": 2,
             "downloaded_bytes": 2984632,
             "current_file": "validation.jsonl",
             "progress_pct": 100
           }
         }
       ]
     },
     {
       "id": "platform-job-step-9kme8ibxDGES4t9TZvLp4X",
       "error_details": {},
       "name": "customization-training-job",
       "status": "completed",
       "status_details": {
         "message": "Job completed successfully with exit code 0"
       },
       "tasks": [
         {
           "id": "platform-job-task-SawMB6ssVZd7NCiruFVJn8",
           "error_details": {},
           "error_stack": "",
           "name": "task-2249da790a574388ba02fcabd06cd338",
           "status": "completed",
           "status_details": {
             "message": "Job completed successfully with exit code 0",
             "phase": "processing_checkpoint",
             "backend": "automodel",
             "max_steps": 94,
             "num_epochs": 2,
             "step": 94,
             "epoch": 2,
             "loss": 0.3437718152999878,
             "lr": 5.000000000000001e-07,
             "grad_norm": 20.125,
             "val_loss": 0.5527229905128479,
             "checkpoint_path": "/var/run/scratch/job/training/checkpoints"
           }
         }
       ]
     },
     {
       "id": "platform-job-step-6gkKgfT5AwyamBWNtQFA9t",
       "error_details": {},
       "name": "model-upload",
       "status": "completed",
       "status_details": {
         "message": "Job completed successfully with exit code 0"
       },
       "tasks": [
         {
           "id": "platform-job-task-J2wt8G8X3vkUHZJCEhzYTP",
           "error_details": {},
           "error_stack": "",
           "name": "task-9647899028aa44c493ce1d65a4ec8f7b",
           "status": "completed",
           "status_details": {
             "message": "Job completed successfully with exit code 0",
             "phase": "completed",
             "total_filesets": 1,
             "completed_filesets": 0,
             "current_fileset": "default/customization-b5b20520fe4f",
             "fileset": "default/customization-b5b20520fe4f",
             "total_files": 7,
             "total_size": 2488928480,
             "uploaded_files": 7,
             "uploaded_bytes": 2488928480,
             "current_file": "model-00001-of-00001.safetensors",
             "progress_pct": 100
           }
         }
       ]
     },
     {
       "id": "platform-job-step-9NmC8mrS3VtthjUSo52EiB",
       "error_details": {},
       "name": "model-entity-creation",
       "status": "completed",
       "status_details": {
         "message": "Job completed successfully with exit code 0"
       },
       "tasks": [
         {
           "id": "platform-job-task-8Mbbz6AnZP5fQLu61aVRb",
           "error_details": {},
           "error_stack": "",
           "name": "task-ab80f766085f4203b72a612f38a2c1b0",
           "status": "completed",
           "status_details": {
             "message": "Job completed successfully with exit code 0"
           }
         }
       ]
     }
   ]
 }
 ```
