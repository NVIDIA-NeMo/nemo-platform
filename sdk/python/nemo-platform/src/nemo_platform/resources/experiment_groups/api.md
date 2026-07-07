# ExperimentGroups

Types:

```python
from nemo_platform.types.experiment_groups import (
    ExperimentGroupFilter,
    ExperimentGroupRequest,
    ExperimentGroupResponse,
    ExperimentGroupResponsesPage,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/experiment-groups">client.experiment_groups.<a href="./src/nemo_platform/resources/experiment_groups/experiment_groups.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/experiment_groups/experiment_group_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/experiment_groups/experiment_group_response.py">ExperimentGroupResponse</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}">client.experiment_groups.<a href="./src/nemo_platform/resources/experiment_groups/experiment_groups.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/experiment_groups/experiment_group_response.py">ExperimentGroupResponse</a></code>
- <code title="put /apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}">client.experiment_groups.<a href="./src/nemo_platform/resources/experiment_groups/experiment_groups.py">update</a>(path_name, \*, workspace, \*\*<a href="src/nemo_platform/types/experiment_groups/experiment_group_update_params.py">params</a>) -> <a href="./src/nemo_platform/types/experiment_groups/experiment_group_response.py">ExperimentGroupResponse</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/experiment-groups">client.experiment_groups.<a href="./src/nemo_platform/resources/experiment_groups/experiment_groups.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/experiment_groups/experiment_group_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/experiment_groups/experiment_group_response.py">SyncDefaultPagination[ExperimentGroupResponse]</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/experiment-groups/{name}">client.experiment_groups.<a href="./src/nemo_platform/resources/experiment_groups/experiment_groups.py">delete</a>(name, \*, workspace) -> None</code>
