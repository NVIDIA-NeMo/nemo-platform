# Intake

## Apps

Types:

```python
from nemo_platform.types.intake import App, AppFilter, AppParam, AppSortField, AppUpdate, AppsPage
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/apps">client.intake.apps.<a href="./src/nemo_platform/resources/intake/apps/apps.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/app_create_params.py">params</a>) -> None</code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/apps/{name}">client.intake.apps.<a href="./src/nemo_platform/resources/intake/apps/apps.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/intake/app.py">App</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/apps">client.intake.apps.<a href="./src/nemo_platform/resources/intake/apps/apps.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/app_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/app.py">SyncDefaultPagination[App]</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/apps/{name}">client.intake.apps.<a href="./src/nemo_platform/resources/intake/apps/apps.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="patch /apis/intake/v2/workspaces/{workspace}/apps/{name}">client.intake.apps.<a href="./src/nemo_platform/resources/intake/apps/apps.py">patch</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/intake/app_patch_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/app.py">App</a></code>

### Tasks

Types:

```python
from nemo_platform.types.intake.apps import (
    Task,
    TaskFilter,
    TaskParam,
    TaskSortField,
    TaskUpdate,
    TasksPage,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/apps/{name}/tasks">client.intake.apps.tasks.<a href="./src/nemo_platform/resources/intake/apps/tasks.py">create</a>(path_name, \*, workspace, \*\*<a href="src/nemo_platform/types/intake/apps/task_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/apps/task.py">Task</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/apps/{app}/tasks/{name}">client.intake.apps.tasks.<a href="./src/nemo_platform/resources/intake/apps/tasks.py">retrieve</a>(name, \*, workspace, app) -> <a href="./src/nemo_platform/types/intake/apps/task.py">Task</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/apps/{name}/tasks">client.intake.apps.tasks.<a href="./src/nemo_platform/resources/intake/apps/tasks.py">list</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/intake/apps/task_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/apps/task.py">SyncDefaultPagination[Task]</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/apps/{app}/tasks/{name}">client.intake.apps.tasks.<a href="./src/nemo_platform/resources/intake/apps/tasks.py">delete</a>(name, \*, workspace, app) -> None</code>
- <code title="patch /apis/intake/v2/workspaces/{workspace}/apps/{app}/tasks/{name}">client.intake.apps.tasks.<a href="./src/nemo_platform/resources/intake/apps/tasks.py">patch</a>(name, \*, workspace, app, \*\*<a href="src/nemo_platform/types/intake/apps/task_patch_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/apps/task.py">Task</a></code>

## Entries

Types:

```python
from nemo_platform.types.intake import (
    Entry,
    EntryContext,
    EntryContextFilter,
    EntryData,
    EntryDataParam,
    EntryFilter,
    EntryParam,
    EntrySortField,
    EntryUpdate,
    EntryUserRatingFilter,
    EntrysPage,
    EvaluatorResultEvent,
    FlexibleEntryRequest,
    FlexibleEntryRequestParam,
    FlexibleEntryResponse,
    FlexibleMessage,
    MessageRole,
    ReviewerAnnotationEvent,
    ThumbDirection,
    Usage,
    UserActionEvent,
    UserFeedbackEvent,
    UserRating,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/entries">client.intake.entries.<a href="./src/nemo_platform/resources/intake/entries/entries.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/entry_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/entry.py">Entry</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/entries/{name}">client.intake.entries.<a href="./src/nemo_platform/resources/intake/entries/entries.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/intake/entry.py">Entry</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/entries">client.intake.entries.<a href="./src/nemo_platform/resources/intake/entries/entries.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/entry_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/entry.py">SyncDefaultPagination[Entry]</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/entries/{name}">client.intake.entries.<a href="./src/nemo_platform/resources/intake/entries/entries.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="patch /apis/intake/v2/workspaces/{workspace}/entries/{name}">client.intake.entries.<a href="./src/nemo_platform/resources/intake/entries/entries.py">patch</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/intake/entry_patch_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/entry.py">Entry</a></code>

### Events

Types:

```python
from nemo_platform.types.intake.entries import EventsCreateRequest
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/entries/{name}/events">client.intake.entries.events.<a href="./src/nemo_platform/resources/intake/entries/events.py">create</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/intake/entries/event_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/entry.py">Entry</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/entries/{entry}/events/{name}">client.intake.entries.events.<a href="./src/nemo_platform/resources/intake/entries/events.py">delete</a>(name, \*, workspace, entry) -> <a href="./src/nemo_platform/types/intake/entry.py">Entry</a></code>

## EvaluatorResults

Types:

```python
from nemo_platform.types.intake import (
    EvaluatorResult,
    EvaluatorResultDataType,
    EvaluatorResultFilter,
    EvaluatorResultParam,
    EvaluatorResultSortField,
    EvaluatorResultsPage,
    FloatFilter,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/evaluator-results">client.intake.evaluator_results.<a href="./src/nemo_platform/resources/intake/evaluator_results.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/evaluator_result_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/evaluator_result.py">EvaluatorResult</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/evaluator-results/{evaluator_result_id}">client.intake.evaluator_results.<a href="./src/nemo_platform/resources/intake/evaluator_results.py">retrieve</a>(evaluator_result_id, \*, workspace) -> <a href="./src/nemo_platform/types/intake/evaluator_result.py">EvaluatorResult</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/evaluator-results">client.intake.evaluator_results.<a href="./src/nemo_platform/resources/intake/evaluator_results.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/evaluator_result_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/evaluator_result.py">SyncDefaultPagination[EvaluatorResult]</a></code>

## Annotations

Types:

```python
from nemo_platform.types.intake import (
    Annotation,
    AnnotationFilter,
    AnnotationKind,
    AnnotationParam,
    AnnotationSortField,
    AnnotationsPage,
    FeedbackAnnotation,
    FeedbackAnnotationParam,
    LabelAnnotation,
    LabelAnnotationParam,
    MetadataAnnotation,
    MetadataAnnotationParam,
    NoteAnnotation,
    NoteAnnotationParam,
    NumericFilter,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/annotations">client.intake.annotations.<a href="./src/nemo_platform/resources/intake/annotations.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/annotation_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/annotation.py">Annotation</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/annotations/{annotation_id}">client.intake.annotations.<a href="./src/nemo_platform/resources/intake/annotations.py">retrieve</a>(annotation_id, \*, workspace) -> <a href="./src/nemo_platform/types/intake/annotation.py">Annotation</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/annotations">client.intake.annotations.<a href="./src/nemo_platform/resources/intake/annotations.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/annotation_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/annotation.py">SyncDefaultPagination[Annotation]</a></code>
- <code title="delete /apis/intake/v2/workspaces/{workspace}/annotations/{annotation_id}">client.intake.annotations.<a href="./src/nemo_platform/resources/intake/annotations.py">delete</a>(annotation_id, \*, workspace) -> None</code>

## Exports

Types:

```python
from nemo_platform.types.intake import (
    ExportConfigParam,
    ExportPreviewRequest,
    ExportPreviewResponse,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/export/preview">client.intake.exports.<a href="./src/nemo_platform/resources/intake/exports/exports.py">preview</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/export_preview_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/export_preview_response.py">ExportPreviewResponse</a></code>

### Jobs

Types:

```python
from nemo_platform.types.intake.exports import (
    ExportConfig,
    ExportJob,
    ExportJobFilter,
    ExportJobParam,
    ExportJobSortField,
    ExportJobsPage,
    ExportStatusDetails,
    JobStatus,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/export/jobs">client.intake.exports.jobs.<a href="./src/nemo_platform/resources/intake/exports/jobs.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/exports/job_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/exports/export_job.py">ExportJob</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/export/jobs/{name}">client.intake.exports.jobs.<a href="./src/nemo_platform/resources/intake/exports/jobs.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/intake/exports/export_job.py">ExportJob</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/export/jobs">client.intake.exports.jobs.<a href="./src/nemo_platform/resources/intake/exports/jobs.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/exports/job_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/exports/export_job.py">SyncDefaultPagination[ExportJob]</a></code>

## Ingest

Types:

```python
from nemo_platform.types.intake import EvaluationContext
```

### Atif

Types:

```python
from nemo_platform.types.intake.ingest import (
    AtifAgent,
    AtifContentPart,
    AtifContentPartImage,
    AtifContentPartText,
    AtifFinalMetrics,
    AtifImageSource,
    AtifIngestRequest,
    AtifMetrics,
    AtifObservation,
    AtifObservationResult,
    AtifStep,
    AtifStepAgent,
    AtifStepSystem,
    AtifStepUser,
    AtifSubagentTrajectoryRef,
    AtifToolCall,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/ingest/atif">client.intake.ingest.atif.<a href="./src/nemo_platform/resources/intake/ingest/atif.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/ingest/atif_create_params.py">params</a>) -> None</code>

### ChatCompletions

Types:

```python
from nemo_platform.types.intake.ingest import (
    ChatCompletionsIngestParam,
    ChatCompletionsIngestResponse,
)
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/ingest/chat-completions">client.intake.ingest.chat_completions.<a href="./src/nemo_platform/resources/intake/ingest/chat_completions.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/ingest/chat_completion_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/ingest/chat_completions_ingest_response.py">ChatCompletionsIngestResponse</a></code>

### Otlp

#### V1

##### Traces

Types:

```python
from nemo_platform.types.intake.ingest.otlp.v1 import IngestResponse
```

Methods:

- <code title="post /apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces">client.intake.ingest.otlp.v1.traces.<a href="./src/nemo_platform/resources/intake/ingest/otlp/v1/traces.py">create</a>(\*, workspace) -> <a href="./src/nemo_platform/types/intake/ingest/otlp/v1/ingest_response.py">IngestResponse</a></code>

## Spans

Types:

```python
from nemo_platform.types.intake import (
    Span,
    SpanEvaluationContext,
    SpanFilter,
    SpanKind,
    SpanSortField,
    SpanStatus,
    SpansPage,
)
```

Methods:

- <code title="get /apis/intake/v2/workspaces/{workspace}/spans/{span_id}">client.intake.spans.<a href="./src/nemo_platform/resources/intake/spans/spans.py">retrieve</a>(span_id, \*, workspace) -> <a href="./src/nemo_platform/types/intake/span.py">Span</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/spans">client.intake.spans.<a href="./src/nemo_platform/resources/intake/spans/spans.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/span_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/span.py">SyncDefaultPagination[Span]</a></code>

### EvaluatorResults

Types:

```python
from nemo_platform.types.intake.spans import EvaluatorResultListResponse
```

Methods:

- <code title="get /apis/intake/v2/workspaces/{workspace}/spans/{span_id}/evaluator-results">client.intake.spans.evaluator_results.<a href="./src/nemo_platform/resources/intake/spans/evaluator_results.py">list</a>(span_id, \*, workspace) -> <a href="./src/nemo_platform/types/intake/spans/evaluator_result_list_response.py">EvaluatorResultListResponse</a></code>

## Traces

Types:

```python
from nemo_platform.types.intake import Trace, TraceFilter, TraceSortField, TracesPage
```

Methods:

- <code title="get /apis/intake/v2/workspaces/{workspace}/traces/{id}">client.intake.traces.<a href="./src/nemo_platform/resources/intake/traces.py">retrieve</a>(id, \*, workspace, \*\*<a href="src/nemo_platform/types/intake/trace_retrieve_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/trace.py">Trace</a></code>
- <code title="get /apis/intake/v2/workspaces/{workspace}/traces">client.intake.traces.<a href="./src/nemo_platform/resources/intake/traces.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/intake/trace_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/intake/trace.py">SyncDefaultPagination[Trace]</a></code>
