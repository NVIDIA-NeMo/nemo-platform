# Agent Eval Class Diagram

```mermaid
classDiagram
    direction LR

    class AgentEvaluator {
        +run(tasks, attempts, target, config) AgentEvalRunResult
        +run_sync(tasks, attempts, target, config) AgentEvalRunResult
        -_score_attempts(tasks, attempts, config, run_id) list~AgentEvalTaskResult~
        -_generate_attempts(tasks, target, config) list~AgentEvalAttempt~
    }

    class AgentEvalRunConfig {
        +Path output_dir
        +str run_id
        +object prompt_template
        +RunConfig params
        +int parallelism
        +bool write_dashboard
        +dict benchmark
        +bool fail_fast
    }

    class AgentEvalRunResult {
        +str run_id
        +list~AgentEvalTask~ tasks
        +list~AgentEvalAttempt~ attempts
        +list~AgentEvalTaskResult~ results
        +AgentEvalSummary summary
        +dict benchmark
        +Path output_dir
        +Path dashboard_path
    }

    class AgentEvalTask {
        +str id
        +str intent
        +dict inputs
        +list~Metric~ metrics
        +dict views
        +dict metadata
    }

    class SemanticView {
        +SemanticReducer reducer
        +list~ViewSignal~ signals
    }

    class ViewSignal {
        +str metric
        +str output
        +float weight
    }

    class AgentEvalAttempt {
        +str id
        +str task_id
        +AgentEvalAttemptStatus status
        +AgentOutput output
        +CandidateEvidence evidence
        +dict metadata
    }

    class AgentOutput {
        +str text
        +Any response
        +dict metadata
        +output_text str
    }

    class CandidateEvidence {
        +dict descriptors
        +dict metadata
        +names(kind) list~str~
        +get(name) EvidenceDescriptor
        +require(name, kind) EvidenceDescriptor
        +filesystem(name) LocalFilesystemEvidence
    }

    class EvidenceDescriptor {
        +str kind
        +str ref
        +str format
        +Any data
        +dict metadata
    }

    class LocalFilesystemEvidence {
        +Path root
        +path(relative_path) Path
        +exists(relative_path) bool
        +read_text(relative_path) str
        +iter_paths(relative_path, recursive) list~str~
    }

    class AgentEvalTaskResult {
        +str id
        +str run_id
        +str task_id
        +str attempt_id
        +str metric_type
        +AgentEvalResultStatus status
        +list~MetricOutput~ outputs
        +list~AgentEvalDiagnostic~ diagnostics
        +dict metadata
    }

    class AgentEvalDiagnostic {
        +AgentEvalDiagnosticSeverity severity
        +str message
        +str source
        +dict details
    }

    class AgentEvalSummary {
        +float overall_score
        +dict metric_scores
        +dict metric_coverage
        +dict semantic_view_scores
        +int task_count
        +int attempt_count
        +int result_count
        +from_results(results, tasks) AgentEvalSummary
    }

    class AgentEvalMetricOutputCoverage {
        +int total
        +int scored
        +int failed
        +int missing
    }

    class AgentAttemptRuntime {
        <<Protocol>>
        +run_tasks(tasks, config) Sequence~AgentEvalAttempt~
    }

    class AgentEvalTarget {
        <<TypeAlias>>
    }

    note for AgentEvalTarget "Model | Agent | AgentAttemptRuntime"

    class Metric {
        <<Protocol>>
        +type MetricTypeName
        +output_spec() list~MetricOutputSpec~
        +compute_scores(input) MetricResult
    }

    class MetricOutput {
        +str name
        +Any value
    }

    AgentEvaluator ..> AgentEvalRunConfig : reads
    AgentEvaluator ..> AgentEvalTarget : accepts target
    AgentEvaluator ..> AgentEvalRunResult : returns
    AgentEvaluator ..> AgentEvalTaskResult : produces
    AgentEvaluator ..> AgentEvalSummary : builds

    AgentEvalRunResult o-- AgentEvalTask
    AgentEvalRunResult o-- AgentEvalAttempt
    AgentEvalRunResult o-- AgentEvalTaskResult
    AgentEvalRunResult o-- AgentEvalSummary

    AgentEvalTask o-- Metric : declares
    AgentEvalTask o-- SemanticView : optional views
    SemanticView o-- ViewSignal

    AgentEvalAttempt o-- AgentOutput
    AgentEvalAttempt o-- CandidateEvidence
    CandidateEvidence o-- EvidenceDescriptor
    CandidateEvidence ..> LocalFilesystemEvidence : lazy handle

    AgentEvalTaskResult o-- MetricOutput
    AgentEvalTaskResult o-- AgentEvalDiagnostic
    AgentEvalSummary o-- AgentEvalMetricOutputCoverage
    AgentAttemptRuntime ..> AgentEvalAttempt : produces
    AgentEvalTarget ..> AgentAttemptRuntime
```

Main flow:

1. `AgentEvaluator.run()` is the orchestrator.
2. A run evaluates `AgentEvalTask` objects with either supplied `AgentEvalAttempt` objects or a live `AgentEvalTarget`.
3. Each task declares concrete `Metric` instances and optional `SemanticView` reporting definitions.
4. Each attempt carries `AgentOutput` plus optional `CandidateEvidence`.
5. Metric execution produces `AgentEvalTaskResult` rows.
6. Results roll up into `AgentEvalSummary`, then `AgentEvalRunResult` holds the complete run bundle.

Evidence model:

- `CandidateEvidence` is descriptor-first. It stores named `EvidenceDescriptor` values.
- `filesystem(name)` is lazy: metrics only get a `LocalFilesystemEvidence` handle if they ask for filesystem evidence.
- `AgentEvalTaskResult` diagnostics represent metric-level failures without necessarily failing the whole run.
