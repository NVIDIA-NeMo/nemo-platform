<a id="admin-manage-secrets"></a>
<a id="entities-secrets"></a>
# Manage Secrets

{{platform_name}} provides an interface to manage user-defined secrets. This allows you to securely store API keys to integrate with other providers. For example, you might want to store a Hugging Face API token as a secret to access models, or a Weights & Biases API key for experiment tracking.

## Concepts

A **secret** is a named resource that holds sensitive information, such as API keys or tokens.

- Secrets are unique within a **workspace**, meaning they exist within a specific workspace in {{platform_name}}. Operations which utilize secrets must specify the workspace in which the secret resides.
- All secrets are encrypted at rest. Once a secret is created, its value cannot be retrieved through the API—not even by workspace Admins. Users can view secret metadata (name, description, timestamps) but can only update or delete the secret, never read its value back.

- Only **Platform Administrators** can retrieve secret values. This restricted access ensures that sensitive credentials remain protected even from users with full workspace administrative privileges.

- Platform services access secrets internally as needed to facilitate user-requested operations, for example, when a job requires access to a Hugging Face model, or when reporting metrics to Weights & Biases.

- Secrets referenced by other resources (for example, customization configs) are referenced by their name and workspace.
 - A reference to a secret by another resource is stored in the format `workspace/secret_name`.

## Access Control

When authentication is enabled, secrets follow role-based access control:

| Role | List | View Metadata | Create | Update | Delete | Read Value |
|------|------|---------------|--------|--------|--------|------------|
| Viewer | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Editor | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| Admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| Platform Admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

!!! important "Even workspace **Admins** cannot read secret values. This is by design—secrets contain sensitive credentials that should not be exposed through the API. Only Platform Administrators have the elevated permissions required to retrieve secret values when absolutely necessary."

## Naming Requirements

Secret names must follow these rules:

- **Allowed characters**: letters (a-z, A-Z), digits (0-9), hyphens (`-`), underscores (`_`), and dots (`.`)
- **Maximum length**: 255 characters
- **Must contain at least one character** (cannot be empty)
- **Pattern**: `^[\w\-.]+$` (word characters, dots, and hyphens)

!!! tip "**Best practice**: Use lowercase letters, numbers, and hyphens only (for example, `my-api-key`). This keeps names portable across platform resources and job environments."

**Example valid names:** `hf-token`, `nim-api-key`, `wandb.key.production`, `my_secret_1`

## Understanding Workspaces

In {{platform_name}}, a **workspace** is used to organize and isolate resources. Workspaces function similarly to namespaces - they provide logical separation between different sets of resources.

- The default workspace is named `default`
- Most API operations require specifying a `workspace` parameter
- Secrets, model providers, jobs, and other resources exist within a workspace
- Resources in one workspace cannot directly access resources in another workspace

!!! tip "If you are just getting started, use the `default` workspace. You can create additional workspaces later to organize resources by team, project, or environment."

## Operations

To manage secrets, you can use the {{platform_name}} SDK. Below are examples of how to create, list, update, and delete secrets.

To work with secrets, you can use the following import and initialization:

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
```

### Creating Secrets

Creating a secret involves specifying a name, workspace, and the initial secret data.

```python
secret = client.secrets.create(
    name="my-secret", workspace="default", value="<your-secret-value>"
)
```

## Listing Secrets

You can list all secrets within a specific workspace. This returns metadata only.

```python
# List all secrets in the "default" workspace
secrets = client.secrets.list(workspace="default")
for secret in secrets.data:
    print(secret.name)
```

## Retrieving a Secret

To retrieve a single secret by name, use the `retrieve` method. This returns the secret's metadata only.

```python
# Get a specific secret's metadata
secret = client.secrets.retrieve(name="my-secret", workspace="default")
print(f"Secret: {secret.name}, Created: {secret.created_at}")
```

## Updating Secrets

To update a secret, you can change its `value` field.

```python
# Update the content of the secret
updated_secret = client.secrets.update(
    name="my-secret", workspace="default", value="<your-new-secret-value>"
)
```

## Deleting Secrets

Deleting a secret will remove the secret from the platform.

```python
# Delete a secret
client.secrets.delete(name="my-secret", workspace="default")
```

## Use Cases

### Hugging Face API Tokens

A Hugging Face API token secret allows {{platform_name}} to authenticate with the Hugging Face Hub for accessing models and repositories.

#### How are Hugging Face API Tokens Used?

{{platform_name}} uses Hugging Face api tokens to authenticate requests to the Hugging Face Hub. This enables users to download private models and upload customized models to their Hugging Face repositories.

#### Creating a Hugging Face Secret

To create a Hugging Face API key secret, use the {{platform_name}} SDK to create a new secret with your Hugging Face token.

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

hf_secret = client.secrets.create(
    name="my-hugging-face-token", workspace="default", value="<your-hugging-face-token>"
)
```

### Weights & Biases Keys

{{platform_name}} users can integrate with Weights & Biases by providing their API key as a secret. This allows the NeMo Customizer service to report training metrics to the user's W&B account.

#### How are Weights & Biases Keys Used?

When a Weights & Biases key is provided, the NeMo Customizer service sends telemetry data to W&B including:

- Job ID
- Training loss
- Validation loss
- Other relevant metrics

All metrics are stored under the user's `nvidia-nemo-customizer` project in their W&B account.

#### Creating a Weights & Biases Secret

To create a W&B secret, use the {{platform_name}} SDK to create a new secret with your W&B API key.

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

wandb_secret = client.secrets.create(
    name="my-wandb-key", workspace="default", value="<your-wandb-api-key>"
)
```

### External Inference Provider API Keys

When you register an external inference provider (such as [NVIDIA Build](https://build.nvidia.com/) or OpenAI), you store the provider's API key as a secret and reference it when creating the model provider.

#### How are External Provider Keys Used?

{{platform_name}} attaches the stored API key to every inference request forwarded through the Inference Gateway to the external provider. This lets you manage credentials centrally and rotate keys without recreating providers.

#### Creating an External Provider Secret


=== "CLI"

    ```bash
    echo "$NVIDIA_API_KEY" | nemo secrets create "nvidia-api-key" --from-file -
    ```

=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    client.secrets.create(name="nvidia-api-key", value=os.environ["NVIDIA_API_KEY"])
    ```

After creating the secret, reference it by name when [registering the provider](../../run-inference/about.md#add-external-providers).

## Encryption Configuration

!!! important "For production deployments, it is critical to configure secure encryption for secrets at rest. The default local encryption provider is intended for initial deployment or evaluation."

### Rotating or Migrating Encryption Keys

{{platform_name}} supports rotation of encryption keys used to secure secrets at rest. Key rotation can be performed by Platform Administrators to comply with security policies or to migrate between encryption providers.

**To rotate or migrate encryption keys**:

1. Add a new provider configuration to the platform config's secrets encryption settings. You can name the new provider as desired (for example, `v2`) and set it as the `current_provider`.

 ```yaml
 secrets:
 encryption:
 current_provider: new_provider_name
 providers:
 secret_key:
 # Keep the existing provider for decryption of old secrets
 v1:
 value: "<old-encryption-key>"
 # Add the new provider for encrypting new secrets
 v2:
 value: "<new-encryption-key>"
 # from_env: "NEW_ENCRYPTION_KEY_ENV_VAR" # Optional alternative to load from environment variable
 ```

2. Re-deploy the platform services to apply the new configuration.

2. As the platform administrator role, call the `/v2/secrets/rotate-encryption-keys` endpoint to initiate the rotation process. This will re-encrypt all existing secrets using the new provider. You can also initiate the rotation using the {{platform_name}} SDK:

 ```python
 import os
 from nemo_platform import NeMoPlatform

 client = NeMoPlatform(
     base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
     workspace="default",
 )

 # Initiate the key rotation process
 client.secrets.admin.rotate_encryption_keys()
 ```

 This operation can take some time depending on the number of secrets stored. During this process, both the old and new encryption providers must be available to ensure seamless access to secrets. Do not remove the old provider until rotation is confirmed completed.

 If any errors occur during rotation, they will be logged for review. You can retry the rotation operation as needed until all secrets are successfully re-encrypted.

4. To validate the rotation completed successfully, you can check the logs for the following confirmation message:

 ```text
 Completed rotation of encryption keys for all secrets
 ```

5. After rotation is confirmed, you can optionally remove the old provider configuration from the platform settings to prevent its further use.
