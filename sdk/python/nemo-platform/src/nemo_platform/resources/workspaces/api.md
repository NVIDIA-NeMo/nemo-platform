# Workspaces

Types:

```python
from nemo_platform.types.workspaces import (
    Workspace,
    WorkspaceParam,
    WorkspaceUpdate,
    WorkspacesPage,
)
```

Methods:

- <code title="post /apis/entities/v2/workspaces">client.workspaces.<a href="./src/nemo_platform/resources/workspaces/workspaces.py">create</a>(\*\*<a href="src/nemo_platform/types/workspaces/workspace_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/workspaces/workspace.py">Workspace</a></code>
- <code title="get /apis/entities/v2/workspaces/{name}">client.workspaces.<a href="./src/nemo_platform/resources/workspaces/workspaces.py">retrieve</a>(name) -> <a href="./src/nemo_platform/types/workspaces/workspace.py">Workspace</a></code>
- <code title="put /apis/entities/v2/workspaces/{name}">client.workspaces.<a href="./src/nemo_platform/resources/workspaces/workspaces.py">update</a>(name, \*\*<a href="src/nemo_platform/types/workspaces/workspace_update_params.py">params</a>) -> <a href="./src/nemo_platform/types/workspaces/workspace.py">Workspace</a></code>
- <code title="get /apis/entities/v2/workspaces">client.workspaces.<a href="./src/nemo_platform/resources/workspaces/workspaces.py">list</a>(\*\*<a href="src/nemo_platform/types/workspaces/workspace_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/workspaces/workspace.py">SyncDefaultPagination[Workspace]</a></code>
- <code title="delete /apis/entities/v2/workspaces/{name}">client.workspaces.<a href="./src/nemo_platform/resources/workspaces/workspaces.py">delete</a>(name) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>

## Members

Types:

```python
from nemo_platform.types.workspaces import (
    WorkspaceMember,
    WorkspaceMemberListResponse,
    WorkspaceMemberParam,
    WorkspaceMemberUpdate,
)
```

Methods:

- <code title="post /apis/entities/v2/workspaces/{workspace}/members">client.workspaces.members.<a href="./src/nemo_platform/resources/workspaces/members.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/workspaces/member_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/workspaces/workspace_member.py">WorkspaceMember</a></code>
- <code title="put /apis/entities/v2/workspaces/{workspace}/members/{principal_id}">client.workspaces.members.<a href="./src/nemo_platform/resources/workspaces/members.py">update</a>(principal_id, \*, workspace, \*\*<a href="src/nemo_platform/types/workspaces/member_update_params.py">params</a>) -> <a href="./src/nemo_platform/types/workspaces/workspace_member.py">WorkspaceMember</a></code>
- <code title="get /apis/entities/v2/workspaces/{workspace}/members">client.workspaces.members.<a href="./src/nemo_platform/resources/workspaces/members.py">list</a>(\*, workspace) -> <a href="./src/nemo_platform/types/workspaces/workspace_member_list_response.py">WorkspaceMemberListResponse</a></code>
- <code title="delete /apis/entities/v2/workspaces/{workspace}/members/{principal_id}">client.workspaces.members.<a href="./src/nemo_platform/resources/workspaces/members.py">delete</a>(principal_id, \*, workspace, \*\*<a href="src/nemo_platform/types/workspaces/member_delete_params.py">params</a>) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>
