# Create a Model Entity

<a id="ft-create-model-entity"></a>
Create a Model Entity that references your FileSet to enable customization jobs.

## Prerequisites

- Created a FileSet containing your model checkpoint (refer to [Create a Model FileSet](create-fileset.md)).
- Set the `NMP_BASE_URL` environment variable.

```bash
export NMP_BASE_URL="https://your-nemo-platform-url"
```

---

## Create the Model Entity

```python
import os
from nemo_platform import NeMoPlatform
from nemo_platform._exceptions import ConflictError

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

try:
    model = client.models.create(
        workspace="default",
        name="llama-3-2-1b",
        fileset="default/llama-3-2-1b",  # Reference: workspace/fileset-name
        description="Llama 3.2 1B base model for customization",
    )
    print(f"Created Model Entity: {model.name}")
except ConflictError:
    print("Model Entity already exists")
    model = client.models.retrieve(workspace="default", name="llama-3-2-1b")
```

??? "Example Response"
    :icon: code-square

    ```json
    {
      "id": "model-abc123def456",
      "name": "llama-3-2-1b",
      "workspace": "default",
      "description": "Llama 3.2 1B base model for customization",
      "fileset": "default/llama-3-2-1b",
      "spec": null,
      "adapters": [],
      "created_at": "2026-02-09T10:30:00Z",
      "updated_at": "2026-02-09T10:30:00Z"
    }
    ```

    Note: `spec` is initially `null` and will be auto-populated by the Models Controller.

---

## Wait for Model Spec Auto-Population

The platform's **Models Controller** automatically analyzes your model files and populates the `spec` field with metadata like architecture, parameter count, and layer information. This is required before running customization jobs.

```python
import time

# Poll until spec is populated
print("Waiting for model spec to be auto-populated...")
while True:
    model = client.models.retrieve(workspace="default", name="llama-3-2-1b")
    if model.spec:
        break
    print(" Still waiting...")
    time.sleep(5)

print(f"\nModel ready for customization!")
print(f" Family: {model.spec.family}")
print(f" Parameters: {model.spec.base_num_parameters:,}")
print(f" Hidden Size: {model.spec.hidden_size}")
print(f" Layers: {model.spec.num_layers}")
print(f" Attention Heads: {model.spec.num_attention_heads}")
```

??? "Example Model Spec"
    :icon: code-square

    ```json
    {
      "spec": {
        "family": "llama",
        "base_num_parameters": 1235814400,
        "hidden_size": 2048,
        "num_layers": 16,
        "num_attention_heads": 32,
        "num_key_value_heads": 8,
        "vocab_size": 128256,
        "max_sequence_length": 131072
      }
    }
    ```

---

## Verify the Model Entity

Before using in a customization job, verify everything is set up correctly:

```python
model = client.models.retrieve(workspace="default", name="llama-3-2-1b")

# Verification checks
assert model.spec is not None, "Model spec not yet populated - wait longer"
assert model.fileset, "FileSet reference missing"

print("Model Entity is ready for customization.")
print(f"\nUse in customization jobs as:")
print(f' model: "{model.workspace}/{model.name}"')
```

---

## Using the Model Entity in Customization Jobs

After your Model Entity is ready (has a populated `spec`), reference it in customization jobs:

```python
# Create a customization job using the Model Entity
job = client.customization.jobs.create(
    workspace="default",
    name="my-lora-job",
    spec={
        "model": "default/llama-3-2-1b",  # Created above
        "dataset": "fileset://default/my-training-dataset",
        "training": {"type": "sft", "peft": {"type": "lora"}, "epochs": 1},
    },
)
```

Refer to [create-job](../manage-customization-jobs/create-job.md) for complete job creation details.

---

## Post-Training Output

After a customization job completes, the output depends on the finetuning type:

- **LoRA training** (`peft: {"type": "lora"}`): An **adapter** is attached to this Model Entity. The adapter contains only the trained LoRA weights.
- **Full SFT training** (no `peft` config): A **new Model Entity** is created containing the complete fine-tuned model weights. This new entity has a `base_model` field linking back to the original.

For LoRA jobs, you can list adapters attached to a model:

```python
model = client.models.retrieve(workspace="default", name="llama-3-2-1b")

if model.adapters:
    print(f"Adapters attached to {model.name}:")
    for adapter in model.adapters:
        print(f" - {adapter.name} (enabled: {adapter.enabled})")
else:
    print("No adapters attached yet")
```

---

## Next Steps

- [Create a customization job](../manage-customization-jobs/create-job.md)
- [Understand hyperparameters](../manage-customization-jobs/hyperparameters.md)
