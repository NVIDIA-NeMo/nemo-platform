# AgentAttemptRuntime compliance mapping

This document maps `nat_runner.py` responsibilities to the agent-eval SDK
design (see `CapturedAgentAttempt` in `shared/evaluator_agent_eval/schemas.py`
and `AgentAttemptRuntime` in `nemo_evaluator_sdk.agent_eval`).

Design reference: internal agent-eval SDK doc
(`https://docs.google.com/document/d/1mA9Kl6LVJFlgbj5CGulUOiaGyliP7QhqBh7jKXFGifM`).

## Scope split (per SDK design)

| `nat_runner` responsibility | Belongs in `AgentAttemptRuntime`? | Current location |
|----------------------------|-----------------------------------|------------------|
| AGENT phase — run backend in Docker, capture logs/trajectory | **Yes** | `runtimes/<backend>/runtime.py` |
| BUILD — task image | **No** | `AgenticEvalOrchestrator` via `shared/environment_spec.py` (env spec / Dockerfile) + `shared/docker.py` |
| VERIFY — pytest `test_outputs.py`, `reward.txt` | **Through env boundary** | `shared/verify.py` via `AgentEnvironmentHandle.run_verifier` (runtimes call it after the agent when `shared.run_verify=True`) |
| CLI — task globs, manifests, summaries | **No** | Still `nat_runner.main` (not migrated) |
| `result.json` contract | **No** (still produced by `nat_runner`) | Importable as an attempt via `shared/result_adapter.py` |

## Backend → runtime class (one class per backend)

| `nat_runner --agent-backend` | Runtime class | Status |
|------------------------------|---------------|--------|
| `workflow` | `NatWorkflowAttemptRuntime` | Implemented |
| `aut` | `AutAgentAttemptRuntime` | Implemented |
| `claude-code` | `ClaudeCodeAgentAttemptRuntime` | Scaffold |
| `codex` | `CodexAgentAttemptRuntime` | Scaffold |
| `cursor-agent` | `CursorAgentAttemptRuntime` | Scaffold |

## `nat_runner` function → module

| Function | Runtime module |
|----------|----------------|
| `_build_workflow_agent_cmd` | `workflow/command.py` |
| `_prepare_workflow_for_runtime` | `workflow/prep.py` |
| `_build_aut_agent_cmd` | `aut/command.py` |
| `_prepare_aut_config_for_runtime` | `aut/prep.py` |
| `_agent_log_has_workflow_error` | `shared/agent_log.py` |
| `run_verify_phase` | `shared/verify.py` (`build_verify_run_spec` + `run_verify` via `run_verifier`) |
| `_docker_run`, `build_task_image` | `shared/docker.py` (`docker_run`, `build_dockerfile`, `build_task_image`) |
| BUILD env resolution (`environment/Dockerfile`) | `shared/environment_spec.py` (`load_environment_spec`, `plan_task_build`) |
| `_write_result` (`result.json`) | `shared/result_adapter.py` (import side only; `nat_runner` still writes it) |
| pass-rate / token / runtime gate | `shared/reporting.py` (mirrors `passrate_token_policy_gate.py`) |
| `_extract_usage_metrics` | `shared/usage.py` (delegates to `nat_runner` until deduped) |
| `capture_agent_attempt` shape | `shared/artifacts.py` |
| `run_agent_phase` | **Removed per backend** once all backends migrated |

## Attempt record contract

`AgentAttemptRuntime.run_tasks()` returns `AgentEvalAttempt` values whose metadata
includes canonical `CapturedAgentAttempt` fields:

- `agent_runtime`, `agent_model`
- `exit_code`, `duration_ms`, `run_id`, `repo_revision` (when known)
- Artifact paths: `agent_log_dir`, `workspace_dir`, `state_dir`, `atif_trajectory_path`
- Phase outcome: `agent_ok`
- Verifier outcome (when `run_verify=True`): `verify_status`, `passed`, `reward`,
  `verifier_log_dir` (stamped by `shared/verify.py::apply_verify_to_metadata`)

Use `to_captured_agent_attempt(task, attempt)` for verify/scoring code that
expects the portable `CapturedAgentAttempt` type.

## `nat_runner` artifact → `AgentEvalAttempt` evidence map (per design doc)

`shared/artifacts.py::_evidence_descriptors` emits the documented keys:

| `nat_runner` output | `AgentEvalAttempt` mapping | Status |
|---------------------|----------------------------|--------|
| `workspace/` | `evidence["final_state"]` (filesystem, `role=final_state`) | Implemented |
| preserved platform/db state | `evidence["state"]` (filesystem, `role=platform_state`) | Implemented |
| `agent/trajectory.json` | `evidence["trace"]` (ATIF when normalized, else json) | Implemented |
| `agent/` logs | `evidence["logs"]` (dir, `primary_log=nat_agent.log`) | Implemented |
| `verifier/` logs | `evidence["verifier_logs"]` (added once verify phase runs) | Implemented (conditional) |
| `result.json` | attempt status + measurements + provenance + token/cost | Implemented — `shared/result_adapter.py::attempt_from_result` / `attempt_from_result_dir` |
| final agent log/message | `AgentOutput.text` | Implemented |

`result.json` mapping detail (`attempt_from_result`):

- `result["agent"]` → attempt `status` (`ok`/`skipped` → `completed`, else `failed`).
- `result["reward"]`/`result["passed"]` → `metadata` measurements (verifier reward
  stays a *measurement*, scored by `VerifierRewardMetric`, not the attempt status).
- `result["metrics"]` (token/cost) → flattened into `metadata`.
- `result["provenance"]`, `candidate_id`, `candidate_params`, `image` → `metadata`.

## Alignment with the design doc's implementation path

| Doc section | Status in this package |
|-------------|------------------------|
| **B1** wrap `nat_runner` as attempt runtime(s) | In progress — AGENT phase extracted to per-backend runtimes (`workflow`, `aut` done; 3 CLI backends scaffolded); live VERIFY wired through the B2 boundary; `result.json` import path added via `shared/result_adapter.py`. Remaining: 3 CLI backends + converging `nat_runner.main` onto the orchestrator. Note: doc proposes one `NatRunnerAttemptRuntime`; we deliberately split per backend per user direction. |
| **B2** `EnvironmentProvider` boundary | **Implemented** — `shared/environment.py` defines `AgentEnvironmentProvider`/`AgentEnvironmentHandle` below `AgentAttemptRuntime`; `DockerEnvironmentProvider` wraps `shared/docker.py`. `workflow` + `aut` runtimes execute through the boundary (provider is injectable). NeMo Gym/local providers can now be added without touching runtimes. |
| **B3** standardize environment authoring | **Implemented (minimal)** — `shared/environment_spec.py` adds a declarative `environment.yaml` (`image` + `profile` + python `dependencies` + `setup`) with a `dockerfile:` escape hatch and backward-compatible auto-detection of `environment/Dockerfile`. `plan_task_build` resolves a spec to a `BuildPlan` (image-based specs generate a tiny derived Dockerfile); the orchestrator BUILD step uses it. `setup` steps are carried as plan/label metadata, not executed (runtime concern). |
| **B4** productize results + CI | **Implemented** — SDK `persist_run` writes `tasks/attempts/results.jsonl`, `summary.json`, `report.html`; `shared/reporting.py` adds candidate-vs-baseline gating (pass-rate, token/cost, runtime tie-breaker) + deterministic provenance checks, persisted as `gate.json` by the orchestrator. `result.json` → attempt adapter + `VerifierRewardMetric` compatibility metric also done. |

### B4 reporting / gating detail

- **Persistence** (already SDK-native): `AgentEvaluator.run(config.output_dir=...)`
  calls `agent_eval.persistence.persist_run`, writing `tasks.jsonl`,
  `attempts.jsonl`, `results.jsonl`, `summary.json`, `benchmark.json`, `run.json`,
  and (when `write_dashboard=True`) `report.html`.
- **Gating** (`shared/reporting.py`): `summarize_run` aggregates pass-rate,
  token totals/coverage, runtime totals, and run-level provenance from the typed
  `AgentEvalRunResult` (metric scores first, attempt metadata as fallback).
  `evaluate_gate` applies absolute thresholds and candidate-vs-baseline checks:
  `min_pass_rate`, `no_pass_rate_regression_vs_baseline`,
  `tokens_not_worse_than_baseline`, `runtime_tie_breaker_not_worse_than_baseline`,
  `baseline_candidate_task_sets_match`, `commit_sha_consistent_within_run`,
  `commit_sha_matches_baseline` (cross-commit guard). Semantics mirror
  `passrate_token_policy_gate.py`, so summaries are interchangeable as baselines.
- **Orchestrator wiring**: `AgenticOrchestratorConfig.write_gate` /
  `gate_thresholds` / `baseline_summary_path` control emission of `gate.json`
  next to the run bundle.

### B2 boundary deviation (documented)

The doc sketches `AgentEnvironmentHandle.run_agent(instruction, config) -> AgentEvalAttempt`.
We instead use `run_agent(EnvRunSpec) -> EnvCommandResult` (and the symmetric
`run_verifier`). Rationale: per-backend command/env/mount construction lives in the
runtime, and attempt construction lives in `shared/artifacts.py`. Keeping the
environment layer at "execute a command, return exit status" means a new provider
(local, Harbor, NeMo Gym) only implements process execution — it never needs to
know about backends or attempt schemas.
