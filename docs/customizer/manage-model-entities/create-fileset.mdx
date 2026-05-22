# Create a Model FileSet

<a id="ft-create-model-fileset"></a>
Create a FileSet containing your base model checkpoint before creating a Model Entity.

## Prerequisites

- Obtained the base URL of your {{platform_name}}.
- For HuggingFace models: Created a secret with your HF token. Refer to [Manage Secrets](../../get-started/concepts/manage-secrets.md).
- Set the `NMP_BASE_URL` environment variable.

```bash
export NMP_BASE_URL="https://your-nemo-platform-url"
```

---

## From HuggingFace Hub

The most common method is downloading directly from HuggingFace:

=== "Python SDK"

    ```python
    import os
    from nemo_platform import ConflictError, NeMoPlatform
    from nemo_platform.types.files import HuggingfaceStorageConfigParam

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    HF_REPO_ID = "meta-llama/Llama-3.2-1B-Instruct"
    MODEL_NAME = "llama-3-2-1b"
    HF_SECRET_NAME = "my-hf-token"
    HF_TOKEN = os.environ.get("HF_TOKEN")
    if not HF_TOKEN:
        raise RuntimeError("Set HF_TOKEN before creating the HuggingFace secret.")

    # First, create a secret for your HF token (if not already created)
    try:
        hf_secret = client.secrets.create(
            name=HF_SECRET_NAME,
            workspace="default",
            value=HF_TOKEN,
        )
        print(f"Created secret: {HF_SECRET_NAME}")
    except ConflictError:
        print(f"Secret '{HF_SECRET_NAME}' already exists, continuing...")
        hf_secret = client.secrets.retrieve(name=HF_SECRET_NAME, workspace="default")

    # Create FileSet from HuggingFace
    try:
        fileset = client.files.filesets.create(
            workspace="default",
            name=MODEL_NAME,
            description="Llama 3.2 1B Instruct from HuggingFace",
            purpose="model",
            storage=HuggingfaceStorageConfigParam(
                type="huggingface",
                repo_id=HF_REPO_ID,
                repo_type="model",
                token_secret=hf_secret.name,
            ),
        )
        print(f"Created FileSet: {fileset.name}")
    except ConflictError:
        print(f"FileSet '{MODEL_NAME}' already exists, retrieving...")
        fileset = client.files.filesets.retrieve(workspace="default", name=MODEL_NAME)

    print(f"FileSet ready: {fileset.name}")
    ```

=== "CLI"

    ```bash
    export WORKSPACE="default"
    export HF_REPO_ID="meta-llama/Llama-3.2-1B-Instruct"
    export MODEL_NAME="llama-3-2-1b"
    export HF_SECRET_NAME="my-hf-token"

    # Export HF_TOKEN with your HuggingFace token before running this.
    : "${HF_TOKEN:?Set HF_TOKEN before creating the HuggingFace secret.}"

    nemo secrets get "$HF_SECRET_NAME" --workspace "$WORKSPACE" >/dev/null 2>&1 || \
      printf '%s' "$HF_TOKEN" | nemo secrets create "$HF_SECRET_NAME" \
        --workspace "$WORKSPACE" \
        --from-file -

    nemo files filesets create "$MODEL_NAME" \
      --workspace "$WORKSPACE" \
      --description "Llama 3.2 1B Instruct from HuggingFace" \
      --purpose model \
      --exist-ok \
      --storage '{
        "type": "huggingface",
        "repo_id": "'"$HF_REPO_ID"'",
        "repo_type": "model",
        "token_secret": "'"$HF_SECRET_NAME"'"
      }'

    nemo files filesets get "$MODEL_NAME" --workspace "$WORKSPACE"
    ```

!!! tip
    For gated models (like Llama), you need to:
    1. Accept the model license on HuggingFace
    2. Create a HuggingFace token with read access
    3. Store the token as a secret in the platform

---

## From NGC

For models from NVIDIA NGC:

=== "Python SDK"

    ```python
    import os
    from nemo_platform import ConflictError, NeMoPlatform
    from nemo_platform.types.files import NGCStorageConfigParam

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    MODEL_NAME = "nemotron-mini-4b"
    NGC_RESOURCE = "nemotron-mini-4b-instruct"
    NGC_ORG = "nvidia"
    NGC_TEAM = "nemo"
    NGC_VERSION = "1.0"
    NGC_API_KEY_SECRET = "my-ngc-key"
    NGC_API_KEY = os.environ.get("NGC_API_KEY")
    if not NGC_API_KEY:
        raise RuntimeError("Set NGC_API_KEY before creating the NGC secret.")

    # First, create a secret for your NGC API key (if not already created)
    try:
        ngc_secret = client.secrets.create(
            name=NGC_API_KEY_SECRET,
            workspace="default",
            value=NGC_API_KEY,
        )
        print(f"Created secret: {NGC_API_KEY_SECRET}")
    except ConflictError:
        print(f"Secret '{NGC_API_KEY_SECRET}' already exists, continuing...")
        ngc_secret = client.secrets.retrieve(name=NGC_API_KEY_SECRET, workspace="default")

    # Create FileSet from NGC
    try:
        fileset = client.files.filesets.create(
            workspace="default",
            name=MODEL_NAME,
            description="Nemotron Mini 4B from NGC",
            purpose="model",
            storage=NGCStorageConfigParam(
                type="ngc",
                org=NGC_ORG,
                team=NGC_TEAM,
                resource=NGC_RESOURCE,  # NGC resource name
                version=NGC_VERSION,
                api_key_secret=ngc_secret.name,
            ),
        )
        print(f"Created FileSet: {fileset.name}")
    except ConflictError:
        print("FileSet already exists, retrieving...")
        fileset = client.files.filesets.retrieve(workspace="default", name=MODEL_NAME)
    ```

=== "CLI"

    ```bash
    export WORKSPACE="default"
    export MODEL_NAME="nemotron-mini-4b"
    export NGC_RESOURCE="nemotron-mini-4b-instruct"
    export NGC_ORG="nvidia"
    export NGC_TEAM="nemo"
    export NGC_VERSION="1.0"
    export NGC_API_KEY_SECRET="my-ngc-key"

    # Export NGC_API_KEY with your NGC API key before running this.
    : "${NGC_API_KEY:?Set NGC_API_KEY before creating the NGC secret.}"

    nemo secrets get "$NGC_API_KEY_SECRET" --workspace "$WORKSPACE" >/dev/null 2>&1 || \
      printf '%s' "$NGC_API_KEY" | nemo secrets create "$NGC_API_KEY_SECRET" \
        --workspace "$WORKSPACE" \
        --from-file -

    nemo files filesets create "$MODEL_NAME" \
      --workspace "$WORKSPACE" \
      --description "Nemotron Mini 4B from NGC" \
      --purpose model \
      --exist-ok \
      --storage '{
        "type": "ngc",
        "org": "'"$NGC_ORG"'",
        "team": "'"$NGC_TEAM"'",
        "resource": "'"$NGC_RESOURCE"'",
        "version": "'"$NGC_VERSION"'",
        "api_key_secret": "'"$NGC_API_KEY_SECRET"'"
      }'

    nemo files filesets get "$MODEL_NAME" --workspace "$WORKSPACE"
    ```

---

## Check FileSet Status

Files are downloaded in the background after you create a FileSet. Check the status:

```python
# List files in the FileSet
files = client.files.list(
    workspace="default",
    fileset="llama-3-2-1b",
)

print(f"Files in FileSet ({len(files)} total):")
for f in files[:10]:  # Show first 10
    print(f" - {f.path} ({f.size:,} bytes)")
```

??? "Example Response"
    :icon: code-square

    ```json
    {
      "data": [
        {
          "file_ref": "/v2/workspaces/default/filesets/llama-3-2-1b/-/config.json",
          "path": "config.json",
          "size": 1234,
          "cache_status": null
        },
        {
          "file_ref": "/v2/workspaces/default/filesets/llama-3-2-1b/-/model.safetensors",
          "path": "model.safetensors",
          "size": 2400000000,
          "cache_status": null
        },
        {
          "file_ref": "/v2/workspaces/default/filesets/llama-3-2-1b/-/tokenizer.json",
          "path": "tokenizer.json",
          "size": 9085657,
          "cache_status": null
        },
        {
          "file_ref": "/v2/workspaces/default/filesets/llama-3-2-1b/-/tokenizer_config.json",
          "path": "tokenizer_config.json",
          "size": 901,
          "cache_status": null
        }
      ]
    }
    ```

---

## Next Steps

Proceed to [create a Model Entity](create-model-entity.md).
