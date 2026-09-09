# Reference
## Discovery
<details><summary><code>client.discovery.<a href="src/nvidia/discovery/client.py">get_auth_discovery</a>() -> AuthDiscoveryResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Return authentication configuration for CLI/SDK discovery.

This endpoint is unauthenticated and returns the information clients
need to authenticate with this NeMo Platform deployment.

**Response fields:**

- `auth_enabled`: Whether authentication is enabled on this cluster
- `oidc`: OIDC configuration (only present when OIDC is enabled)
  - `issuer`: The OIDC issuer URL
  - `authorization_endpoint`: Authorization endpoint for browser-based flows
  - `token_endpoint`: Token exchange endpoint
  - `device_authorization_endpoint`: Device flow authorization endpoint (for CLI)
  - `userinfo_endpoint`: UserInfo endpoint
  - `client_id`: OAuth client ID to use
  - `default_scopes`: OAuth scopes to request during authentication
  - `scope_prefix`: Prefix to prepend to custom scopes (those with ':' or '.default')
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.discovery.get_auth_discovery()

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Iam
<details><summary><code>client.iam.<a href="src/nvidia/iam/client.py">list_role_bindings</a>(...) -> RoleBindingsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List all role bindings (Platform Admin only)
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.iam.list_role_bindings()

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[str]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[RoleBindingFilter]` — Filter role bindings by principal, workspace, role, granted_by, is_active, granted_at, and revoked_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.iam.<a href="src/nvidia/iam/client.py">create_role_binding</a>(...) -> RoleBinding</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new role binding (Platform Admin only)
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.iam.create_role_binding(
    principal="principal",
    role="role",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**principal:** `str` — The principal identifier (email, user ID, or group ID)
    
</dd>
</dl>

<dl>
<dd>

**role:** `str` — The role name (e.g., 'Viewer', 'Editor', 'Admin')
    
</dd>
</dl>

<dl>
<dd>

**wait_role_propagation:** `typing.Optional[bool]` — If true, wait for role to propagate before returning (default: true). Set to false for bulk operations.
    
</dd>
</dl>

<dl>
<dd>

**workspace:** `typing.Optional[str]` — The workspace this binding applies to. None for platform-level roles.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.iam.<a href="src/nvidia/iam/client.py">get_role_binding</a>(...) -> RoleBinding</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific role binding (Platform Admin only)
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.iam.get_role_binding(
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.iam.<a href="src/nvidia/iam/client.py">revoke_role_binding</a>(...) -> DeleteResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Revoke a role binding (Platform Admin only)
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.iam.revoke_role_binding(
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**wait_role_propagation:** `typing.Optional[bool]` — If true, wait for role to propagate before returning (default: true). Set to false for bulk operations.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## EntityStore
<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">get_entity_by_id</a>(...) -> Entity</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific entity by its unique identifier.
This endpoint is primarily for debugging and internal use.

Example:
```
GET /apis/entities/v2/entities/customization-config-5Q2LoF8z8M9JZxZsHwJKNn
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.get_entity_by_id(
    id="id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">list_workspaces</a>(...) -> WorkspacesPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List all workspaces with pagination.

When authentication is enabled, only workspaces the principal has access to
are returned. Service principals and platform admins have access to all workspaces.

Query Parameters:
- page, page_size: Pagination
- sort: Sort field
- filter: Advanced filters (JSON, text, or bracket notation)

Example:
```
GET /apis/entities/v2/workspaces?sort=-created_at&page=1&page_size=10
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.list_workspaces()

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Items per page
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[GenericSortField]` — Sort field
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[str]` 

Query filter expression. Supports text and JSON syntaxes:
- Text: name:"value" AND status>500 with operators : ~ > >= < <= IN NOT IN AND OR and negation prefix -
- Object (JSON): {"name":{"$like":"value"}} with operators $eq, $like, $lt, $lte, $gt, $gte, $in, $nin, $and, $or, $not
- Bracket notation: ?filter[name][$like]=value
- Relationship traversal: ?filter[relationship][$exists]=true or ?filter[relationship][field]=value
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">create_workspace</a>(...) -> Workspace</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new workspace.

The creator is automatically granted Admin role on the workspace.
By default, this endpoint waits for the Admin role to propagate before returning.
Use `wait_role_propagation=false` to skip waiting (useful for bulk operations).

Example:
```
POST /apis/entities/v2/workspaces
{
    "name": "ml-team",
    "description": "Machine Learning Team workspace"
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.create_workspace(
    name="ml-team",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**name:** `str` — Workspace name (unique identifier). Name must start with a lowercase letter, be 2-63 characters, and contain only lowercase letters, digits, and hyphens (no consecutive hyphens, cannot end with a hyphen).
    
</dd>
</dl>

<dl>
<dd>

**wait_role_propagation:** `typing.Optional[bool]` — If true, wait for Admin role to propagate before returning (default: true). Set to false for bulk operations.
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the workspace
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">get_workspace</a>(...) -> Workspace</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific workspace by ID.

Example:
```
GET /apis/entities/v2/workspaces/ml-team
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.get_workspace(
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">update_workspace</a>(...) -> Workspace</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update a workspace's description.

Example:
```
PUT /apis/entities/v2/workspaces/ml-team
{
    "description": "Updated description for ML Team"
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.update_workspace(
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Updated description
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">delete_workspace</a>(...) -> DeleteResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a workspace.

This marks the workspace for deletion and returns immediately. The workspace
will no longer be accessible via the API. An asynchronous cleanup controller
will handle deletion of all entities and external resources.

Role bindings are immediately deleted to revoke access.

Example:
```
DELETE /apis/entities/v2/workspaces/ml-team
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.delete_workspace(
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">list_entities</a>(...) -> EntitiesPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List all entities of a specific type in the given workspace.

Use workspace="-" to list entities across all workspaces the principal has
access to.

Query Parameters:
- sort: Sort field
- page, page_size: Pagination
- filter: Advanced filters (JSON, text, or bracket notation)

Examples:
```
GET /apis/entities/v2/workspaces/default/entities/customization_config?sort=-created_at
GET /apis/entities/v2/workspaces/-/entities/customization_config  # Cross-workspace query
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.list_entities(
    workspace="workspace",
    entity_type="entity_type",
    sort="-created_at",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**entity_type:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Items per page
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[str]` — Sort field
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[str]` 

Query filter expression. Supports text and JSON syntaxes:
- Text: name:"value" AND status>500 with operators : ~ > >= < <= IN NOT IN AND OR and negation prefix -
- Object (JSON): {"name":{"$like":"value"}} with operators $eq, $like, $lt, $lte, $gt, $gte, $in, $nin, $and, $or, $not
- Bracket notation: ?filter[name][$like]=value
- Relationship traversal: ?filter[relationship][$exists]=true or ?filter[relationship][field]=value
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">create_entity</a>(...) -> Entity</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new entity of the specified type in the given workspace.

If name is not provided, it will be auto-generated based on the entity type.

Example:
```
POST /apis/entities/v2/workspaces/default/entities/customization_config
{
    "name": "my-config",
    "data": {
        "target_id": "llama-2-7b",
        "training_options": {"learning_rate": 0.01}
    }
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.create_entity(
    workspace="workspace",
    entity_type="entity_type",
    data={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**entity_type:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**data:** `typing.Dict[str, typing.Any]` — Entity-specific data (schema is opaque to entity store, validated by client SDK)
    
</dd>
</dl>

<dl>
<dd>

**name:** `typing.Optional[str]` — Entity name (optional - auto-generated if not provided). Name must start with a lowercase letter, be 2-63 characters, and contain only lowercase letters, digits, and hyphens (no consecutive hyphens, cannot end with a hyphen).
    
</dd>
</dl>

<dl>
<dd>

**parent:** `typing.Optional[str]` — Parent entity ID for nested entities
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The name of the project associated with this entity
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">get_entity_by_name</a>(...) -> Entity</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific entity by its workspace, type, and name.

Example:
```
GET /apis/entities/v2/workspaces/default/entities/customization_config/my-config
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.get_entity_by_name(
    workspace="workspace",
    entity_type="entity_type",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**entity_type:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**parent:** `typing.Optional[str]` — Parent entity ID for nested entities
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">update_entity_by_name</a>(...) -> Entity</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update an entity by its name. Optionally change the entity's name.

Example:
```
PUT /apis/entities/v2/workspaces/default/entities/customization_config/my-config
{
    "data": {
        "target_id": "llama-2-7b",
        "training_options": {"learning_rate": 0.02}
    }
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.update_entity_by_name(
    workspace="workspace",
    entity_type="entity_type",
    name="name",
    data={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**entity_type:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**data:** `typing.Dict[str, typing.Any]` — Updated entity-specific data
    
</dd>
</dl>

<dl>
<dd>

**parent:** `typing.Optional[str]` — Parent entity ID for nested entities
    
</dd>
</dl>

<dl>
<dd>

**new_name:** `typing.Optional[str]` — Updated entity name (optional). Name must start with a lowercase letter, be 2-63 characters, and contain only lowercase letters, digits, and hyphens (no consecutive hyphens, cannot end with a hyphen).
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The name of the project associated with this entity
    
</dd>
</dl>

<dl>
<dd>

**expected_db_version:** `typing.Optional[int]` — Optional database version for optimistic locking. Update only succeeds if current version matches.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">delete_entity_by_name</a>(...) -> DeleteResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete an entity by its name.

Example:
```
DELETE /apis/entities/v2/workspaces/default/entities/customization_config/my-config
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.delete_entity_by_name(
    workspace="workspace",
    entity_type="entity_type",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**entity_type:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**parent:** `typing.Optional[str]` — Parent entity ID for nested entities
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">list_workspace_members</a>(...) -> WorkspaceMemberListResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List all members of a workspace with their roles.

Returns a list of all principals with active role bindings in the workspace.

Example:
```
GET /apis/entities/v2/workspaces/ml-team/members
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.list_workspace_members(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">add_workspace_member</a>(...) -> WorkspaceMember</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Add a new member to the workspace with specified roles.

This creates role bindings for the specified principal with the given roles.
By default, this endpoint waits for the roles to propagate before returning.
Use `wait_role_propagation=false` to skip waiting (useful for bulk operations).

Example:
```
POST /apis/entities/v2/workspaces/ml-team/members
{
    "principal": "user@example.com",
    "roles": ["Editor"]
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.add_workspace_member(
    workspace="workspace",
    principal="user@example.com",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**principal:** `str` — The principal identifier (email, user ID, or group ID)
    
</dd>
</dl>

<dl>
<dd>

**wait_role_propagation:** `typing.Optional[bool]` — If true, wait for roles to propagate before returning (default: true). Set to false for bulk operations.
    
</dd>
</dl>

<dl>
<dd>

**roles:** `typing.Optional[typing.List[str]]` — List of roles to grant to the principal
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">update_workspace_member</a>(...) -> WorkspaceMember</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update the roles for a workspace member.

This will revoke existing roles not in the new list and add new roles.
By default, this endpoint waits for the roles to propagate before returning.
Use `wait_role_propagation=false` to skip waiting (useful for bulk operations).

Example:
```
PUT /apis/entities/v2/workspaces/ml-team/members/user@example.com
{
    "roles": ["Viewer", "Editor"]
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.update_workspace_member(
    workspace="workspace",
    principal_id="principal_id",
    roles=[
        "Viewer"
    ],
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**principal_id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**roles:** `typing.List[str]` — Updated list of roles for the principal
    
</dd>
</dl>

<dl>
<dd>

**wait_role_propagation:** `typing.Optional[bool]` — If true, wait for roles to propagate before returning (default: true). Set to false for bulk operations.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">remove_workspace_member</a>(...) -> DeleteResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Remove a member from the workspace by revoking all their roles.

This revokes all active role bindings for the principal in the workspace.
By default, this endpoint waits for all roles to be revoked before returning.
Use `wait_role_propagation=false` to skip waiting (useful for bulk operations).

Example:
```
DELETE /apis/entities/v2/workspaces/ml-team/members/user@example.com
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.remove_workspace_member(
    workspace="workspace",
    principal_id="principal_id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**principal_id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**wait_role_propagation:** `typing.Optional[bool]` — If true, wait for roles to propagate before returning (default: true). Set to false for bulk operations.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">list_projects</a>(...) -> ProjectsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List all projects in a workspace with pagination.

Query Parameters:
- page, page_size: Pagination
- sort: Sort field
- filter: Advanced filters

Example:
```
GET /apis/entities/v2/workspaces/default/projects?sort=-created_at&page=1&page_size=10
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.list_projects(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Items per page
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[ProjectSortField]` — Sort field
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[str]` 

Query filter expression. Supports text and JSON syntaxes:
- Text: name:"value" AND status>500 with operators : ~ > >= < <= IN NOT IN AND OR and negation prefix -
- Object (JSON): {"name":{"$like":"value"}} with operators $eq, $like, $lt, $lte, $gt, $gte, $in, $nin, $and, $or, $not
- Bracket notation: ?filter[name][$like]=value
- Relationship traversal: ?filter[relationship][$exists]=true or ?filter[relationship][field]=value
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">create_project</a>(...) -> Project</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new project in the given workspace.

Example:
```
POST /apis/entities/v2/workspaces/default/projects
{
    "name": "ml-project",
    "description": "Machine Learning project"
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.create_project(
    workspace="workspace",
    name="ml-project",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Project name (unique within workspace). Name must start with a lowercase letter, be 2-63 characters, and contain only lowercase letters, digits, and hyphens (no consecutive hyphens, cannot end with a hyphen).
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the project
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">get_project</a>(...) -> Project</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific project by its workspace and name.

Example:
```
GET /apis/entities/v2/workspaces/default/projects/ml-project
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.get_project(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">update_project</a>(...) -> Project</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update a project's description.

Example:
```
PUT /apis/entities/v2/workspaces/default/projects/ml-project
{
    "description": "Updated description for ML project"
}
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.update_project(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Updated description
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.entity_store.<a href="src/nvidia/entity_store/client.py">delete_project</a>(...) -> DeleteResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a project.

Example:
```
DELETE /apis/entities/v2/workspaces/default/projects/ml-project
```
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.entity_store.delete_project(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Files
<details><summary><code>client.files.<a href="src/nvidia/files/client.py">list_filesets</a>(...) -> FilesetOutputsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List Filesets endpoint with filtering and pagination.

Supports filtering by name, description, purpose, storage_type, created_at, and updated_at via query parameters.
Returns paginated results with sorting options.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.list_filesets(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[GenericSortField]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[FilesetFilter]` — Filter filesets by name, description, purpose, storage_type, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">create_fileset</a>(...) -> FilesetOutput</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new fileset.

If no storage configuration is provided, the default storage backend will be used.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.create_fileset(
    workspace="workspace",
    name="training-data-v1",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — The name of the fileset. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — The description of the fileset.
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The name of the project associated with this fileset.
    
</dd>
</dl>

<dl>
<dd>

**storage:** `typing.Optional[CreateFilesetRequestStorage]` — The storage configuration for the fileset. If not provided, uses default storage.
    
</dd>
</dl>

<dl>
<dd>

**purpose:** `typing.Optional[FilesetPurpose]` — The purpose of the fileset.
    
</dd>
</dl>

<dl>
<dd>

**metadata:** `typing.Optional[FilesetMetadataInput]` — Purpose-specific metadata. Use the purpose as the key (e.g., {dataset: {...}}).
    
</dd>
</dl>

<dl>
<dd>

**custom_fields:** `typing.Optional[typing.Dict[str, typing.Any]]` — Custom fields for the fileset.
    
</dd>
</dl>

<dl>
<dd>

**cache:** `typing.Optional[bool]` — Cache all files after creation. Only applies to external storage.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">retrieve_fileset</a>(...) -> FilesetOutput</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get Fileset by Workspace and Name.

Returns the details of a specific fileset identified by its workspace and name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.retrieve_fileset(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">delete_fileset</a>(...) -> FilesetOutput</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete Fileset.

Permanently deletes a fileset from the platform.
Returns metadata about the deleted fileset.
For local storage backends, this also deletes the underlying files.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.delete_fileset(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">update_fileset_metadata</a>(...) -> FilesetOutput</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update Fileset Metadata.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.update_fileset_metadata(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — The description of the fileset.
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The name of the project associated with this fileset.
    
</dd>
</dl>

<dl>
<dd>

**purpose:** `typing.Optional[FilesetPurpose]` — The purpose of the fileset.
    
</dd>
</dl>

<dl>
<dd>

**metadata:** `typing.Optional[FilesetMetadataInput]` — Purpose-specific metadata. Use the purpose as the key (e.g., {dataset: {...}}).
    
</dd>
</dl>

<dl>
<dd>

**custom_fields:** `typing.Optional[typing.Dict[str, typing.Any]]` — Custom fields for the fileset.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">download_file_apis_files_v2workspaces_workspace_filesets_name_path_get</a>(...) -> typing.Iterator[bytes]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Download file content from a fileset.

Supports HTTP Range requests for partial content retrieval (status 206).
Returns the full file content (status 200) if no Range header is provided.
For external resources (HuggingFace, NGC), content is cached locally on first access.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.download_file_apis_files_v2workspaces_workspace_filesets_name_path_get(
    workspace="workspace",
    name="name",
    path="path",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**path:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">upload_file_apis_files_v2workspaces_workspace_filesets_name_path_put</a>(...) -> FilesetFileOutput</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Upload file content to a fileset.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
client.files.upload_file_apis_files_v2workspaces_workspace_filesets_name_path_put(...)
```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**path:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Union[bytes, typing.Iterator[bytes], typing.AsyncIterator[bytes]]` — Upload the file either as a raw octet stream.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">delete_file_apis_files_v2workspaces_workspace_filesets_name_path_delete</a>(...) -> FilesetFileOutput</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a specific file from a fileset.

Permanently deletes the file from the storage backend.
Returns metadata about the deleted file.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.delete_file_apis_files_v2workspaces_workspace_filesets_name_path_delete(
    workspace="workspace",
    name="name",
    path="path",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**path:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">head_file_apis_files_v2workspaces_workspace_filesets_name_path_head</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get file metadata without downloading content.

HEAD requests are often used before Range GETs to ensure the server
supports partial downloads (e.g., DuckDB's httpfs).
Returns Accept-Ranges, Content-Length, and Content-Type headers.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.head_file_apis_files_v2workspaces_workspace_filesets_name_path_head(
    workspace="workspace",
    name="name",
    path="path",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**path:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.files.<a href="src/nvidia/files/client.py">list_fileset_files</a>(...) -> ListFilesetFilesResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List Files in Fileset.

Returns a list of files stored in the specified fileset.
Optionally filter by path prefix to list files under a specific directory.

Each file includes a cache_status field:
- "not_cacheable": File is on default storage, caching not applicable
- "cached": File exists in cache storage
- "caching": File is currently being downloaded and cached
- "not_cached": File not in cache, will be cached on next download
- null: External storage, but cache status not checked (use include_cache_status=true)
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.files.list_fileset_files(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**path:** `typing.Optional[str]` — Filter files by path prefix
    
</dd>
</dl>

<dl>
<dd>

**include_cache_status:** `typing.Optional[bool]` — Check and return cache status for each file. When false, storage files return null for cache_status.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Otlp
<details><summary><code>client.otlp.<a href="src/nvidia/otlp/client.py">upload_otlp_logs</a>(...) -> OtelExportLogsServiceResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Upload OTLP logs to a specified fileset in JSON or Protobuf format.

Supports both application/json and application/x-protobuf content types.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.otlp.upload_otlp_logs(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.otlp.<a href="src/nvidia/otlp/client.py">query_otlp_logs</a>(...) -> PlatformJobLogPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Query logs from parquet files in a fileset.

This is an internal endpoint that runs DuckDB queries with direct storage
access.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.otlp.query_otlp_logs(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**filters:** `typing.Optional[typing.Dict[str, str]]` — Key-value filters to apply to the query
    
</dd>
</dl>

<dl>
<dd>

**limit:** `typing.Optional[int]` — Maximum number of results to return
    
</dd>
</dl>

<dl>
<dd>

**page_cursor:** `typing.Optional[str]` — Cursor for pagination
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Guardrails
<details><summary><code>client.guardrails.<a href="src/nvidia/guardrails/client.py">check</a>(...) -> GuardrailCheckResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Chat completion for the provided conversation.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi
from nvidia.guardrails import GuardrailCheckRequestMessagesItem_System

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.guardrails.check(
    workspace="workspace",
    model="model",
    messages=[
        GuardrailCheckRequestMessagesItem_System(
            content="content",
        )
    ],
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**model:** `str` — The model to use for completion. Must be one of the available models.
    
</dd>
</dl>

<dl>
<dd>

**messages:** `typing.List[GuardrailCheckRequestMessagesItem]` — A list of messages comprising the conversation so far
    
</dd>
</dl>

<dl>
<dd>

**response_format:** `typing.Optional[typing.Dict[str, typing.Any]]` — Format of the response. Use {'type': 'json_object'} for JSON mode or {'type': 'json_schema', 'json_schema': {...}} for structured outputs.
    
</dd>
</dl>

<dl>
<dd>

**max_tokens:** `typing.Optional[int]` — The maximum number of tokens that can be generated in the chat completion.
    
</dd>
</dl>

<dl>
<dd>

**n:** `typing.Optional[int]` — How many chat completion choices to generate for each input message.
    
</dd>
</dl>

<dl>
<dd>

**stream:** `typing.Optional[bool]` — If set, partial message deltas will be sent, like in ChatGPT.
    
</dd>
</dl>

<dl>
<dd>

**temperature:** `typing.Optional[float]` — What sampling temperature to use, between 0 and 2.
    
</dd>
</dl>

<dl>
<dd>

**top_p:** `typing.Optional[float]` — An alternative to sampling with temperature, called nucleus sampling.
    
</dd>
</dl>

<dl>
<dd>

**stop:** `typing.Optional[GuardrailCheckRequestStop]` — Up to 4 sequences where the API will stop generating further tokens.
    
</dd>
</dl>

<dl>
<dd>

**frequency_penalty:** `typing.Optional[float]` — Positive values penalize new tokens based on their existing frequency in the text.
    
</dd>
</dl>

<dl>
<dd>

**presence_penalty:** `typing.Optional[float]` — Positive values penalize new tokens based on whether they appear in the text so far.
    
</dd>
</dl>

<dl>
<dd>

**function_call:** `typing.Optional[GuardrailCheckRequestFunctionCall]` — Deprecated in favor of tool_choice. 'none' means the model will not call a function and instead generates a message. 'auto' means the model can pick between generating a message or calling a function. Specifying a particular function via {'name': 'my_function'} forces the model to call that function.
    
</dd>
</dl>

<dl>
<dd>

**seed:** `typing.Optional[int]` — If specified, attempts to sample deterministically.
    
</dd>
</dl>

<dl>
<dd>

**logit_bias:** `typing.Optional[typing.Dict[str, float]]` — Modify the likelihood of specified tokens appearing in the completion. Maps token IDs (as strings) to bias values from -100 to 100.
    
</dd>
</dl>

<dl>
<dd>

**top_logprobs:** `typing.Optional[int]` — The number of most likely tokens to return at each token position.
    
</dd>
</dl>

<dl>
<dd>

**logprobs:** `typing.Optional[bool]` — Whether to return log probabilities of the output tokens or not. If true, returns the log probabilities of each output token returned in the content of message
    
</dd>
</dl>

<dl>
<dd>

**tool_choice:** `typing.Optional[GuardrailCheckRequestToolChoice]` — Controls which (if any) tool is called by the model. 'none' means no tool is called, 'auto' lets the model decide, 'required' forces a tool call.
    
</dd>
</dl>

<dl>
<dd>

**user:** `typing.Optional[str]` — A unique identifier representing your end-user, used by some providers for abuse monitoring.
    
</dd>
</dl>

<dl>
<dd>

**tools:** `typing.Optional[typing.List[typing.Dict[str, typing.Any]]]` — A list of tools the model may call. Each tool is an object with a 'type' field and a 'function' definition.
    
</dd>
</dl>

<dl>
<dd>

**ignore_eos:** `typing.Optional[bool]` — Ignore the eos when running
    
</dd>
</dl>

<dl>
<dd>

**reasoning_effort:** `typing.Optional[str]` — Constrains effort on reasoning for reasoning models. Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning in a response.
    
</dd>
</dl>

<dl>
<dd>

**max_completion_tokens:** `typing.Optional[int]` — An upper bound for the number of tokens that can be generated for a completion, including visible output tokens and reasoning tokens. Preferred over max_tokens for reasoning models.
    
</dd>
</dl>

<dl>
<dd>

**stream_options:** `typing.Optional[typing.Dict[str, bool]]` — Options for streaming response. Only set this when stream=True. Supports include_usage to receive token usage in the final stream chunk.
    
</dd>
</dl>

<dl>
<dd>

**vision:** `typing.Optional[bool]` — Whether this is a vision-capable request with image inputs.
    
</dd>
</dl>

<dl>
<dd>

**guardrails:** `typing.Optional[GuardrailsDataInput]` — Guardrails specific options for the request.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.guardrails.<a href="src/nvidia/guardrails/client.py">list_guardrail_configs</a>(...) -> GuardrailConfigsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List available guardrail configs.

Lists guardrail configs for a specific workspace.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.guardrails.list_guardrail_configs(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[GenericSortField]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[GuardrailConfigFilter]` — Filter guardrail configs by name, description, project, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.guardrails.<a href="src/nvidia/guardrails/client.py">create_config</a>(...) -> GuardrailConfig</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new guardrail config.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.guardrails.create_config(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — The name of the guardrail config
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Description of the guardrail config
    
</dd>
</dl>

<dl>
<dd>

**data:** `typing.Optional[typing.Dict[str, typing.Any]]` — Guardrail configuration data
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.guardrails.<a href="src/nvidia/guardrails/client.py">get_guardrail_config</a>(...) -> GuardrailConfig</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get info about a guardrail configuration.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.guardrails.get_guardrail_config(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.guardrails.<a href="src/nvidia/guardrails/client.py">delete_config</a>(...) -> DeleteResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a guardrail config.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.guardrails.delete_config(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.guardrails.<a href="src/nvidia/guardrails/client.py">update_config</a>(...) -> GuardrailConfig</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update model metadata. If the request body has an empty field,
keep the old value.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.guardrails.update_config(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Description of the guardrail config
    
</dd>
</dl>

<dl>
<dd>

**data:** `typing.Optional[typing.Dict[str, typing.Any]]` — Guardrail configuration data
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## InferenceGateway
<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">gateway_proxy_get</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to model entity inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.gateway_proxy_get(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">gateway_proxy_post</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to model entity inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.gateway_proxy_post(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">gateway_proxy_put</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to model entity inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.gateway_proxy_put(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">gateway_proxy_delete</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to model entity inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.gateway_proxy_delete(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">gateway_proxy_patch</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to model entity inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.gateway_proxy_patch(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">openai_proxy_list_models</a>(...) -> OpenAiListModelsResp</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

This endpoint aggregates models from all model entities and returns them
in OpenAI's list models format. Each model ID is the model entity identifier
in format workspace/model_entity_name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.openai_proxy_list_models(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">openai_proxy_get_model</a>(...) -> OpenAiModelResp</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Retrieve information about a specific OpenAI-compatible model.
Workspace is always taken from the URL path; name may be model_entity_name
or workspace/model_entity_name (workspace prefix is ignored).
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.openai_proxy_get_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">openai_proxy_get</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to OpenAI-compatible inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.openai_proxy_get(
    workspace="workspace",
    trailing_uri="trailing_uri",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">openai_proxy_post</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to OpenAI-compatible inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.openai_proxy_post(
    workspace="workspace",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">openai_proxy_put</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to OpenAI-compatible inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.openai_proxy_put(
    workspace="workspace",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">openai_proxy_delete</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to OpenAI-compatible inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.openai_proxy_delete(
    workspace="workspace",
    trailing_uri="trailing_uri",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">openai_proxy_patch</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to OpenAI-compatible inference endpoints.

All inference requests must resolve to a `VirtualModel`. The platform's
provider reconciler auto-creates an implicit `autoprovisioned` VirtualModel
for every served model entity (named after the entity, with
`default_model_entity` set to the entity ref) so this is the typical case;
operators can also create custom VirtualModels for routing, plugin chains,
LoRA escape-hatches, etc. Requests for which no VirtualModel can be found
return `404`.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.openai_proxy_patch(
    workspace="workspace",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">provider_proxy_get</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to provider inference endpoints.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.provider_proxy_get(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">provider_proxy_post</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to provider inference endpoints.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.provider_proxy_post(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">provider_proxy_put</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to provider inference endpoints.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.provider_proxy_put(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">provider_proxy_delete</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to provider inference endpoints.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.provider_proxy_delete(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">provider_proxy_patch</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Proxy requests to provider inference endpoints.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.provider_proxy_patch(
    workspace="workspace",
    name="name",
    trailing_uri="trailing_uri",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**trailing_uri:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.inference_gateway.<a href="src/nvidia/inference_gateway/client.py">provider_ready</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Check if a model provider is registered in the gateway's cache.

This is a lightweight endpoint that only checks the gateway's internal state,
without making any requests to the actual provider backend. Use this to verify
the gateway is ready to route requests to a provider after deployment.

Returns:
    200 OK with provider info if the provider is registered
    404 Not Found if the provider is not yet in the gateway's cache
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.inference_gateway.provider_ready(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## VirtualModels
<details><summary><code>client.virtual_models.<a href="src/nvidia/virtual_models/client.py">list_virtual_models</a>(...) -> VirtualModelsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List VirtualModels for the given workspace.

Use ``workspace=-`` to list across all workspaces accessible to the caller.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.virtual_models.list_virtual_models(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number (1-indexed).
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Number of results per page.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[str]` — Sort field.  Prefix with ``-`` for descending order.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.virtual_models.<a href="src/nvidia/virtual_models/client.py">create_virtual_model</a>(...) -> VirtualModel</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new VirtualModel in the given workspace.

A VirtualModel defines an ordered middleware pipeline that IGW executes
when an inference request arrives with ``model: "workspace/name"`` matching
this entity.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.virtual_models.create_virtual_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Name of the virtual model within the workspace. Must be unique per workspace.
    
</dd>
</dl>

<dl>
<dd>

**default_model_entity:** `typing.Optional[str]` — Model entity to route to, in "workspace/name" format. Written into request["model"] before the request middleware pipeline runs. If omitted, a request middleware plugin must handle backend routing itself. Set to null to clear an existing value.
    
</dd>
</dl>

<dl>
<dd>

**autoprovisioned:** `typing.Optional[bool]` — Marks this VirtualModel as controller-managed. The Models controller will delete it once no ModelProvider serves the matching entity. Setting this manually opts the VirtualModel into that cleanup behavior.
    
</dd>
</dl>

<dl>
<dd>

**models:** `typing.Optional[typing.List[VirtualModelInferenceConfig]]` — Model entity references used by this VirtualModel. A per-entry backend_format overrides the referenced ModelEntity backend_format when IGW resolves the backend format for a request.
    
</dd>
</dl>

<dl>
<dd>

**request_middleware:** `typing.Optional[typing.List[MiddlewareCall]]` — Ordered list of middleware plugins applied before proxying to the backend. Each entry is a MiddlewareCall with a "name" (plugin identifier) and optional "config_type" and "config_id" fields that reference a stored plugin configuration.
    
</dd>
</dl>

<dl>
<dd>

**response_middleware:** `typing.Optional[typing.List[MiddlewareCall]]` — Ordered list of middleware plugins applied after the backend response is received, before returning it to the caller.
    
</dd>
</dl>

<dl>
<dd>

**post_response_middleware:** `typing.Optional[typing.List[MiddlewareCall]]` — Ordered list of middleware plugins invoked after the response has been returned to the caller. Intended for fire-and-forget work (logging, analytics) that must not block or modify the response.
    
</dd>
</dl>

<dl>
<dd>

**override_proxy:** `typing.Optional[str]` — Plugin-provided proxy implementation for IGW to use instead of its default aiohttp proxy. Format: "plugin-name.proxy-name". Leave unset to use the default IGW proxy. Set to null to clear an existing value.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.virtual_models.<a href="src/nvidia/virtual_models/client.py">get_virtual_model</a>(...) -> VirtualModel</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a VirtualModel by workspace and name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.virtual_models.get_virtual_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.virtual_models.<a href="src/nvidia/virtual_models/client.py">delete_virtual_model</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Permanently delete a VirtualModel.

This does not affect any in-flight requests already being routed through
this VirtualModel.  IGW's model cache is refreshed on its next polling cycle.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.virtual_models.delete_virtual_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.virtual_models.<a href="src/nvidia/virtual_models/client.py">update_virtual_model</a>(...) -> VirtualModel</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Partially update a VirtualModel.

Only fields present in the request body are modified.  Fields absent from
the request body retain their current values.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.virtual_models.update_virtual_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**default_model_entity:** `typing.Optional[str]` — Model entity to route to, in "workspace/name" format. Written into request["model"] before the request middleware pipeline runs. If omitted, a request middleware plugin must handle backend routing itself. Set to null to clear an existing value.
    
</dd>
</dl>

<dl>
<dd>

**autoprovisioned:** `typing.Optional[bool]` — Marks this VirtualModel as controller-managed. The Models controller will delete it once no ModelProvider serves the matching entity. Setting this manually opts the VirtualModel into that cleanup behavior.
    
</dd>
</dl>

<dl>
<dd>

**models:** `typing.Optional[typing.List[VirtualModelInferenceConfig]]` — Model entity references used by this VirtualModel. A per-entry backend_format overrides the referenced ModelEntity backend_format when IGW resolves the backend format for a request.
    
</dd>
</dl>

<dl>
<dd>

**request_middleware:** `typing.Optional[typing.List[MiddlewareCall]]` — Ordered list of middleware plugins applied before proxying to the backend. Each entry is a MiddlewareCall with a "name" (plugin identifier) and optional "config_type" and "config_id" fields that reference a stored plugin configuration.
    
</dd>
</dl>

<dl>
<dd>

**response_middleware:** `typing.Optional[typing.List[MiddlewareCall]]` — Ordered list of middleware plugins applied after the backend response is received, before returning it to the caller.
    
</dd>
</dl>

<dl>
<dd>

**post_response_middleware:** `typing.Optional[typing.List[MiddlewareCall]]` — Ordered list of middleware plugins invoked after the response has been returned to the caller. Intended for fire-and-forget work (logging, analytics) that must not block or modify the response.
    
</dd>
</dl>

<dl>
<dd>

**override_proxy:** `typing.Optional[str]` — Plugin-provided proxy implementation for IGW to use instead of its default aiohttp proxy. Format: "plugin-name.proxy-name". Leave unset to use the default IGW proxy. Set to null to clear an existing value.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Annotations
<details><summary><code>client.annotations.<a href="src/nvidia/annotations/client.py">list_annotations</a>(...) -> AnnotationsPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.annotations.list_annotations(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[AnnotationSortField]` 
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[AnnotationFilter]` — Filter annotations by span_id, session_id, kind, name, created_by, and created_at range.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.annotations.<a href="src/nvidia/annotations/client.py">create_annotation</a>(...) -> Annotation</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi, AnnotationInput_Feedback

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.annotations.create_annotation(
    workspace="workspace",
    request=AnnotationInput_Feedback(
        session_id="session_id",
        value="positive",
    ),
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `AnnotationInput` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.annotations.<a href="src/nvidia/annotations/client.py">get_annotation</a>(...) -> Annotation</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.annotations.get_annotation(
    workspace="workspace",
    annotation_id="annotation_id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**annotation_id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.annotations.<a href="src/nvidia/annotations/client.py">delete_annotation</a>(...)</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.annotations.delete_annotation(
    workspace="workspace",
    annotation_id="annotation_id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**annotation_id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## EvaluatorResults
<details><summary><code>client.evaluator_results.<a href="src/nvidia/evaluator_results/client.py">list_evaluator_results</a>(...) -> EvaluatorResultsPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.evaluator_results.list_evaluator_results(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[EvaluatorResultSortField]` 
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[EvaluatorResultFilter]` — Filter evaluator results by span_id, session_id, name, data_type, created_by, value range, and created_at range.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.evaluator_results.<a href="src/nvidia/evaluator_results/client.py">create_evaluator_result</a>(...) -> EvaluatorResult</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.evaluator_results.create_evaluator_result(
    workspace="workspace",
    span_id="span_id",
    session_id="session_id",
    name="name",
    data_type="NUMERIC",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**span_id:** `str` — Target span id. Not validated against existing spans (loose target policy).
    
</dd>
</dl>

<dl>
<dd>

**session_id:** `str` — Session id the target span belongs to. Denormalized so session-scoped reads stay fast.
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Evaluator / metric identity (e.g. 'faithfulness/v1').
    
</dd>
</dl>

<dl>
<dd>

**data_type:** `EvaluatorResultDataType` — Discriminator for which of value / string_value carries the payload.
    
</dd>
</dl>

<dl>
<dd>

**value:** `typing.Optional[float]` — Numeric value. Required when data_type is NUMERIC or BOOLEAN (0|1).
    
</dd>
</dl>

<dl>
<dd>

**string_value:** `typing.Optional[str]` — String value. Required when data_type is CATEGORICAL or TEXT.
    
</dd>
</dl>

<dl>
<dd>

**comment:** `typing.Optional[str]` — Free-text rationale or explanation.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.evaluator_results.<a href="src/nvidia/evaluator_results/client.py">get_evaluator_result</a>(...) -> EvaluatorResult</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.evaluator_results.get_evaluator_result(
    workspace="workspace",
    evaluator_result_id="evaluator_result_id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**evaluator_result_id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.evaluator_results.<a href="src/nvidia/evaluator_results/client.py">list_evaluator_results_for_span</a>(...) -> typing.List[EvaluatorResult]</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.evaluator_results.list_evaluator_results_for_span(
    workspace="workspace",
    span_id="span_id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**span_id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## ExperimentGroups
<details><summary><code>client.experiment_groups.<a href="src/nvidia/experiment_groups/client.py">list_experiment_groups</a>(...) -> ExperimentGroupResponsesPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiment_groups.list_experiment_groups(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[ListExperimentGroupsApisIntakeV2WorkspacesWorkspaceExperimentGroupsGetRequestSort]` — Sort field; prefix with '-' for descending.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[ExperimentGroupFilter]` — Filter experiment groups by name.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiment_groups.<a href="src/nvidia/experiment_groups/client.py">create_experiment_group</a>(...) -> ExperimentGroupResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiment_groups.create_experiment_group(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `ExperimentGroupRequest` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiment_groups.<a href="src/nvidia/experiment_groups/client.py">get_experiment_group</a>(...) -> ExperimentGroupResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiment_groups.get_experiment_group(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiment_groups.<a href="src/nvidia/experiment_groups/client.py">update_experiment_group</a>(...) -> ExperimentGroupResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiment_groups.update_experiment_group(
    workspace="workspace",
    name_="name",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `ExperimentGroupRequest` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiment_groups.<a href="src/nvidia/experiment_groups/client.py">delete_experiment_group</a>(...)</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiment_groups.delete_experiment_group(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Experiments
<details><summary><code>client.experiments.<a href="src/nvidia/experiments/client.py">list_experiments</a>(...) -> ExperimentResponsesPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiments.list_experiments(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[ListExperimentsApisIntakeV2WorkspacesWorkspaceExperimentsGetRequestSort]` — Sort field; prefix with '-' for descending.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[ExperimentFilter]` — Filter experiments by name, experiment_group_id, agent_name, agent_version, dataset_name, dataset_version, created_by, created_at, or updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiments.<a href="src/nvidia/experiments/client.py">create_experiment</a>(...) -> ExperimentResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiments.create_experiment(
    workspace="workspace",
    name="name",
    agent_name="agent_name",
    agent_version="agent_version",
    dataset_name="dataset_name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `ExperimentRequest` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiments.<a href="src/nvidia/experiments/client.py">get_experiment</a>(...) -> ExperimentResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiments.get_experiment(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiments.<a href="src/nvidia/experiments/client.py">update_experiment</a>(...) -> ExperimentResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiments.update_experiment(
    workspace="workspace",
    name_="name",
    name="name",
    agent_name="agent_name",
    agent_version="agent_version",
    dataset_name="dataset_name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `ExperimentRequest` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiments.<a href="src/nvidia/experiments/client.py">delete_experiment</a>(...)</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiments.delete_experiment(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.experiments.<a href="src/nvidia/experiments/client.py">list_experiment_sessions</a>(...) -> ExperimentSessionResponsesPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.experiments.list_experiment_sessions(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[ExperimentSessionFilter]` — Filter sessions by test_case_id and status.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Ingest
<details><summary><code>client.ingest.<a href="src/nvidia/ingest/client.py">ingest_atif</a>(...)</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi, AtifAgent

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.ingest.ingest_atif(
    workspace="workspace",
    schema_version="ATIF-v1.0",
    agent=AtifAgent(
        name="name",
        version="version",
    ),
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**schema_version:** `AtifIngestRequestSchemaVersion` 
    
</dd>
</dl>

<dl>
<dd>

**agent:** `AtifAgent` 
    
</dd>
</dl>

<dl>
<dd>

**experiment_context:** `typing.Optional[ExperimentContext]` 
    
</dd>
</dl>

<dl>
<dd>

**evaluation_context:** `typing.Optional[EvaluationContext]` — Deprecated. Use experiment_context; when both are sent, experiment_context takes precedence.
    
</dd>
</dl>

<dl>
<dd>

**session_id:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**final_metrics:** `typing.Optional[AtifFinalMetrics]` 
    
</dd>
</dl>

<dl>
<dd>

**continued_trajectory_ref:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**notes:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**extra:** `typing.Optional[typing.Dict[str, typing.Any]]` 
    
</dd>
</dl>

<dl>
<dd>

**steps:** `typing.Optional[typing.List[AtifStep]]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.ingest.<a href="src/nvidia/ingest/client.py">ingest_chat_completion</a>(...) -> ChatCompletionsIngestResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi, CapturedChatCompletionsRequest, CapturedChatMessage

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.ingest.ingest_chat_completion(
    workspace="workspace",
    request=CapturedChatCompletionsRequest(
        messages=[
            CapturedChatMessage(
                role="user",
            ),
            CapturedChatMessage(
                role="user",
            )
        ],
        model="model",
    ),
    response={"key": "value"},
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `CapturedChatCompletionsRequest` 
    
</dd>
</dl>

<dl>
<dd>

**response:** `CapturedChatCompletionsResponse` 
    
</dd>
</dl>

<dl>
<dd>

**experiment_context:** `typing.Optional[ExperimentContext]` 
    
</dd>
</dl>

<dl>
<dd>

**evaluation_context:** `typing.Optional[EvaluationContext]` — Deprecated. Use experiment_context; when both are sent, experiment_context takes precedence.
    
</dd>
</dl>

<dl>
<dd>

**session_id:** `typing.Optional[str]` — Groups related chat-completions calls without forcing them into the same trace.
    
</dd>
</dl>

<dl>
<dd>

**trace_id:** `typing.Optional[str]` — Opt into joining an existing trace built via OTel or ATIF. This is not a grouping mechanism for chat-completions calls; use session_id to group related calls.
    
</dd>
</dl>

<dl>
<dd>

**provider:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**cost_usd:** `typing.Optional[float]` — Total estimated cost of this model call in USD. This matches ATIF step metrics; Intake stores it as semantic cost_total_usd on spans.
    
</dd>
</dl>

<dl>
<dd>

**cost_input_usd:** `typing.Optional[float]` — Estimated input-token cost of this model call in USD.
    
</dd>
</dl>

<dl>
<dd>

**cost_output_usd:** `typing.Optional[float]` — Estimated output-token cost of this model call in USD.
    
</dd>
</dl>

<dl>
<dd>

**cost_details:** `typing.Optional[typing.Dict[str, float]]` — Additional estimated cost breakdown fields in USD.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.ingest.<a href="src/nvidia/ingest/client.py">ingest_otlp_traces</a>(...) -> IngestResponse</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.ingest.ingest_otlp_traces(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Spans
<details><summary><code>client.spans.<a href="src/nvidia/spans/client.py">list_spans</a>(...) -> SpansPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.spans.list_spans(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[SpanSortField]` 
    
</dd>
</dl>

<dl>
<dd>

**mode:** `typing.Optional[ListSpansApisIntakeV2WorkspacesWorkspaceSpansGetRequestMode]` 
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[SpanFilter]` — Filter spans by session_id, trace_id, parent_span_id, project, evaluation context fields, source, kind, status, model, tool_name, provider, agent_id, agent_name, prompt_name, prompt_version, and started_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.spans.<a href="src/nvidia/spans/client.py">get_span</a>(...) -> Span</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.spans.get_span(
    workspace="workspace",
    span_id="span_id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**span_id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Traces
<details><summary><code>client.traces.<a href="src/nvidia/traces/client.py">list_traces</a>(...) -> TracesPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.traces.list_traces(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[TraceSortField]` 
    
</dd>
</dl>

<dl>
<dd>

**mode:** `typing.Optional[ListTracesApisIntakeV2WorkspacesWorkspaceTracesGetRequestMode]` — Use summary for root-span trace fields only, or detailed to include token, cost, and span-count rollups.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[TraceFilter]` — Filter root-span-backed traces by id, session_id, rolled-up status, root span started_at, and root-span evaluation context fields.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.traces.<a href="src/nvidia/traces/client.py">get_trace</a>(...) -> Trace</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.traces.get_trace(
    workspace="workspace",
    id="id",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**id:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**mode:** `typing.Optional[GetTraceApisIntakeV2WorkspacesWorkspaceTracesIdGetRequestMode]` — Use summary for root-span trace fields only, or detailed to include token, cost, and span-count rollups.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Jobs
<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">get_execution_profiles</a>() -> typing.List[GetExecutionProfilesApisJobsV2ExecutionProfilesGetResponseItem]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get all currently configured execution profiles.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.get_execution_profiles()

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">list_jobs</a>(...) -> PlatformJobResponsesPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List platform jobs with filtering and pagination.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.list_jobs(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[PlatformJobSortField]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[PlatformJobsListFilter]` — Filter jobs by workspace, project, name, status, source, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">create_job</a>(...) -> PlatformJobResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi, PlatformJobSpecInput, PlatformJobStepSpecInput, PlatformJobStepSpecInputExecutor_Cpu, ContainerSpec

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.create_job(
    workspace="workspace",
    spec={
        "key": "value"
    },
    platform_spec=PlatformJobSpecInput(
        steps=[
            PlatformJobStepSpecInput(
                name="preprocess",
                executor=PlatformJobStepSpecInputExecutor_Cpu(
                    container=ContainerSpec(
                        image="image",
                    ),
                ),
            )
        ],
    ),
    source="source",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**spec:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**platform_spec:** `PlatformJobSpecInput` 
    
</dd>
</dl>

<dl>
<dd>

**source:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**ownership:** `typing.Optional[typing.Dict[str, typing.Any]]` 
    
</dd>
</dl>

<dl>
<dd>

**custom_fields:** `typing.Optional[typing.Dict[str, typing.Any]]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">get_job_result</a>(...) -> PlatformJobResultResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific job result.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.get_job_result(
    workspace="workspace",
    job="job",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">create_job_result</a>(...) -> PlatformJobResultResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new result for a job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.create_job_result(
    workspace="workspace",
    job="job",
    name="name",
    artifact_url="artifact_url",
    artifact_storage_type="fileset",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**artifact_url:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**artifact_storage_type:** `FileStorageType` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">download_job_result</a>(...) -> typing.Iterator[bytes]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Download a job result file.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.download_job_result(
    workspace="workspace",
    job="job",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">get_job_step</a>(...) -> PlatformJobStep</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific job step.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.get_job_step(
    workspace="workspace",
    job="job",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">update_job_step_status</a>(...) -> PlatformJobStep</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update a job step status.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.update_job_step_status(
    workspace="workspace",
    job="job",
    name="name",
    status="created",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**status:** `PlatformJobStatus` — The new status to set for the job.
    
</dd>
</dl>

<dl>
<dd>

**status_details:** `typing.Optional[typing.Dict[str, typing.Any]]` — Optional status details related to the status update.
    
</dd>
</dl>

<dl>
<dd>

**error_details:** `typing.Optional[typing.Dict[str, typing.Any]]` — Optional error details related to the status update.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">list_job_step_tasks</a>(...) -> PlatformJobListTaskResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List tasks for a job step.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.list_job_step_tasks(
    workspace="workspace",
    job="job",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">get_job_step_task</a>(...) -> PlatformJobTask</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific job step task.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.get_job_step_task(
    workspace="workspace",
    job="job",
    step="step",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**step:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">update_job_step_task</a>(...) -> PlatformJobTask</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update a job step task.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.update_job_step_task(
    workspace="workspace",
    job="job",
    step="step",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**job:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**step:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**status:** `typing.Optional[PlatformJobStatus]` 
    
</dd>
</dl>

<dl>
<dd>

**status_details:** `typing.Optional[typing.Dict[str, typing.Any]]` 
    
</dd>
</dl>

<dl>
<dd>

**error_details:** `typing.Optional[typing.Dict[str, typing.Any]]` 
    
</dd>
</dl>

<dl>
<dd>

**error_stack:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">get_job</a>(...) -> PlatformJobResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a platform job by name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.get_job(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">delete_job</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.delete_job(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">cancel_job</a>(...) -> PlatformJobResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Cancel a platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.cancel_job(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">page_job_logs</a>(...) -> PlatformJobLogPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get paginated logs for a platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.page_job_logs(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**limit:** `typing.Optional[int]` — Maximum number of logs to return
    
</dd>
</dl>

<dl>
<dd>

**page_cursor:** `typing.Optional[str]` — Page cursor
    
</dd>
</dl>

<dl>
<dd>

**attempt_id:** `typing.Optional[int]` — Filter logs by job attempt ID
    
</dd>
</dl>

<dl>
<dd>

**step_id:** `typing.Optional[str]` — Filter logs by step name
    
</dd>
</dl>

<dl>
<dd>

**task_id:** `typing.Optional[str]` — Filter logs by task ID
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">pause_job</a>(...) -> PlatformJobResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Pause a platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.pause_job(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">list_job_results</a>(...) -> PlatformJobListResultResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List results for a job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.list_job_results(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[PlatformJobSortField]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">resume_job</a>(...) -> PlatformJobResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Resume a paused platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.resume_job(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">get_job_status</a>(...) -> PlatformJobStatusResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get the status of a platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.get_job_status(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">update_job_status_details</a>(...) -> typing.Any</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update the status details of a platform job.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.update_job_status_details(
    workspace="workspace",
    name="name",
    request={
        "key": "value"
    },
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `typing.Dict[str, typing.Any]` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.jobs.<a href="src/nvidia/jobs/client.py">list_steps</a>(...) -> PlatformJobStepWithContextsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List job steps with pagination and filtering.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.jobs.list_steps(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[PlatformJobSortField]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[PlatformJobStepsListFilter]` — Filter steps by job, status, and source.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Adapters
<details><summary><code>client.adapters.<a href="src/nvidia/adapters/client.py">list_adapters</a>(...) -> AdaptersPage</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.adapters.list_adapters(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[str]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[AdapterEntityFilter]` — Filter adapters by name, model (parent model ref string, stored on the adapter), description, fileset, finetuning_type, enabled, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.adapters.<a href="src/nvidia/adapters/client.py">create_adapter</a>(...) -> Adapter</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create an adapter under a base model specified by the "model" field in the body.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.adapters.create_adapter(
    workspace="workspace",
    name="lora-adapter-v1",
    fileset="fileset",
    finetuning_type="lora_merged",
    model="llama-3-8b-instruct",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Name of the adapter. Name must be unique in the workspace. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**fileset:** `str` — Location where adapter files are stored - expected format {workspace}/{fileset_name}
    
</dd>
</dl>

<dl>
<dd>

**finetuning_type:** `FinetuningType` — Type of finetuning (LORA, P_TUNING, etc.)
    
</dd>
</dl>

<dl>
<dd>

**model:** `str` 

Base model entity.
            Use `{workspace}/{model_name}` to reference a model in any workspace, or a single `{model_name}` resolved in the path workspace. A single name (2-63 characters) or 'workspace/model_name' where each segment is a valid name (lowercase, digits, hyphens, and temporarily @ . + _; no leading/trailing or consecutive hyphens). If one slash, both sides must be non-empty.
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the adapter
    
</dd>
</dl>

<dl>
<dd>

**enabled:** `typing.Optional[bool]` — Whether to make this adapter available for inference post training
    
</dd>
</dl>

<dl>
<dd>

**lora_config:** `typing.Optional[Lora]` — Lora configuration specifics
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.adapters.<a href="src/nvidia/adapters/client.py">get_adapter</a>(...) -> Adapter</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.adapters.get_adapter(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.adapters.<a href="src/nvidia/adapters/client.py">delete_adapter</a>(...)</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.adapters.delete_adapter(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.adapters.<a href="src/nvidia/adapters/client.py">update_adapter</a>(...) -> Adapter</code></summary>
<dl>
<dd>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.adapters.update_adapter(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `UpdateAdapterRequest` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## ModelDeploymentConfigs
<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">list_deployment_configs</a>(...) -> ModelDeploymentConfigsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List ModelDeploymentConfigs for a specific workspace.
Returns only the latest version of each config.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.list_deployment_configs(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[str]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[ModelDeploymentConfigFilter]` — Filter deployment configs by workspace, project, model_entity_id, name, description, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">create_deployment_config</a>(...) -> ModelDeploymentConfig</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new ModelDeploymentConfig (version 1).
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi, ModelDeploymentConfigModelSpec, ContainerExecutorConfig

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.create_deployment_config(
    workspace="workspace",
    name="nim-config-v1",
    engine="nim",
    model_spec=ModelDeploymentConfigModelSpec(),
    executor_config=ContainerExecutorConfig(
        gpu=1,
    ),
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Name of the deployment configuration. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**engine:** `Engine` — Inference engine selecting the compiler path (nim/vllm/generic)
    
</dd>
</dl>

<dl>
<dd>

**model_spec:** `ModelDeploymentConfigModelSpec` — What model to serve and how -- independent of the executor it runs on
    
</dd>
</dl>

<dl>
<dd>

**executor_config:** `ContainerExecutorConfig` — Compute + container settings for the executor the deployment runs on
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The URN of the project associated with this deployment configuration
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the deployment configuration
    
</dd>
</dl>

<dl>
<dd>

**model_entity_id:** `typing.Optional[str]` — Optional reference to the base model entity ID for this deployment
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">get_deployment_config_version</a>(...) -> ModelDeploymentConfig</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific version of a ModelDeploymentConfig.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.get_deployment_config_version(
    workspace="workspace",
    config="config",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**config:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">delete_deployment_config_version</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a specific version of a ModelDeploymentConfig.

This operation will fail with 409 Conflict if any ModelDeployments currently
reference this specific version and are not in DELETED status. Delete or wait for
dependent deployments to reach DELETED status before deleting the config version.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.delete_deployment_config_version(
    workspace="workspace",
    config="config",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**config:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">get_latest_deployment_config</a>(...) -> ModelDeploymentConfig</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get the latest version of a ModelDeploymentConfig.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.get_latest_deployment_config(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">update_deployment_config</a>(...) -> ModelDeploymentConfig</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update a ModelDeploymentConfig (creates a new immutable version).
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi, ModelDeploymentConfigModelSpec, ContainerExecutorConfig

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.update_deployment_config(
    workspace="workspace",
    name="name",
    engine="nim",
    model_spec=ModelDeploymentConfigModelSpec(),
    executor_config=ContainerExecutorConfig(
        gpu=1,
    ),
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**engine:** `Engine` — Inference engine selecting the compiler path (nim/vllm/generic)
    
</dd>
</dl>

<dl>
<dd>

**model_spec:** `ModelDeploymentConfigModelSpec` — What model to serve and how -- independent of the executor it runs on
    
</dd>
</dl>

<dl>
<dd>

**executor_config:** `ContainerExecutorConfig` — Compute + container settings for the executor the deployment runs on
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the deployment configuration
    
</dd>
</dl>

<dl>
<dd>

**model_entity_id:** `typing.Optional[str]` — Optional reference to the base model entity ID for this deployment
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">delete_all_deployment_config_versions</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete all versions of a ModelDeploymentConfig.

This operation will fail with 409 Conflict if any ModelDeployments currently
reference this config and are not in DELETED status. Delete or wait for
dependent deployments to reach DELETED status before deleting the config.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.delete_all_deployment_config_versions(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployment_configs.<a href="src/nvidia/model_deployment_configs/client.py">list_deployment_config_versions</a>(...) -> typing.List[ModelDeploymentConfig]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List all versions of a ModelDeploymentConfig.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployment_configs.list_deployment_config_versions(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## ModelDeployments
<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">list_deployments</a>(...) -> ModelDeploymentsPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List ModelDeployments for a specific workspace.

By default, returns only the latest version of each deployment.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.list_deployments(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[str]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**all_versions:** `typing.Optional[bool]` — If true, return all versions of each deployment. If false (default), return only the latest version.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[ModelDeploymentFilter]` — Filter deployments by workspace, project, status, config, model_provider_id, name, status_message, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">create_deployment</a>(...) -> ModelDeployment</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new ModelDeployment (version 1).
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.create_deployment(
    workspace="workspace",
    name="llama-deploy-v1",
    config="config",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Name of the deployment. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**config:** `str` — Reference to the ModelDeploymentConfig name
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The URN of the project associated with this deployment
    
</dd>
</dl>

<dl>
<dd>

**config_version:** `typing.Optional[int]` — Reference to a specific ModelDeploymentConfig version. If not specified, uses latest.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">get_deployment_version</a>(...) -> ModelDeployment</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a specific version of a ModelDeployment.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.get_deployment_version(
    workspace="workspace",
    deployment="deployment",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**deployment:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">delete_deployment_version</a>(...) -> typing.Optional[typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a specific version of a ModelDeployment.

If the deployment is in any state other than DELETED, this will set its status to DELETING.
The models controller will then:
1. Delete the infrastructure (e.g., K8s NimService)
2. Update the status to DELETED

If the deployment is already in DELETED status, calling delete again will permanently
remove it from the database.

Returns:
- 202 Accepted: Deployment version marked for deletion (status set to DELETING)
- 204 No Content: Deployment version permanently removed from database (was already DELETED)
- 404 Not Found: Deployment version doesn't exist
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.delete_deployment_version(
    workspace="workspace",
    deployment="deployment",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**deployment:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">get_latest_deployment</a>(...) -> ModelDeployment</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get the latest version of a ModelDeployment.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.get_latest_deployment(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">update_deployment</a>(...) -> ModelDeployment</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update a ModelDeployment (creates a new immutable version).
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.update_deployment(
    workspace="workspace",
    name="name",
    config="config",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**config:** `str` — Reference to the ModelDeploymentConfig name
    
</dd>
</dl>

<dl>
<dd>

**config_version:** `typing.Optional[int]` — Reference to a specific ModelDeploymentConfig version. If not specified, uses latest.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">delete_all_deployment_versions</a>(...) -> typing.Optional[typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete all versions of a ModelDeployment.

If the deployment is in any state other than DELETED, this will set its status to DELETING.
The models controller will then:
1. Delete the infrastructure (e.g., K8s NimService)
2. Update the status to DELETED

If the deployment is already in DELETED status, calling delete again will permanently
remove it from the database.

Returns:
- 202 Accepted: Deployment marked for deletion (status set to DELETING)
- 204 No Content: Deployment permanently removed from database (was already DELETED)
- 404 Not Found: Deployment doesn't exist
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.delete_all_deployment_versions(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">get_deployment_models</a>(...) -> typing.Dict[str, typing.Any]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get Latest ModelDeployment's Model Entities from Entity Store.
This provides the API contract that NIMs expect from Entity Store today, for pulling LoRAs,
but enables us to enforce AuthZ boundaries.

TODO: Implement model entity retrieval based on deployment config.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.get_deployment_models(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">update_deployment_status</a>(...) -> ModelDeployment</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update the status of a ModelDeployment (mutable operation).
If version is not specified, updates the latest version.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.update_deployment_status(
    workspace="workspace",
    name="name",
    status="UNKNOWN",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**status:** `ModelDeploymentStatus` — New status for the deployment
    
</dd>
</dl>

<dl>
<dd>

**version:** `typing.Optional[str]` 
    
</dd>
</dl>

<dl>
<dd>

**status_message:** `typing.Optional[str]` — Detailed status message
    
</dd>
</dl>

<dl>
<dd>

**model_provider_id:** `typing.Optional[str]` — Optional reference to the auto-created ModelProvider workspace/name (format: workspace/name)
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_deployments.<a href="src/nvidia/model_deployments/client.py">list_deployment_versions</a>(...) -> typing.List[ModelDeployment]</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List all versions of a ModelDeployment.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_deployments.list_deployment_versions(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Models
<details><summary><code>client.models.<a href="src/nvidia/models/client.py">list_models</a>(...) -> ModelEntitysPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List Models endpoint with filtering, pagination, and sorting.

Supports filter parameters for various criteria (including peft, custom fields),
pagination (page, page_size), sorting, and workspace filtering via query parameter.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.list_models(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[ModelEntitySortField]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**verbose:** `typing.Optional[bool]` — Whether to include full spec details
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[ModelEntityFilter]` — Filter models by name, project, workspace, base_model, adapters, finetuning_type, prompt, lora_enabled, description, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.models.<a href="src/nvidia/models/client.py">create_model</a>(...) -> ModelEntity</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new model entity.

This endpoint creates a new Model Entity in the Models service database.
The Model Entity will be registered for use within the platform.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.create_model(
    workspace="workspace",
    name="llama-3.1-8b",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Name of the model entity. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The URN of the project associated with this model entity
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the model
    
</dd>
</dl>

<dl>
<dd>

**spec:** `typing.Optional[ModelSpec]` — Detailed specification for the model - Automatically generated by the platform at creation when fileset provided.
    
</dd>
</dl>

<dl>
<dd>

**finetuning_type:** `typing.Optional[FinetuningType]` — Set for full weight finetuned models
    
</dd>
</dl>

<dl>
<dd>

**fileset:** `typing.Optional[str]` — A set of checkpoint files, configs, and other auxiliary info associated with this model - expected format {workspace}/{fileset_name}
    
</dd>
</dl>

<dl>
<dd>

**base_model:** `typing.Optional[str]` — Link to another model which is used as a base for the current model
    
</dd>
</dl>

<dl>
<dd>

**api_endpoint:** `typing.Optional[ApiEndpointData]` — Data about the inference endpoint for this model
    
</dd>
</dl>

<dl>
<dd>

**backend_format:** `typing.Optional[BackendFormat]` — Inference API wire format expected by the backend. If unset, inference routing treats the model as OPENAI_CHAT.
    
</dd>
</dl>

<dl>
<dd>

**prompt:** `typing.Optional[PromptData]` — Configuration for prompt engineering
    
</dd>
</dl>

<dl>
<dd>

**custom_fields:** `typing.Optional[typing.Dict[str, typing.Any]]` — Custom fields for additional metadata
    
</dd>
</dl>

<dl>
<dd>

**ownership:** `typing.Optional[typing.Dict[str, typing.Any]]` — Ownership information for the model
    
</dd>
</dl>

<dl>
<dd>

**model_providers:** `typing.Optional[typing.List[str]]` — List of ModelProvider workspace/name resource names that provide inference for this Model Entity
    
</dd>
</dl>

<dl>
<dd>

**trust_remote_code:** `typing.Optional[bool]` 

Whether to trust remote code for the checkpoint.
        Some models without support in certain libraries such as Transformers require additional custom Python code to execute.
        Due to security ramifications of running arbitrary code, this can only be set to true on one of the following conditions:
        (1) the model's fileset's source is pre-approved in the platform config, or
        (2) the user creating this model is an administrator.
        
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.models.<a href="src/nvidia/models/client.py">create_model_adapter</a>(...) -> Adapter</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Adds an Adapter to the Model
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.create_model_adapter(
    workspace="workspace",
    model_name="model_name",
    name="lora-adapter-v1",
    fileset="fileset",
    finetuning_type="lora_merged",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**model_name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Name of the adapter. Name must be unique in the workspace. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**fileset:** `str` — Location where adapter files are stored - expected format {workspace}/{fileset_name}
    
</dd>
</dl>

<dl>
<dd>

**finetuning_type:** `FinetuningType` — Type of finetuning (LORA, P_TUNING, etc.)
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the adapter
    
</dd>
</dl>

<dl>
<dd>

**enabled:** `typing.Optional[bool]` — Whether to make this adapter available for inference post training
    
</dd>
</dl>

<dl>
<dd>

**lora_config:** `typing.Optional[Lora]` — Lora configuration specifics
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.models.<a href="src/nvidia/models/client.py">delete_model_adapter</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete Adapter from Model entity.

Permanently deletes an adapter from a model entity, if it was deployed, it will be cleaned up automatically.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.delete_model_adapter(
    workspace="workspace",
    model_name="model_name",
    adapter="adapter",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**model_name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**adapter:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.models.<a href="src/nvidia/models/client.py">update_model_adapter</a>(...) -> Adapter</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update Adapter deployment or description.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.update_model_adapter(
    workspace="workspace",
    model_name="model_name",
    adapter="adapter",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**model_name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**adapter:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request:** `UpdateAdapterRequest` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.models.<a href="src/nvidia/models/client.py">get_model</a>(...) -> ModelEntity</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get Model by Workspace and Name.

Returns the details of a specific model entity identified by its workspace and name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.get_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**verbose:** `typing.Optional[bool]` — Whether to include full spec details
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.models.<a href="src/nvidia/models/client.py">delete_model</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete Model entity.

Permanently deletes a model entity from the platform.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.delete_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.models.<a href="src/nvidia/models/client.py">update_model</a>(...) -> ModelEntity</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update Model metadata.

Updates the metadata of an existing model entity. If the request body has an empty field,
the old value is kept.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.models.update_model(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**verbose:** `typing.Optional[bool]` — Whether to include full spec details
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the model
    
</dd>
</dl>

<dl>
<dd>

**spec:** `typing.Optional[ModelSpec]` — Detailed specification for the model
    
</dd>
</dl>

<dl>
<dd>

**fileset:** `typing.Optional[str]` — A set of checkpoint files, configs, and other auxiliary info associated with this model - expected format {workspace}/{fileset_name}
    
</dd>
</dl>

<dl>
<dd>

**finetuning_type:** `typing.Optional[FinetuningType]` — Set for full weight finetuned models
    
</dd>
</dl>

<dl>
<dd>

**base_model:** `typing.Optional[str]` — Link to another model which is used as a base for the current model
    
</dd>
</dl>

<dl>
<dd>

**api_endpoint:** `typing.Optional[ApiEndpointData]` — Data about the inference endpoint for this model
    
</dd>
</dl>

<dl>
<dd>

**backend_format:** `typing.Optional[BackendFormat]` — Inference API wire format expected by the backend. If unset, inference routing treats the model as OPENAI_CHAT.
    
</dd>
</dl>

<dl>
<dd>

**prompt:** `typing.Optional[PromptData]` — Configuration for prompt engineering
    
</dd>
</dl>

<dl>
<dd>

**custom_fields:** `typing.Optional[typing.Dict[str, typing.Any]]` — Custom fields for additional metadata
    
</dd>
</dl>

<dl>
<dd>

**ownership:** `typing.Optional[typing.Dict[str, typing.Any]]` — Ownership information for the model
    
</dd>
</dl>

<dl>
<dd>

**model_providers:** `typing.Optional[typing.List[str]]` — List of ModelProvider workspace/name resource names that provide inference for this Model Entity
    
</dd>
</dl>

<dl>
<dd>

**trust_remote_code:** `typing.Optional[bool]` 

Whether to trust remote code for the checkpoint.
        Some models without support in certain libraries such as Transformers require additional custom Python code to execute.
        Due to security ramifications of running arbitrary code, this can only be set to true on one of the following conditions:
        (1) the model's fileset's source is pre-approved in the platform config, or
        (2) the user creating this model is an administrator.
        
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## ModelProviders
<details><summary><code>client.model_providers.<a href="src/nvidia/model_providers/client.py">list_providers</a>(...) -> ModelProvidersPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List model providers for a specific workspace.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_providers.list_providers(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**sort:** `typing.Optional[ModelProviderSort]` — The field to sort by. To sort in decreasing order, use `-` in front of the field name.
    
</dd>
</dl>

<dl>
<dd>

**filter:** `typing.Optional[ModelProviderFilter]` — Filter model providers by workspace, project, status, model_deployment_id, name, description, host_url, created_at, and updated_at.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_providers.<a href="src/nvidia/model_providers/client.py">create_provider</a>(...) -> ModelProvider</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new model provider.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_providers.create_provider(
    workspace="workspace",
    name="my-nim-provider",
    host_url="host_url",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — Name of the model provider. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**host_url:** `str` — The network endpoint URL for the model provider
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The URN of the project associated with this model provider
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the model provider
    
</dd>
</dl>

<dl>
<dd>

**api_key_secret_name:** `typing.Optional[str]` — Reference to an API key secret stored in the Secrets service. Create the secret first via secrets API, then pass the secret name here.
    
</dd>
</dl>

<dl>
<dd>

**enabled_models:** `typing.Optional[typing.List[str]]` — Optional list of specific models to enable from this provider
    
</dd>
</dl>

<dl>
<dd>

**default_extra_body:** `typing.Optional[typing.Dict[str, typing.Any]]` — Default body parameters for inference requests. Can be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**default_extra_headers:** `typing.Optional[typing.Dict[str, str]]` — Default headers for inference requests. Can be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**required_extra_body:** `typing.Optional[typing.Dict[str, typing.Any]]` — Required body parameters for inference requests. Cannot be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**required_extra_headers:** `typing.Optional[typing.Dict[str, str]]` — Required headers for inference requests. Cannot be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**model_deployment_id:** `typing.Optional[str]` — Optional reference to the ModelDeployment ID if this provider is being auto-created for a deployment
    
</dd>
</dl>

<dl>
<dd>

**status:** `typing.Optional[ModelProviderStatus]` — Status of the model provider
    
</dd>
</dl>

<dl>
<dd>

**status_message:** `typing.Optional[str]` — Status message
    
</dd>
</dl>

<dl>
<dd>

**auth_header_format:** `typing.Optional[str]` — Jinja2 template string controlling how the API key secret is sent to the upstream. Must contain exactly one variable named `auth_secret`, which is substituted with the resolved secret value at request time. Example: `'X-Api-Key: {{ auth_secret }}'`. If not set, defaults to `'Authorization: Bearer {{ auth_secret }}'`.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_providers.<a href="src/nvidia/model_providers/client.py">get_provider</a>(...) -> ModelProvider</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Get a model provider by workspace and name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_providers.get_provider(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_providers.<a href="src/nvidia/model_providers/client.py">upsert_provider</a>(...) -> ModelProvider</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create or update a model provider.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_providers.upsert_provider(
    workspace="workspace",
    name="name",
    host_url="host_url",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**host_url:** `str` — The network endpoint URL for the model provider
    
</dd>
</dl>

<dl>
<dd>

**project:** `typing.Optional[str]` — The URN of the project associated with this model provider
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — Optional description of the model provider
    
</dd>
</dl>

<dl>
<dd>

**api_key_secret_name:** `typing.Optional[str]` — Reference to an API key secret stored in the Secrets service. Create the secret first via secrets API, then pass the secret name here.
    
</dd>
</dl>

<dl>
<dd>

**enabled_models:** `typing.Optional[typing.List[str]]` — Optional list of specific models to enable from this provider
    
</dd>
</dl>

<dl>
<dd>

**default_extra_body:** `typing.Optional[typing.Dict[str, typing.Any]]` — Default body parameters for inference requests. Can be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**default_extra_headers:** `typing.Optional[typing.Dict[str, str]]` — Default headers for inference requests. Can be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**required_extra_body:** `typing.Optional[typing.Dict[str, typing.Any]]` — Required body parameters for inference requests. Cannot be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**required_extra_headers:** `typing.Optional[typing.Dict[str, str]]` — Required headers for inference requests. Cannot be overridden by user requests.
    
</dd>
</dl>

<dl>
<dd>

**model_deployment_id:** `typing.Optional[str]` — Optional reference to the ModelDeployment ID if this provider is associated with a deployment
    
</dd>
</dl>

<dl>
<dd>

**status:** `typing.Optional[ModelProviderStatus]` — Status of the model provider
    
</dd>
</dl>

<dl>
<dd>

**status_message:** `typing.Optional[str]` — Status message
    
</dd>
</dl>

<dl>
<dd>

**auth_header_format:** `typing.Optional[str]` — Jinja2 template string controlling how the API key secret is sent to the upstream. Must contain exactly one variable named `auth_secret`, which is substituted with the resolved secret value at request time. Example: `'X-Api-Key: {{ auth_secret }}'`. If not set, defaults to `'Authorization: Bearer {{ auth_secret }}'`.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_providers.<a href="src/nvidia/model_providers/client.py">delete_provider</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a model provider by workspace and name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_providers.delete_provider(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.model_providers.<a href="src/nvidia/model_providers/client.py">update_provider_status</a>(...) -> ModelProvider</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update status-related fields of a model provider.

This endpoint supports partial updates for fields managed by Models Controller:
- model_deployment_id
- served_models
- status
- status_message

If status is provided without status_message, status_message will be set to empty string.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.model_providers.update_provider_status(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**model_deployment_id:** `typing.Optional[str]` — Reference to the ModelDeployment ID if this provider is associated with a deployment
    
</dd>
</dl>

<dl>
<dd>

**served_models:** `typing.Optional[typing.List[ServedModelMapping]]` — List of models served by this provider with routing information for IGW
    
</dd>
</dl>

<dl>
<dd>

**status:** `typing.Optional[ModelProviderStatus]` — Status of the model provider
    
</dd>
</dl>

<dl>
<dd>

**status_message:** `typing.Optional[str]` — Status message. If status is provided without status_message, defaults to empty string.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## SecretsAdmin
<details><summary><code>client.secrets_admin.<a href="src/nvidia/secrets_admin/client.py">admin_rotate_encryption_keys</a>() -> PlatformSecretAdminRotationResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Rotate encryption keys for all platform secrets.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.secrets_admin.admin_rotate_encryption_keys()

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

## Secrets
<details><summary><code>client.secrets.<a href="src/nvidia/secrets/client.py">list_secrets</a>(...) -> PlatformSecretResponsesPage</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

List available secrets
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.secrets.list_secrets(
    workspace="workspace",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**page:** `typing.Optional[int]` — Page number.
    
</dd>
</dl>

<dl>
<dd>

**page_size:** `typing.Optional[int]` — Page size.
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.secrets.<a href="src/nvidia/secrets/client.py">create_secret</a>(...) -> PlatformSecretResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Create a new secret.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.secrets.create_secret(
    workspace="workspace",
    name="hf-token",
    value="value",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` — The name of the secret to create. Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots.
    
</dd>
</dl>

<dl>
<dd>

**value:** `str` — The payload of the secret
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — An optional description of the secret
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.secrets.<a href="src/nvidia/secrets/client.py">get_secret</a>(...) -> PlatformSecretResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Retrieve a secret by its name.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.secrets.get_secret(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.secrets.<a href="src/nvidia/secrets/client.py">delete_secret</a>(...)</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Delete a secret.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.secrets.delete_secret(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.secrets.<a href="src/nvidia/secrets/client.py">update_secret</a>(...) -> PlatformSecretResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Update a secret's metadata.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.secrets.update_secret(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**description:** `typing.Optional[str]` — An optional description of the secret
    
</dd>
</dl>

<dl>
<dd>

**value:** `typing.Optional[str]` — The new secret value
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

<details><summary><code>client.secrets.<a href="src/nvidia/secrets/client.py">access_secret</a>(...) -> PlatformSecretAccessResponse</code></summary>
<dl>
<dd>

#### 📝 Description

<dl>
<dd>

<dl>
<dd>

Access the value of a secret.
</dd>
</dl>
</dd>
</dl>

#### 🔌 Usage

<dl>
<dd>

<dl>
<dd>

```python
from nvidia import NvidiaApi

client = NvidiaApi(
    base_url="https://yourhost.com/path/to/api",
)

client.secrets.access_secret(
    workspace="workspace",
    name="name",
)

```
</dd>
</dl>
</dd>
</dl>

#### ⚙️ Parameters

<dl>
<dd>

<dl>
<dd>

**workspace:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**name:** `str` 
    
</dd>
</dl>

<dl>
<dd>

**request_options:** `typing.Optional[RequestOptions]` — Request-specific configuration.
    
</dd>
</dl>
</dd>
</dl>


</dd>
</dl>
</details>

