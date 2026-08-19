# Secrets

Types:

```python
from nemo_platform.types.secrets import (
    PlatformSecretAccessResponse,
    PlatformSecretCreateRequest,
    PlatformSecretResponse,
    PlatformSecretResponsesPage,
    PlatformSecretUpdateRequest,
)
```

Methods:

- <code title="post /apis/secrets/v2/workspaces/{workspace}/secrets">client.secrets.<a href="./src/nemo_platform/resources/secrets/secrets.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/secrets/secret_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/secrets/platform_secret_response.py">PlatformSecretResponse</a></code>
- <code title="get /apis/secrets/v2/workspaces/{workspace}/secrets/{name}">client.secrets.<a href="./src/nemo_platform/resources/secrets/secrets.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/secrets/platform_secret_response.py">PlatformSecretResponse</a></code>
- <code title="patch /apis/secrets/v2/workspaces/{workspace}/secrets/{name}">client.secrets.<a href="./src/nemo_platform/resources/secrets/secrets.py">update</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/secrets/secret_update_params.py">params</a>) -> <a href="./src/nemo_platform/types/secrets/platform_secret_response.py">PlatformSecretResponse</a></code>
- <code title="get /apis/secrets/v2/workspaces/{workspace}/secrets">client.secrets.<a href="./src/nemo_platform/resources/secrets/secrets.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/secrets/secret_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/secrets/platform_secret_response.py">SyncDefaultPagination[PlatformSecretResponse]</a></code>
- <code title="delete /apis/secrets/v2/workspaces/{workspace}/secrets/{name}">client.secrets.<a href="./src/nemo_platform/resources/secrets/secrets.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="get /apis/secrets/v2/workspaces/{workspace}/secrets/{name}/access">client.secrets.<a href="./src/nemo_platform/resources/secrets/secrets.py">access</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/secrets/platform_secret_access_response.py">PlatformSecretAccessResponse</a></code>

## Admin

Types:

```python
from nemo_platform.types.secrets import PlatformSecretAdminRotationResponse
```

Methods:

- <code title="post /apis/secrets/v2/rotate-encryption-keys">client.secrets.admin.<a href="./src/nemo_platform/resources/secrets/admin.py">rotate_encryption_keys</a>() -> <a href="./src/nemo_platform/types/secrets/platform_secret_admin_rotation_response.py">PlatformSecretAdminRotationResponse</a></code>
