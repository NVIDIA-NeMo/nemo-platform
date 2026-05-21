# Evaluation

Types:

```python
from nemo_platform.types.evaluation import (
    Agent,
    AgentGoalAccuracyMetric,
    AgentGoalAccuracyMetricParam,
    AggregatedMetricResult,
    AnswerAccuracyMetric,
    AnswerAccuracyMetricParam,
    BleuMetric,
    BleuMetricParam,
    ContextEntityRecallMetric,
    ContextEntityRecallMetricParam,
    ContextPrecisionMetric,
    ContextPrecisionMetricParam,
    ContextRecallMetric,
    ContextRecallMetricParam,
    ContextRelevanceMetric,
    ContextRelevanceMetricParam,
    DatasetRows,
    ExactMatchMetric,
    ExactMatchMetricParam,
    F1Metric,
    F1MetricParam,
    FaithfulnessMetric,
    FaithfulnessMetricParam,
    FieldMapping,
    FilesetRef,
    InferenceParams,
    JsonScoreParser,
    LLMJudgeMetric,
    LLMJudgeMetricParam,
    MetricOutput,
    MetricRef,
    Model,
    NeMoAgentToolkitRemoteMetric,
    NeMoAgentToolkitRemoteMetricParam,
    NoiseSensitivityMetric,
    NoiseSensitivityMetricParam,
    NumberCheckMetric,
    NumberCheckMetricParam,
    Parameter,
    RangeScore,
    ReasoningParams,
    RegexScoreParser,
    RemoteMetric,
    RemoteMetricParam,
    RemoteScore,
    ResponseGroundednessMetric,
    ResponseGroundednessMetricParam,
    ResponseRelevancyMetric,
    ResponseRelevancyMetricParam,
    RougeMetric,
    RougeMetricParam,
    RowScore,
    Rubric,
    RubricScore,
    RunConfig,
    RunConfigOnline,
    RunConfigOnlineModel,
    StringCheckMetric,
    StringCheckMetricParam,
    ToolCallAccuracyMetric,
    ToolCallAccuracyMetricParam,
    ToolCallingMetric,
    ToolCallingMetricParam,
    TopicAdherenceMetric,
    TopicAdherenceMetricParam,
)
```

## Benchmarks

Types:

```python
from nemo_platform.types.evaluation import (
    Benchmark,
    BenchmarkRequest,
    BenchmarksListResponse,
    ExtendedBenchmark,
    SystemBenchmark,
    SystemMetric,
    BenchmarkCreateResponse,
    BenchmarkRetrieveResponse,
)
```

Methods:

- <code title="post /apis/evaluation/v2/workspaces/{workspace}/benchmarks">client.evaluation.benchmarks.<a href="./src/nemo_platform/resources/evaluation/benchmarks.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/benchmark_create_response.py">BenchmarkCreateResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmarks/{name}">client.evaluation.benchmarks.<a href="./src/nemo_platform/resources/evaluation/benchmarks.py">retrieve</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_retrieve_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/benchmark_retrieve_response.py">BenchmarkRetrieveResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmarks">client.evaluation.benchmarks.<a href="./src/nemo_platform/resources/evaluation/benchmarks.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_list_params.py">params</a>) -> SyncDefaultPagination[Data]</code>
- <code title="delete /apis/evaluation/v2/workspaces/{workspace}/benchmarks/{name}">client.evaluation.benchmarks.<a href="./src/nemo_platform/resources/evaluation/benchmarks.py">delete</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>

## BenchmarkJobs

Types:

```python
from nemo_platform.types.evaluation import (
    BenchmarkEvaluationJob,
    BenchmarkEvaluationJobRequest,
    BenchmarkEvaluationJobsListFilter,
    BenchmarkEvaluationJobsPage,
    BenchmarkEvaluationJobsSortField,
    BenchmarkOfflineJob,
    BenchmarkOnlineAgentJob,
    BenchmarkOnlineJob,
    BenchmarkRef,
    SystemBenchmarkOfflineJob,
    SystemBenchmarkOnlineJob,
)
```

Methods:

- <code title="post /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs">client.evaluation.benchmark_jobs.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/benchmark_jobs.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_job_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/benchmark_evaluation_job.py">BenchmarkEvaluationJob</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{name}">client.evaluation.benchmark_jobs.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/benchmark_jobs.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/evaluation/benchmark_evaluation_job.py">BenchmarkEvaluationJob</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs">client.evaluation.benchmark_jobs.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/benchmark_jobs.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_job_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/benchmark_evaluation_job.py">SyncDefaultPagination[BenchmarkEvaluationJob]</a></code>
- <code title="delete /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{name}">client.evaluation.benchmark_jobs.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/benchmark_jobs.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="post /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{name}/cancel">client.evaluation.benchmark_jobs.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/benchmark_jobs.py">cancel</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/evaluation/benchmark_evaluation_job.py">BenchmarkEvaluationJob</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{name}/logs">client.evaluation.benchmark_jobs.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/benchmark_jobs.py">get_logs</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_job_get_logs_params.py">params</a>) -> <a href="./src/nemo_platform/types/shared/platform_job_log.py">SyncLogsPagination[PlatformJobLog]</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{name}/status">client.evaluation.benchmark_jobs.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/benchmark_jobs.py">get_status</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/platform_job_status_response.py">PlatformJobStatusResponse</a></code>

### Results

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{job}/results/{name}">client.evaluation.benchmark_jobs.results.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/results/results.py">retrieve</a>(name, \*, workspace, job) -> <a href="./src/nemo_platform/types/shared/platform_job_result_response.py">PlatformJobResultResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{name}/results">client.evaluation.benchmark_jobs.results.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/results/results.py">list</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/platform_job_list_result_response.py">PlatformJobListResultResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{job}/results/{name}/download">client.evaluation.benchmark_jobs.results.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/results/results.py">download</a>(name, \*, workspace, job) -> BinaryAPIResponse</code>

#### AggregateScores

Types:

```python
from nemo_platform.types.evaluation.benchmark_jobs.results import (
    BenchmarkEvaluationResult,
    BenchmarkMetricResult,
)
```

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{job}/results/aggregate-scores/download">client.evaluation.benchmark_jobs.results.aggregate_scores.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/results/aggregate_scores.py">download</a>(job, \*, workspace) -> <a href="./src/nemo_platform/types/evaluation/benchmark_jobs/results/benchmark_evaluation_result.py">BenchmarkEvaluationResult</a></code>

#### RowScores

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{job}/results/row-scores/download">client.evaluation.benchmark_jobs.results.row_scores.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/results/row_scores.py">download</a>(job, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_jobs/results/row_score_download_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/row_score.py">JSONLDecoder[RowScore]</a></code>

#### Artifacts

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-jobs/{job}/results/artifacts/download">client.evaluation.benchmark_jobs.results.artifacts.<a href="./src/nemo_platform/resources/evaluation/benchmark_jobs/results/artifacts.py">download</a>(job, \*, workspace) -> BinaryAPIResponse</code>

## BenchmarkJobResults

Types:

```python
from nemo_platform.types.evaluation import BenchmarkJobResult, BenchmarkJobResultsListResponse
```

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-job-results/{name}">client.evaluation.benchmark_job_results.<a href="./src/nemo_platform/resources/evaluation/benchmark_job_results.py">retrieve</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_job_result_retrieve_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/benchmark_job_result.py">BenchmarkJobResult</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/benchmark-job-results">client.evaluation.benchmark_job_results.<a href="./src/nemo_platform/resources/evaluation/benchmark_job_results.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/benchmark_job_result_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/benchmark_job_result.py">SyncDefaultPagination[BenchmarkJobResult]</a></code>
- <code title="delete /apis/evaluation/v2/workspaces/{workspace}/benchmark-job-results/{name}">client.evaluation.benchmark_job_results.<a href="./src/nemo_platform/resources/evaluation/benchmark_job_results.py">delete</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>

## Metrics

Types:

```python
from nemo_platform.types.evaluation import (
    AgentGoalAccuracyMetricResponse,
    AggregateRangeScore,
    AggregateRubricScore,
    AnswerAccuracyMetricResponse,
    BleuMetricResponse,
    ContextEntityRecallMetricResponse,
    ContextPrecisionMetricResponse,
    ContextRecallMetricResponse,
    ContextRelevanceMetricResponse,
    EvaluateDatasetRows,
    ExactMatchMetricResponse,
    F1MetricResponse,
    FaithfulnessMetricResponse,
    Histogram,
    HistogramBin,
    LLMJudgeMetricResponse,
    MetricEvaluationRequest,
    MetricEvaluationResponse,
    MetricEvaluationRowScore,
    MetricType,
    MetricsListResponse,
    ModelRef,
    NeMoAgentToolkitRemoteMetricResponse,
    NoiseSensitivityMetricResponse,
    NumberCheckMetricResponse,
    Percentiles,
    RemoteMetricResponse,
    ResponseGroundednessMetricResponse,
    ResponseRelevancyMetricResponse,
    RougeMetricResponse,
    RubricScoreStat,
    StringCheckMetricResponse,
    SystemMetricResponse,
    ToolCallAccuracyMetricResponse,
    ToolCallingMetricResponse,
    TopicAdherenceMetricResponse,
    MetricCreateResponse,
    MetricRetrieveResponse,
)
```

Methods:

- <code title="post /apis/evaluation/v2/workspaces/{workspace}/metrics/{name}">client.evaluation.metrics.<a href="./src/nemo_platform/resources/evaluation/metrics.py">create</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/metric_create_response.py">MetricCreateResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metrics/{name}">client.evaluation.metrics.<a href="./src/nemo_platform/resources/evaluation/metrics.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/evaluation/metric_retrieve_response.py">MetricRetrieveResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metrics">client.evaluation.metrics.<a href="./src/nemo_platform/resources/evaluation/metrics.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_list_params.py">params</a>) -> SyncDefaultPagination[Data]</code>
- <code title="delete /apis/evaluation/v2/workspaces/{workspace}/metrics/{name}">client.evaluation.metrics.<a href="./src/nemo_platform/resources/evaluation/metrics.py">delete</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>
- <code title="post /apis/evaluation/v2/workspaces/{workspace}/metric-evaluate">client.evaluation.metrics.<a href="./src/nemo_platform/resources/evaluation/metrics.py">evaluate</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_evaluate_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/metric_evaluation_response.py">MetricEvaluationResponse</a></code>

## MetricJobs

Types:

```python
from nemo_platform.types.evaluation import (
    BuiltInDataset,
    Fileset,
    MetricEvaluationJob,
    MetricEvaluationJobRequest,
    MetricEvaluationJobsListFilter,
    MetricEvaluationJobsPage,
    MetricEvaluationJobsSortField,
    MetricOfflineJob,
    MetricOnlineAgentJob,
    MetricOnlineJob,
    MetricRetrieverJob,
    RetrieverPipeline,
    SystemMetricParam,
)
```

Methods:

- <code title="post /apis/evaluation/v2/workspaces/{workspace}/metric-jobs">client.evaluation.metric_jobs.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/metric_jobs.py">create</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_job_create_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/metric_evaluation_job.py">MetricEvaluationJob</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{name}">client.evaluation.metric_jobs.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/metric_jobs.py">retrieve</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/evaluation/metric_evaluation_job.py">MetricEvaluationJob</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs">client.evaluation.metric_jobs.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/metric_jobs.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_job_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/metric_evaluation_job.py">SyncDefaultPagination[MetricEvaluationJob]</a></code>
- <code title="delete /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{name}">client.evaluation.metric_jobs.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/metric_jobs.py">delete</a>(name, \*, workspace) -> None</code>
- <code title="post /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{name}/cancel">client.evaluation.metric_jobs.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/metric_jobs.py">cancel</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/evaluation/metric_evaluation_job.py">MetricEvaluationJob</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{name}/logs">client.evaluation.metric_jobs.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/metric_jobs.py">get_logs</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_job_get_logs_params.py">params</a>) -> <a href="./src/nemo_platform/types/shared/platform_job_log.py">SyncLogsPagination[PlatformJobLog]</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{name}/status">client.evaluation.metric_jobs.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/metric_jobs.py">get_status</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/platform_job_status_response.py">PlatformJobStatusResponse</a></code>

### Results

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{job}/results/{name}">client.evaluation.metric_jobs.results.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/results/results.py">retrieve</a>(name, \*, workspace, job) -> <a href="./src/nemo_platform/types/shared/platform_job_result_response.py">PlatformJobResultResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{name}/results">client.evaluation.metric_jobs.results.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/results/results.py">list</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/platform_job_list_result_response.py">PlatformJobListResultResponse</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{job}/results/{name}/download">client.evaluation.metric_jobs.results.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/results/results.py">download</a>(name, \*, workspace, job) -> BinaryAPIResponse</code>

#### AggregateScores

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{job}/results/aggregate-scores/download">client.evaluation.metric_jobs.results.aggregate_scores.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/results/aggregate_scores.py">download</a>(job, \*, workspace) -> <a href="./src/nemo_platform/types/evaluation/aggregated_metric_result.py">AggregatedMetricResult</a></code>

#### RowScores

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{job}/results/row-scores/download">client.evaluation.metric_jobs.results.row_scores.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/results/row_scores.py">download</a>(job, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_jobs/results/row_score_download_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/row_score.py">JSONLDecoder[RowScore]</a></code>

#### Artifacts

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-jobs/{job}/results/artifacts/download">client.evaluation.metric_jobs.results.artifacts.<a href="./src/nemo_platform/resources/evaluation/metric_jobs/results/artifacts.py">download</a>(job, \*, workspace) -> BinaryAPIResponse</code>

## MetricJobResults

Types:

```python
from nemo_platform.types.evaluation import MetricJobResult, MetricJobResultsListResponse
```

Methods:

- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-job-results/{name}">client.evaluation.metric_job_results.<a href="./src/nemo_platform/resources/evaluation/metric_job_results.py">retrieve</a>(name, \*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_job_result_retrieve_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/metric_job_result.py">MetricJobResult</a></code>
- <code title="get /apis/evaluation/v2/workspaces/{workspace}/metric-job-results">client.evaluation.metric_job_results.<a href="./src/nemo_platform/resources/evaluation/metric_job_results.py">list</a>(\*, workspace, \*\*<a href="src/nemo_platform/types/evaluation/metric_job_result_list_params.py">params</a>) -> <a href="./src/nemo_platform/types/evaluation/metric_job_result.py">SyncDefaultPagination[MetricJobResult]</a></code>
- <code title="delete /apis/evaluation/v2/workspaces/{workspace}/metric-job-results/{name}">client.evaluation.metric_job_results.<a href="./src/nemo_platform/resources/evaluation/metric_job_results.py">delete</a>(name, \*, workspace) -> <a href="./src/nemo_platform/types/shared/delete_response.py">DeleteResponse</a></code>
