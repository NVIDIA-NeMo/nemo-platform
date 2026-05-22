# Manage Model Entities for Customization

<a id="ft-manage-model-entities"></a>
Before running a customization job, you need to set up a **Model Entity** that points to your base model checkpoint. This section covers creating the required FileSet and Model Entity.

## Task Guides

<div class="grid cards" markdown>

-   **[Create a Model FileSet](create-fileset.md)**

    ---

    Create a FileSet containing your base model checkpoint from HuggingFace, NGC, or local storage.

-   **[Create a Model Entity](create-model-entity.md)**

    ---

    Create a Model Entity that references your FileSet and enables customization.

</div>

---

## Key Concepts

### What is a FileSet?

A **FileSet** is a collection of files managed by the platform. For customization, you create a FileSet containing:

- Model weights (`.safetensors`, `.bin`, or `.nemo` files)
- Model configuration (`config.json`)
- Tokenizer files (`tokenizer.json`, `tokenizer_config.json`, and so on)

FileSets can be populated from:
-   **HuggingFace Hub** - Download directly from HF repositories
-   **NGC** - Download from NVIDIA NGC catalogs
-   **Local upload** - Upload files from your local machine

### What is a Model Entity?

A **Model Entity** is the platform's representation of a model. It contains:

-   **FileSet reference** - Points to where the model files are stored
-   **Model Spec** - Auto-populated metadata about the model architecture
-   **Adapters** - LoRA or other adapters attached to this model (populated after training)
-   **Base model link** - For fine-tuned models, links back to the parent

---

## Quick Start Example

Complete example of setting up a model for customization:

!!! tip
    **HuggingFace Token**: If downloading from a gated HuggingFace repository (like Llama models), you will need to create a secret containing your HuggingFace API token first. Refer to [Manage Secrets](../../get-started/concepts/manage-secrets.md) for instructions.

```python
import os
import time
from nemo_platform import NeMoPlatform
from nemo_platform._exceptions import ConflictError
from nemo_platform.types.files import HuggingfaceStorageConfigParam

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Step 1: Create FileSet from HuggingFace
try:
    fileset = client.files.filesets.create(
        workspace="default",
        name="llama-3-2-1b",
        description="Llama 3.2 1B base model from HuggingFace",
        storage=HuggingfaceStorageConfigParam(
            type="huggingface",
            repo_id="meta-llama/Llama-3.2-1B-Instruct",
            repo_type="model",
            token_secret="my-hf-token",  # Refer to Manage Secrets documentation
        ),
    )
    print(f"Created FileSet: {fileset.name}")
except ConflictError:
    print("FileSet already exists, retrieving...")
    fileset = client.files.filesets.retrieve(workspace="default", name="llama-3-2-1b")

# Step 2: Create Model Entity
try:
    model = client.models.create(
        workspace="default",
        name="llama-3-2-1b",
        fileset="default/llama-3-2-1b",  # Reference to the FileSet
        description="Llama 3.2 1B base model for customization",
    )
    print(f"Created Model Entity: {model.name}")
except ConflictError:
    print("Model Entity already exists, retrieving...")
    model = client.models.retrieve(workspace="default", name="llama-3-2-1b")

# Step 3: Wait for ModelSpec to be auto-populated
print("Waiting for model spec to be populated...")
while not model.spec:
    time.sleep(5)
    model = client.models.retrieve(workspace="default", name="llama-3-2-1b")

print(f"Model ready!")
print(f" Architecture: {model.spec.family}")
print(f" Parameters: {model.spec.base_num_parameters:,}")
print(f" Layers: {model.spec.num_layers}")
```

After the Model Entity is ready (has a `spec`), you can use it in customization jobs with `model: "default/llama-3-2-1b"`.

---
