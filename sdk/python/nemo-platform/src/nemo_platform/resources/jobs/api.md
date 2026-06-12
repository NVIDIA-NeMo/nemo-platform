# Jobs

Types:

```python
from nemo_platform.types.jobs import (
    ComputeResourceSpec,
    ComputeResources,
    ContainerSpec,
    CPUExecutionProvider,
    CPUExecutionProviderParam,
    CreatePlatformJobRequest,
    DistributedGPUExecutionProvider,
    DistributedGPUExecutionProviderParam,
    DockerJobExecutionProfile,
    DockerJobExecutionProfileConfig,
    DockerJobNetworkConfig,
    DockerJobStorageConfig,
    DockerVolumeMount,
    E2EJobExecutionProfile,
    GPUExecutionProvider,
    GPUExecutionProviderParam,
    ImagePullSecret,
    JobExecutionProfileConfig,
    KubernetesEmptyDirVolume,
    KubernetesJobExecutionProfile,
    KubernetesJobExecutionProfileConfig,
    KubernetesJobStorageConfig,
    KubernetesObjectMetadata,
    KubernetesPersistentVolumeClaim,
    KubernetesVolume,
    KubernetesVolumeMount,
    PlatformJobEnvironmentVariable,
    PlatformJobResponse,
    PlatformJobResponsesPage,
    PlatformJobSecretEnvironmentVariableRef,
    PlatformJobSortField,
    PlatformJobSpec,
    PlatformJobSpecParam,
    PlatformJobStepSpec,
    PlatformJobStepSpecParam,
    PlatformJobsListFilter,
    StepLifecycle,
    SubprocessExecutionProvider,
    SubprocessJobExecutionProfile,
    SubprocessJobExecutionProfileConfig,
    VolcanoJobExecutionProfile,
    VolcanoJobExecutionProfileConfig,
    JobListExecutionProfilesResponse,
)
```

Methods:

- <code title="post /apis/jobs/v2/workspaces/{workspace}/jobs">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/jobs/job_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/jobs/platform_job_response.py">PlatformJobResponse</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{name}">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/jobs/platform_job_response.py">PlatformJobResponse</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/jobs/job_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/jobs/platform_job_response.py">SyncDefaultPagination[PlatformJobResponse]</a></code>
- <code title="delete /apis/jobs/v2/workspaces/{workspace}/jobs/{name}">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="post /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/cancel">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">cancel</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/jobs/platform_job_response.py">PlatformJobResponse</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/logs">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">get_logs</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/jobs/job_get_logs_params.py">params</a>) -> <a href="./src/nemo_platform/types/shared/platform_job_log.py">SyncLogsPagination[PlatformJobLog]</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/status">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">get_status</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/platform_job_status_response.py">PlatformJobStatusResponse</a></code>
- <code title="get /apis/jobs/v2/execution-profiles">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">list_execution_profiles</a>() -> <a href="./src/nemo_platform/types/jobs/job_list_execution_profiles_response.py">JobListExecutionProfilesResponse</a></code>
- <code title="post /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/pause">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">pause</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/jobs/platform_job_response.py">PlatformJobResponse</a></code>
- <code title="post /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/resume">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">resume</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/jobs/platform_job_response.py">PlatformJobResponse</a></code>
- <code title="patch /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/status-details">client.jobs.<a href="./src/nemo_platform/resources/jobs/jobs.py">update_status_details</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/jobs/job_update_status_details_params.py">params</a>) -> object</code>

## Results

Types:

```python
from nemo_platform.types.jobs import PlatformJobResultCreateRequest
```

Methods:

- <code title="post /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/results/{name}">client.jobs.results.<a href="./src/nemo_platform/resources/jobs/results.py">create</a>(name, \*, workspace, job, \*\*<a href="src/nemo_platform/types/jobs/result_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/shared/platform_job_result_response.py">PlatformJobResultResponse</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/results/{name}">client.jobs.results.<a href="./src/nemo_platform/resources/jobs/results.py">retrieve</a>(name, \*, workspace, job) -> <a href="./src/nemo_platform/types/shared/platform_job_result_response.py">PlatformJobResultResponse</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/results">client.jobs.results.<a href="./src/nemo_platform/resources/jobs/results.py">list</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/jobs/result_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/shared/platform_job_list_result_response.py">PlatformJobListResultResponse</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/results/{name}/download">client.jobs.results.<a href="./src/nemo_platform/resources/jobs/results.py">download</a>(name, \*, workspace, job) -> BinaryAPIResponse</code>

## Steps

Types:

```python
from nemo_platform.types.jobs import (
    PlatformJobStatusUpdateRequest,
    PlatformJobStep,
    PlatformJobStepWithContext,
    PlatformJobStepWithContextsPage,
    PlatformJobStepsListFilter,
)
```

Methods:

- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/steps/{name}">client.jobs.steps.<a href="./src/nemo_platform/resources/jobs/steps.py">retrieve</a>(name, \*, workspace, job) -> <a href="./src/nemo_platform/types/jobs/platform_job_step.py">PlatformJobStep</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{name}/steps">client.jobs.steps.<a href="./src/nemo_platform/resources/jobs/steps.py">list</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/jobs/step_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/jobs/platform_job_step_with_context.py">SyncDefaultPagination[PlatformJobStepWithContext]</a></code>
- <code title="patch /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/steps/{name}/status">client.jobs.steps.<a href="./src/nemo_platform/resources/jobs/steps.py">update_status</a>(name, \*, workspace, job, \*\*<a href="src/nemo_platform/types/jobs/step_update_status_params.py">params</a>) -> <a href="./src/nemo_platform/types/jobs/platform_job_step.py">PlatformJobStep</a></code>

## Tasks

Types:

```python
from nemo_platform.types.jobs import (
    PlatformJobListTaskResponse,
    PlatformJobTask,
    PlatformJobTaskUpdate,
)
```

Methods:

- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/steps/{step}/tasks/{name}">client.jobs.tasks.<a href="./src/nemo_platform/resources/jobs/tasks.py">retrieve</a>(name, \*, workspace, job, step) -> <a href="./src/nemo_platform/types/jobs/platform_job_task.py">PlatformJobTask</a></code>
- <code title="get /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/steps/{name}/tasks">client.jobs.tasks.<a href="./src/nemo_platform/resources/jobs/tasks.py">list</a>(name, \*, workspace, job) -> <a href="./src/nemo_platform/types/jobs/platform_job_list_task_response.py">PlatformJobListTaskResponse</a></code>
- <code title="put /apis/jobs/v2/workspaces/{workspace}/jobs/{job}/steps/{step}/tasks/{name}">client.jobs.tasks.<a href="./src/nemo_platform/resources/jobs/tasks.py">create_or_update</a>(name, \*, workspace, job, step, \*\*<a href="src/nemo_platform/types/jobs/task_create_or_update_params.py">params</a>) -> <a href="./src/nemo_platform/types/jobs/platform_job_task.py">PlatformJobTask</a></code>
