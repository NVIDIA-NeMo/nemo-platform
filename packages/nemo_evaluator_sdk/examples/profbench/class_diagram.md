# ProfBench Class Diagram

```mermaid
classDiagram
    direction LR

    class ProfBenchBenchmark {
        +list~AgentEvalTask~ tasks
        +list~AgentEvalAttempt~ attempts
        +dict metadata
    }

    class ProfBenchCriterion {
        +str id
        +str description
        +str weight_name
        +float points
        +CriterionType criterion_type
        +str source_uri
        +int line_number
        +str json_path
        +from_raw(...) ProfBenchCriterion
        +source_locator() EvidenceLocator
    }

    class ProfBenchRubricMetric {
        +list~ProfBenchCriterion~ criteria
        +ProfBenchJudge judge
        +Path evidence_dir
        +type str
        +output_spec() list~MetricOutputSpec~
        +compute_scores(input) MetricResult
        -_score(input) ProfBenchRubricDetails
        -_write_judge_artifact(...) EvidenceLocator
    }

    class ProfBenchJudge {
        <<Protocol>>
        +judge(request) Awaitable~ProfBenchJudgeDecision~
    }

    class ProfBenchModelJudge {
        +Model model
        +RunConfigOnlineModel params
        +InferenceFn inference_fn
        +Any client
        +dict default_headers
        +judge(request) ProfBenchJudgeDecision
    }

    class ProfBenchJudgeRequest {
        +str task_id
        +str prompt
        +str response
        +str criterion_id
        +str criterion_description
        +CriterionType criterion_type
        +str weight_name
    }

    class ProfBenchJudgeDecision {
        +bool fulfilled
        +str reason
        +dict raw_response
    }

    class ProfBenchRubricDetails {
        +float score
        +float earned_points
        +float max_points
        +str model_id
        +str domain
        +list~CriterionScore~ criterion_scores
        +list~ScoreDeduction~ deductions
    }

    class CriterionScore {
        +str criterion_id
        +str description
        +CriterionType criterion_type
        +str weight_name
        +float points
        +bool fulfilled
        +list~EvidenceLocator~ evidence
        +str judge_reason
        +dict metadata
    }

    class ScoreDeduction {
        +float raw_points
        +float normalized_impact
        +str criterion_id
        +str reason
        +list~EvidenceLocator~ evidence
        +dict metadata
    }

    class EvidenceLocator {
        +str kind
        +str uri
        +int line
        +str json_path
        +str excerpt
        +str label
        +href() str
    }

    class AgentEvalTask {
        <<SDK>>
    }

    class AgentEvalAttempt {
        <<SDK>>
    }

    class AgentEvalRunResult {
        <<SDK>>
    }

    class write_example_dashboards {
        <<function>>
        +write_example_dashboards(result, output_dir) dashboard paths
    }

    class render_profbench_dashboard {
        <<function>>
        +render_profbench_dashboard(result) str
    }

    class load_profbench {
        <<function>>
        +load_profbench(source, limit, judge, evidence_dir, include_cached_fulfilments) ProfBenchBenchmark
    }

    load_profbench ..> ProfBenchBenchmark : creates
    load_profbench ..> ProfBenchCriterion : builds criteria
    load_profbench ..> ProfBenchRubricMetric : attaches to tasks
    load_profbench ..> AgentEvalTask : creates
    load_profbench ..> AgentEvalAttempt : creates recorded attempts

    ProfBenchBenchmark o-- AgentEvalTask
    ProfBenchBenchmark o-- AgentEvalAttempt

    ProfBenchRubricMetric o-- ProfBenchCriterion
    ProfBenchRubricMetric o-- ProfBenchJudge
    ProfBenchRubricMetric ..> ProfBenchRubricDetails : emits
    ProfBenchRubricMetric ..> EvidenceLocator : writes judge artifacts

    ProfBenchJudge <|.. ProfBenchModelJudge
    ProfBenchModelJudge ..> ProfBenchJudgeRequest : sends
    ProfBenchModelJudge ..> ProfBenchJudgeDecision : returns

    ProfBenchRubricDetails o-- CriterionScore
    ProfBenchRubricDetails o-- ScoreDeduction
    CriterionScore o-- EvidenceLocator
    ScoreDeduction o-- EvidenceLocator

    write_example_dashboards ..> AgentEvalRunResult
    write_example_dashboards ..> render_profbench_dashboard
    render_profbench_dashboard ..> ProfBenchRubricDetails : reads metric output
```

## How to read this diagram

This diagram shows how the ProfBench example adapts the generic SDK agent-eval types. The boxes marked `<<SDK>>` are imported from `nemo_evaluator_sdk.agent_eval`; the other boxes are ProfBench-specific.

Notation:

- `o--` means "contains" or "is made of". For example, `ProfBenchBenchmark o-- AgentEvalTask` means the loaded benchmark object contains SDK tasks.
- `..>` means "uses", "creates", or "depends on". For example, `load_profbench ..> ProfBenchCriterion` means the loader builds criterion objects.
- `<|..` means "implements protocol". Here, `ProfBenchModelJudge` implements the `ProfBenchJudge` protocol.
- `<<function>>` marks module-level helper functions rather than classes.
- `+` means public field/method. `-` means private/internal helper.

Main structure:

1. `load_profbench()` reads the JSONL dataset and returns a `ProfBenchBenchmark`.
2. `ProfBenchBenchmark` contains SDK `AgentEvalTask` objects and recorded SDK `AgentEvalAttempt` objects.
3. Each task gets one `ProfBenchRubricMetric` configured with a list of `ProfBenchCriterion` objects.
4. Baseline scoring uses cached fulfilment labels from the dataset.
5. Live scoring uses a `ProfBenchJudge`; the concrete implementation is `ProfBenchModelJudge`.
6. The metric emits generic SDK metric outputs, but the detailed output value is a `ProfBenchRubricDetails` object.
7. The ProfBench dashboard reads those detailed outputs to render model scores, criterion scores, deductions, and evidence links.

Evidence model:

- `ProfBenchCriterion.source_locator()` links each criterion back to the local copied dataset JSONL.
- Live judge decisions can be written as `judge-*.json` artifacts.
- `CriterionScore` and `ScoreDeduction` both point at `EvidenceLocator` entries so the report can link back to source and judge evidence.
