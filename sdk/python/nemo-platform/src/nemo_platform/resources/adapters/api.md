# Adapters

Types:

```python
from nemo_platform.types.adapters import AdapterEntityFilter, AdaptersPage
```

Methods:

- <code title="post /apis/models/v2/workspaces/{workspace}/adapters">client.adapters.<a href="./src/nemo_platform/resources/adapters/adapters.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/adapters/adapter_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/models/adapter.py">Adapter</a></code>
- <code title="get /apis/models/v2/workspaces/{workspace}/adapters/{name}">client.adapters.<a href="./src/nemo_platform/resources/adapters/adapters.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/models/adapter.py">Adapter</a></code>
- <code title="get /apis/models/v2/workspaces/{workspace}/adapters">client.adapters.<a href="./src/nemo_platform/resources/adapters/adapters.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/adapters/adapter_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/models/adapter.py">SyncDefaultPagination[Adapter]</a></code>
- <code title="delete /apis/models/v2/workspaces/{workspace}/adapters/{name}">client.adapters.<a href="./src/nemo_platform/resources/adapters/adapters.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="patch /apis/models/v2/workspaces/{workspace}/adapters/{name}">client.adapters.<a href="./src/nemo_platform/resources/adapters/adapters.py">patch</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/adapters/adapter_patch_params.py">params</a>) -> <a href="./src/nemo_platform/types/models/adapter.py">Adapter</a></code>
