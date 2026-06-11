# ProfBench Live LLM-Judge Execution Sequence

```mermaid
---
config:
  theme: dark
---
sequenceDiagram
    autonumber
    actor User
    participant Caller as SDK caller
    participant Adapter as ProfBenchAgentEvalBenchmark
    participant Loader as load_profbench()
    participant Judge as ProfBenchModelJudge
    participant Evaluator as AgentEvaluator
    participant Candidate as evaluated Model
    participant Metric as ProfBenchRubricMetric
    participant SDK as metric_execution.generate_online_sample()
    participant Persist as persist_run()
    participant Dash as write_example_dashboards()
    participant Output as output-dir/run-id/live-candidate

    User->>Caller: build ProfBench adapter and candidate target
    Caller->>Adapter: load(AgentEvalBenchmarkLoadConfig(LIVE_TARGET))
    Caller->>Caller: create output-dir/run-id/

    opt optional baseline path
        Caller->>Adapter: load(AgentEvalBenchmarkLoadConfig(STORED_ATTEMPTS))
        Caller->>Loader: load_profbench(source, evidence_dir=baseline/evidence)
        Loader-->>Caller: ProfBenchBenchmark(tasks, recorded attempts, metadata)
        Caller->>Evaluator: run(tasks, attempts, config run_id=run-id-baseline)
        Evaluator->>Metric: compute_scores() with cached dataset fulfilments
        Metric-->>Evaluator: MetricResult(profbench, profbench_details)
        Evaluator->>Persist: persist_run(result, baseline/)
        Caller->>Dash: write SDK and ProfBench dashboards
    end

    Caller->>Caller: prepare evaluated target and judge model
    Adapter->>Loader: load_profbench(source, judge=ProfBenchModelJudge, evidence_dir=live-candidate/evidence, include_cached_fulfilments=False)
    Loader->>Output: write evidence/profbench-dataset.jsonl
    Loader-->>Caller: ProfBenchBenchmark(tasks with ProfBenchRubricMetric, metadata)

    Caller->>Evaluator: run(tasks, target=evaluated_model, config run_id=run-id-live-candidate)
    Evaluator->>Evaluator: _generate_attempts(tasks, target)

    loop each ProfBench task
        Evaluator->>SDK: generate_online_sample(target=evaluated_model, row=_task_row(task))
        SDK->>Candidate: inference request with rendered task prompt
        Candidate-->>SDK: model response
        SDK-->>Evaluator: sample(output_text, response)
        Evaluator->>Evaluator: _attempt_from_sample() builds AgentEvalAttempt
    end

    Evaluator->>Evaluator: _score_attempts(tasks, generated attempts)

    loop each generated attempt and rubric criterion
        Evaluator->>Metric: compute_scores(MetricInput(task, candidate, evidence))
        Metric->>Judge: judge(ProfBenchJudgeRequest)
        Judge->>SDK: generate_online_sample(target=judge_model, row=judge prompt)
        SDK->>Judge: raw judge sample(output_text, response)
        Judge->>Judge: _parse_yes_no_decision(output_text)
        Judge-->>Metric: ProfBenchJudgeDecision(fulfilled, reason)
        Metric->>Output: write evidence/judge-*.json
        Metric-->>Evaluator: MetricResult(profbench score, ProfBenchRubricDetails)
    end

    Evaluator->>Evaluator: AgentEvalSummary.from_results()
    Evaluator->>Persist: persist_run(result, live-candidate/)
    Persist->>Output: write benchmark.json
    Persist->>Output: write tasks.jsonl
    Persist->>Output: write attempts.jsonl
    Persist->>Output: write results.jsonl
    Persist->>Output: write summary.json
    Persist->>Output: write run.json manifest
    Persist-->>Evaluator: result with output_dir

    Evaluator-->>Caller: AgentEvalRunResult
    Caller->>Dash: write_example_dashboards(result, live-candidate/)
    Dash->>Output: write sdk-report.html
    Dash->>Output: write report.html
    Caller-->>User: receive task counts, metric scores, dashboard paths
```

## Details

What happens in the full live-candidate path:

1. The SDK caller prepares an output directory, a candidate target, a judge model, and a `ProfBenchAgentEvalBenchmark`.
2. An optional baseline run loads ProfBench recorded attempts, scores those attempts with dataset labels, persists baseline files, and writes dashboards.
3. The live-candidate path uses separate roles for the evaluated target and the judge model.
4. `ProfBenchAgentEvalBenchmark.load()` calls `load_profbench()` with `include_cached_fulfilments=False`, so cached labels are removed and the metric must call the judge.
5. `AgentEvaluator.run(..., target=evaluated_model, ...)` first generates fresh candidate attempts.
6. For each task, the evaluator calls `generate_online_sample()` against the evaluated model and converts the returned sample into an `AgentEvalAttempt`.
7. The evaluator then scores those generated attempts with `ProfBenchRubricMetric`.
8. For each rubric criterion, `ProfBenchRubricMetric` calls `ProfBenchModelJudge`.
9. `ProfBenchModelJudge` calls `generate_online_sample()` against the judge model, parses the judge output into a yes/no decision, and returns it to the metric.
10. The metric writes `evidence/judge-*.json` files and returns `MetricResult` outputs.
11. `AgentEvaluator` builds the summary and persists the run bundle.
12. `write_example_dashboards()` writes both `sdk-report.html` and the ProfBench-specific `report.html`.

Important distinction:

- The evaluated model produces the candidate answer.
- The judge model evaluates each rubric criterion.
- They can point to the same model configuration, but the code treats them as separate roles.

## Execution Flow Diagram

```mermaid
---
config:
  theme: dark
---
flowchart TD
    Start([SDK caller starts])
    Parse[Prepare benchmark config]
    ResolveRun[Resolve output root and create run id]
    CreateRunDir[Create output-dir/run-id]

    Start --> Parse --> ResolveRun --> CreateRunDir

    subgraph Baseline["Baseline path - optional stored attempts"]
        LoadBaseline[ProfBench adapter loads cached fulfilments]
        ScoreBaseline[AgentEvaluator.run with recorded attempts]
        DatasetLabels[ProfBenchRubricMetric uses dataset labels]
        PersistBaseline[Persist baseline run bundle]
        DashBaseline[Write baseline sdk-report.html and report.html]

        LoadBaseline --> ScoreBaseline --> DatasetLabels --> PersistBaseline --> DashBaseline
    end

    CreateRunDir --> LoadBaseline

    DashBaseline --> RunLiveJudge{run live judge?}
    RunLiveJudge -- no --> SkipJudge[Skip live-judge directory]
    RunLiveJudge -- yes --> LoadLiveJudge[load_profbench recorded answers without cached fulfilments]

    subgraph LiveJudge["Live judge path - recorded answers, live rubric judge"]
        LoadLiveJudge --> ScoreRecorded[AgentEvaluator.run with recorded attempts]
        ScoreRecorded --> JudgeRecorded[For each criterion call ProfBenchModelJudge]
        JudgeRecorded --> JudgeArtifactsA[Write live-judge/evidence/judge-*.json]
        JudgeArtifactsA --> PersistLiveJudge[Persist live-judge run bundle]
        PersistLiveJudge --> DashLiveJudge[Write live-judge dashboards]
    end

    SkipJudge --> RunLiveCandidate{run_live_candidate?}
    DashLiveJudge --> RunLiveCandidate

    RunLiveCandidate -- no --> SkipCandidate[Skip live-candidate directory]
    RunLiveCandidate -- yes --> ResolveModels[Prepare evaluated target and judge model]

    subgraph LiveCandidate["Live candidate path - fresh answers, live rubric judge"]
        ResolveModels --> LoadLiveCandidate[load_profbench tasks without cached fulfilments]
        LoadLiveCandidate --> GenerateAttempts[Generate fresh attempts with evaluated model]
        GenerateAttempts --> ScoreFresh[Score generated attempts]
        ScoreFresh --> JudgeFresh[For each criterion call ProfBenchModelJudge]
        JudgeFresh --> JudgeArtifactsB[Write live-candidate/evidence/judge-*.json]
        JudgeArtifactsB --> PersistLiveCandidate[Persist live-candidate run bundle]
        PersistLiveCandidate --> DashLiveCandidate[Write live-candidate dashboards]
    end

    SkipCandidate --> Done([Caller records paths and exits])
    DashLiveCandidate --> Done
```

How this differs from the sequence diagram:

- The sequence diagram shows call timing and who calls whom.
- This flow diagram shows decisions and branches.
- Baseline always runs first.
- `live-judge` reuses recorded dataset answers and only calls the judge model.
- `live-candidate` calls the evaluated model first, then calls the judge model for rubric scoring.
