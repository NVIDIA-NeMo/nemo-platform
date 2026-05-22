<a id="fine-tune-metrics"></a>
# Checking Your Customization Job Metrics

After completing a customization job, you can monitor its performance through training and validation metrics. You can access these metrics in three ways:

1. Using the API
2. Through MLflow (optional)
3. Using Weights & Biases (optional)

!!! note "The time to complete this tutorial is approximately 10 minutes."

## Prerequisites

--8<-- "_snippets/tutorials/prereqs.md"

--8<-- "customizer/tutorials/_snippets/customizer-prereqs.md"

### Tutorial-Specific Prerequisites

- Completed customization job with a valid ID
- (Optional) Access to NeMo with MLflow tracking enabled

## Available Metrics

Each customization job tracks two key metrics:

- **Training Loss**: Calculated during training, logged every 10 steps (default, configurable via hyperparameters)
- **Validation Loss**: Calculated during validation, logged at each validation interval

## Viewing Your Metrics

### Using the API

Get job status and training metrics using the Customization Service:

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Get job status with metrics
job_name = "my-sft-job"
status = client.customization.jobs.get_status(name=job_name, workspace="default")

print(f"Job: {status.name}")
print(f"Status: {status.status}")

# Check training step progress
for step in status.steps or []:
    if step.name == "customization-training-job":
        for task in step.tasks or []:
            details = task.status_details or {}
            print(f"Training Phase: {details.get('phase')}")
            print(f"Step: {details.get('step')}/{details.get('max_steps')}")
            print(f"Epoch: {details.get('epoch')}/{details.get('num_epochs')}")
            print(f"Training Loss: {details.get('loss')}")
            print(f"Validation Loss: {details.get('val_loss')}")
            print(f"Learning Rate: {details.get('lr')}")
            print(f"Gradient Norm: {details.get('grad_norm')}")
```

The response includes training progress and metrics including loss, learning rate, and validation loss.

### Using MLflow

If your deployment has MLflow tracking enabled:

1. Access the MLflow UI at your cluster's MLflow tracking URL
2. Locate your experiment by the output model name
3. Find the run using your customization job ID
4. View detailed metrics, including training and validation loss curves, under the "Metrics" tab

!!! note "MLflow integration is configured at the cluster level. Contact your administrator if you need access to the MLflow UI or if MLflow tracking is not enabled for your deployment."

<a id="ft-tut-metrics-wandb"></a>
### Using Weights & Biases

If your customization job was created with W&B integration enabled (see [Weights & Biases Integration](../manage-customization-jobs/create-job.md)):

1. Go to [wandb.ai](https://wandb.ai/home) and navigate to your project
2. Find the run corresponding to your customization job
3. View training and validation loss curves, learning rate schedules, and other metrics under the run's dashboard

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Create a customization job with W&B integration

```python
job = client.customization.jobs.create(
    name="my-wandb-job",
    workspace="default",
    spec={
        "model": "default/llama-3-2-1b",
        "dataset": "fileset://default/my-dataset",
        "training": {
            "type": "sft",
            "peft": {"type": "lora"},
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 1e-4,
        },
        "integrations": {
            "wandb": {
                "project": "my-finetuning-project",
                "entity": "my-team",
                "tags": ["fine-tuning", "llama"],
                "api_key_secret": "my-wandb-key",
            }
        },
    },
)

print(f"Created job: {job.name}")
print(f"Status: {job.status}")
```

The `api_key_secret` field references a stored secret containing your `WANDB_API_KEY`.
Use the secret name (e.g., `"my-wandb-key"`) to resolve it from the request workspace.
To create the secret, see [Weights & Biases Keys](../../get-started/concepts/manage-secrets.md).

Then view your results at [wandb.ai](https://wandb.ai/home) under your project.
![W&B charts example](../_images/wandb_charts_example.png)

!!! note
    The W&B integration is optional and must be configured when [creating the customization job](../manage-customization-jobs/create-job.md). When enabled, training metrics are sent to W&B using your API key. While we encrypt your API key and don't log it internally, please review W&B's terms of service before use.
