# Create Job

<a id="ft-create-customization-job"></a>
## Prerequisites

Before you can create a customization job, make sure that you have:

- Obtained the base URL of your {{platform_name}}.
- Created a [FileSet and Model Entity](../manage-model-entities/index.md) for your base model.
- [Uploaded a dataset](../../get-started/concepts/manage-files.md) as a FileSet.
- Determined the [training configuration](hyperparameters.md) you want to use for the customization job.
- Verified that the platform has sufficient storage for the job. Full SFT jobs require approximately 3× the base model size in free disk space; LoRA jobs require approximately 1.5×. See [ft-tut-understand-models](../tutorials/understand-configurations-and-models.md) for details. If you are also deploying the model from a base checkpoint fileset, plan for ~2.5× model size overall for LoRA.
- Set the `NMP_BASE_URL` environment variable to your {{platform_name}} endpoint.

```bash
export NMP_BASE_URL="https://your-nemo-platform-url"
```

---

## To Create a Customization Job

Use the SDK to create a customization job:

```python
import os
from nemo_platform import NeMoPlatform

# Initialize the client
client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Create a customization job
job = client.customization.jobs.create(
    name="my-lora-job",
    workspace="default",
    spec={
        "model": "default/llama-3-2-1b",  # Model Entity (workspace/name format)
        "dataset": "fileset://default/my-training-dataset",
        "training": {
            "type": "sft",
            "peft": {"type": "lora", "rank": 8, "alpha": 32, "dropout": 0.0},
            "batch_size": 32,
            "epochs": 3,
            "learning_rate": 1e-4,
            "max_seq_length": 2048,
        },
        "output": {
            "name": "my-custom-model"
        },  # Optional: auto-generated if not provided
        "deployment_config": {
            "lora_enabled": True  # Optional: deploy base model with LoRA support
        },
    },
)

print(f"Created job: {job.name}")
print(f"Job status: {job.status}")
```

??? "Example Response"
    :icon: code-square
    :open:

    ```json
    {
      "name": "my-lora-job",
      "workspace": "default",
      "id": "job-abc123def456",
      "status": "created",
      "spec": {
        "model": "default/llama-3-2-1b",
        "dataset": "fileset://default/my-training-dataset",
        "training": {
          "type": "sft",
          "peft": {
            "type": "lora",
            "rank": 8,
            "alpha": 32,
            "dropout": 0.0
          },
          "batch_size": 32,
          "epochs": 3,
          "learning_rate": 0.0001,
          "max_seq_length": 2048
        },
        "output": {
          "name": "my-custom-model",
          "type": "adapter",
          "fileset": "my-custom-model-a1b2c3d4e5f6"
        }
      },
      "created_at": "2026-02-09T10:30:00.000Z",
      "updated_at": "2026-02-09T10:30:00.000Z"
    }
    ```

---

### Knowledge Distillation Example

For knowledge distillation, specify `type: "distillation"` with a `teacher_model` that references a second Model Entity. The `model` field is the student model that is being trained.

```python
job = client.customization.jobs.create(
    name="my-kd-job",
    workspace="default",
    spec={
        "model": "default/llama-3-2-1b-instruct",  # Student model
        "dataset": "fileset://default/my-training-dataset",
        "training": {
            "type": "distillation",
            "teacher_model": "default/llama-3-2-3b-instruct",  # Teacher model
            "teacher_precision": "bf16",
            "distillation_ratio": 0.5,
            "distillation_temperature": 2.0,
            "batch_size": 64,
            "epochs": 2,
            "learning_rate": 5e-5,
            "max_seq_length": 2048,
            "parallelism": {"num_gpus_per_node": 1},
        },
    },
)
```

!!! note
    See [Knowledge Distillation constraints](hyperparameters.md) for requirements on model compatibility, tokenizer, and GPU memory.

---

## Job Configuration Reference

The job spec contains the model, dataset, training, output, deployment, and integration settings for the job. For key fields, the complete API schema, and W&B or MLflow integration options, see [Customization Job Reference](customization-job-reference.md).

---

## Training Output

When training completes, the system automatically:

1. **Uploads artifacts** to a new FileSet (`output.fileset`)
2. **Creates the output** based on PEFT configuration:

| PEFT Configuration | Output Created |
|---------------------|----------------|
| `peft: { type: "lora", ... }` | **Adapter** attached to the parent Model Entity |
| `peft` omitted | **New Model Entity** with all model weights (complete fine-tuned model) |

### LoRA Adapters

For LoRA jobs, the adapter is added to the parent Model Entity's `adapters` list:

```python
# After training completes, retrieve the model to see the adapter
model = client.models.retrieve(workspace="default", name="llama-3-2-1b")

for adapter in model.adapters or []:
    print(f"Adapter: {adapter.name}")
    print(f" Fileset: {adapter.fileset}")
    print(f" Enabled: {adapter.enabled}")
```

Adapters are enabled by default and will automatically be loaded by NIMs serving this model with LoRA support.
