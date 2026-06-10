# Agentic-Use Runtime Architecture

This package adapts the task directories under `tests/agentic-use/` to the
Evaluator SDK `AgentEvaluator` APIs. It separates three concerns:

- CLI routing in `run_agent_eval.py`
- backend-specific attempt generation in runtime classes
- shared task loading, build, layout, verification, and reporting helpers

## Runtime Package Model

The core contract is simple: every backend runtime implements the SDK
`AgentAttemptRuntime` shape by exposing `run_tasks(tasks, config)`. A runtime
receives one or more `AgentEvalTask` objects and returns `AgentEvalAttempt`
objects containing the candidate answer plus evidence metadata.

`AgenticEvalOrchestrator` is the normal agentic-use path. It loads one task
directory, builds that task image, runs the selected runtime through
`AgentEvaluator`, optionally runs verify, and writes gate/report artifacts.

`run_agent_eval.py --task profbench` is intentionally special. ProfBench rows are
loaded from the SDK `ProfBenchAgentEvalBenchmark`, not from a task-local
`instruction.md`. For `--backend workflow`, candidate generation uses an SDK
`Model` target directly instead of the NAT `workflow.yml` runtime because
ProfBench prompts are pure model-answer tasks and do not need NeMo MCP tools.

## Execution Workflow

```mermaid
flowchart TD
    CLI["CLI: run_agent_eval.py"] --> Parse["Parse args and shared config"]
    Parse --> TaskBranch{"args.task == profbench?"}

    TaskBranch -- "no" --> RescoreBranch{"--rescore-dir provided?"}
    RescoreBranch -- "no: live agentic-use task" --> RuntimeSelect["runtime_for_backend(args.backend)"]
    RuntimeSelect --> RuntimeConfig["Build backend config\nWorkflow / AUT / Codex / Claude / Cursor"]
    RuntimeConfig --> Orchestrator["AgenticEvalOrchestrator(runtime)"]
    Orchestrator --> LoadTask["agentic_task_from_dir(task_name)\nreads instruction.md + task.toml"]
    LoadTask --> Metrics["Keep task metrics\nappend VerifierRewardMetric if verify is enabled"]
    Metrics --> BuildImage["plan_task_build + execute_build_plan\nor require existing image with --skip-build"]
    BuildImage --> SDKRun["AgentEvaluator.run(tasks=[task], target=runtime)"]
    SDKRun --> RuntimeRun{"Concrete runtime"}
    RuntimeRun -- "workflow" --> NAT["NatWorkflowAttemptRuntime\nuses task_dir/workflow.yml\nruns nat inside task image"]
    RuntimeRun -- "aut" --> AUT["AutAgentAttemptRuntime\nruns AUT backend in task image"]
    RuntimeRun -- "codex" --> Codex["CodexAgentAttemptRuntime\nthin wrapper around SDK Codex runtime"]
    RuntimeRun -- "scaffolded" --> Other["Claude/Cursor scaffold runtimes"]
    NAT --> Attempt["AgentEvalAttempt + evidence"]
    AUT --> Attempt
    Codex --> Attempt
    Other --> Attempt
    Attempt --> Verify["maybe_run_verify\npytest verifier in same task image when enabled"]
    Verify --> Result["AgentEvalRunResult"]
    Result --> Gate["Optional gate.json/report artifacts"]
    Gate --> Summary["Print run_id, attempts, score, metadata"]

    RescoreBranch -- "yes: stored attempts" --> StoredRuntime["runtime_for_backend(args.backend)\nselected for config/verify policy only"]
    StoredRuntime --> StoredOrch["AgenticEvalOrchestrator(runtime)"]
    StoredOrch --> StoredTask["agentic_task_from_dir(task_name)"]
    StoredTask --> ImportAttempts["attempt_from_result_dir(...)\nimports existing result.json runs"]
    ImportAttempts --> StoredEval["AgentEvaluator.run(tasks=[task], attempts=attempts)"]
    StoredEval --> StoredGate["Optional gate/report artifacts"]
    StoredGate --> Summary

    TaskBranch -- "yes: ProfBench" --> ProfbenchGuard{"--rescore-dir?"}
    ProfbenchGuard -- "yes" --> Error["raise ValueError\nProfBench does not support stored-attempt rescore here"]
    ProfbenchGuard -- "no" --> ProfTarget{"backend == workflow?"}
    ProfTarget -- "yes" --> ModelTarget["SDK Model target\nuses --model/--agent-model\nwith RunConfigOnlineModel"]
    ProfTarget -- "no" --> BackendTarget["runtime_for_backend(args.backend)\nCodex/AUT/etc. target"]
    ModelTarget --> ProfRun["run_profbench_agent_eval(...)"]
    BackendTarget --> ProfRun
    ProfRun --> ProfBundle["ProfBenchAgentEvalBenchmark.load(...)\ncreates dataset row AgentEvalTask objects"]
    ProfBundle --> ProfMetadata["Add task_dir, instruction_path,\nagentic_use_run_subdir metadata"]
    ProfMetadata --> ProfPrepare{"target has environment?"}
    ProfPrepare -- "yes" --> ProfImage["Build/require shared profbench image\nattach DockerEnvironmentProvider"]
    ProfPrepare -- "no" --> ProfEval
    ProfImage --> ProfEval["run_benchmark_bundle(target, params, report_writer)"]
    ProfEval --> ProfReports["SDK dashboard + benchmark report paths"]
    ProfReports --> Summary
```

## Important Current Changes

- `run_agent_eval.py` now has explicit CLI parsing so tests can call `_main(argv)`.
  It routes normal tasks, stored-attempt rescoring, and ProfBench separately.
- `CodexAgentAttemptRuntime` is no longer a scaffold. It delegates to the SDK
  local Codex runtime, or the SDK Docker Codex runtime when `--codex-auth-json`
  is supplied.
- `runtimes/profbench.py` owns the special ProfBench path: it loads SDK benchmark
  rows, attaches live judge config, and only uses the task directory for runtime
  environment metadata.
- `shared/layout.py` honors `task.metadata["agentic_use_run_subdir"]` under an
  explicit SDK `output_dir`, and rejects subdirs that escape the output root.

## Why ProfBench Bypasses `workflow.yml`

Normal `--backend workflow` means: load a task directory, mount its
`workflow.yml`, and execute `nat run` inside the task image.

ProfBench `--backend workflow` currently means something different: use the
Evaluator SDK online `Model` target to answer ProfBench dataset prompts. That
path never constructs `NatWorkflowAttemptRuntime`, so it never reads the
ProfBench task directory's `workflow.yml`.

Because of that, a `tests/agentic-use/profbench/workflow.yml` file is not
required by the new ProfBench route. If kept, it should be renamed or clearly
excluded from generic task execution so it does not look like a normal runnable
agentic-use workflow.
