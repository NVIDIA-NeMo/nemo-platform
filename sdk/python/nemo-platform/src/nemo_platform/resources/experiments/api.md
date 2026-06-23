# Experiments

Types:

```python
from nemo_platform.types.experiments import (
    EvaluatorAggregate,
    ExperimentFilter,
    ExperimentRequest,
    ExperimentResponse,
    ExperimentResponsesPage,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/experiments">client.experiments.<a href="./src/nemo_platform/resources/experiments/experiments.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/experiments/experiment_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/experiments/experiment_response.py">ExperimentResponse</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/experiments/{name}">client.experiments.<a href="./src/nemo_platform/resources/experiments/experiments.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/experiments/experiment_response.py">ExperimentResponse</a></code>
- <code title="put /apis/intake/v2/workspaces/{workspace}/experiments/{name}">client.experiments.<a href="./src/nemo_platform/resources/experiments/experiments.py">update</a>(path_name, \*, workspace, \*\*<a href="src/nemo_platform/types/experiments/experiment_update_params.py">params</a>) -> <a href="./src/nemo_platform/types/experiments/experiment_response.py">ExperimentResponse</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/experiments">client.experiments.<a href="./src/nemo_platform/resources/experiments/experiments.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/experiments/experiment_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/experiments/experiment_response.py">SyncDefaultPagination[ExperimentResponse]</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/experiments/{name}">client.experiments.<a href="./src/nemo_platform/resources/experiments/experiments.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="post /apis/intake/v2/workspaces/{workspace}/experiments/{name}/pin">client.experiments.<a href="./src/nemo_platform/resources/experiments/experiments.py">pin</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/experiments/experiment_response.py">ExperimentResponse</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/experiments/{name}/pin">client.experiments.<a href="./src/nemo_platform/resources/experiments/experiments.py">unpin</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/experiments/experiment_response.py">ExperimentResponse</a></code>

## Sessions

Types:

```python
from nemo_platform.types.experiments import (
    ExperimentSessionFilter,
    ExperimentSessionResponse,
    ExperimentSessionResponsesPage,
)
```

Methods:

- <code title="get /apis/intake/v2/workspaces/{workspace}/experiments/{name}/sessions">client.experiments.sessions.<a href="./src/nemo_platform/resources/experiments/sessions.py">list</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/experiments/session_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/experiments/experiment_session_response.py">SyncDefaultPagination[ExperimentSessionResponse]</a></code>
