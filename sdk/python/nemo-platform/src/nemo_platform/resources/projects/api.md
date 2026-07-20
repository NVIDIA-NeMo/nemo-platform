# Projects

Types:

```python
from nemo_platform.types.projects import Project, ProjectParam, ProjectUpdate, ProjectsPage
```

Methods:

- <code title="post /apis/entities/v2/workspaces/{workspace}/projects">client.projects.<a href="./src/nemo_platform/resources/projects/projects.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/projects/project_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/projects/project.py">Project</a></code>
- <code title="get /apis/entities/v2/workspaces/{workspace}/projects/{name}">client.projects.<a href="./src/nemo_platform/resources/projects/projects.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/projects/project.py">Project</a></code>
- <code title="put /apis/entities/v2/workspaces/{workspace}/projects/{name}">client.projects.<a href="./src/nemo_platform/resources/projects/projects.py">update</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/projects/project_update_params.py">params</a>) -> <a href="./src/nemo_platform/types/projects/project.py">Project</a></code>
- <code title="get /apis/entities/v2/workspaces/{workspace}/projects">client.projects.<a href="./src/nemo_platform/resources/projects/projects.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/projects/project_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/projects/project.py">SyncDefaultPagination[Project]</a></code>
- <code title="delete /apis/entities/v2/workspaces/{workspace}/projects/{name}">client.projects.<a href="./src/nemo_platform/resources/projects/projects.py">delete</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>
