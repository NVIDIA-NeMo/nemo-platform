# Agentic-use AgentAttemptRuntime implementations

Backend-specific runtimes extracted from `nat_runner.py` for use with
`nemo_evaluator_sdk.agent_eval.AgentEvaluator`.

## Layout

```text
runtimes/
  shared/           # backend-agnostic building blocks:
                    #   docker.py            Docker exec + build helpers
                    #   environment.py       AgentEnvironmentProvider/Handle boundary (B2)
                    #   environment_spec.py  environment.yaml authoring + build plans (B3)
                    #   layout.py            per-run output layout
                    #   task_loader.py       agentic-use task -> AgentEvalTask
                    #   container_env.py     base container env vars
                    #   artifacts.py         agent artifacts -> AgentEvalAttempt (+ evidence)
                    #   result_adapter.py    nat_runner result.json -> AgentEvalAttempt (B1/B4)
                    #   verify.py            live VERIFY via run_verifier
                    #   reporting.py         summary + candidate/baseline gate (B4)
                    #   metrics.py           AgentPhaseSuccessMetric, VerifierRewardMetric
  workflow/         # NatWorkflowAttemptRuntime (implemented)
  aut/              # AutAgentAttemptRuntime (implemented)
  claude_code/      # ClaudeCodeAgentAttemptRuntime (scaffold)
  codex/            # CodexAgentAttemptRuntime (scaffold)
  cursor_agent/     # CursorAgentAttemptRuntime (scaffold)
  orchestrator.py   # BUILD (env spec) + AgentEvaluator + gate; verify runs in the runtime
```

## Example: workflow backend

From the repository root (requires Docker + built task image):

```bash
uv run python tests/agentic-use/runtimes/run_agent_eval.py \
  --task workspace-basic-cli-easy \
  --backend workflow \
  --skip-build
```

Programmatic use:

```python
from runtimes import AgenticEvalOrchestrator, NatWorkflowAttemptRuntime
from runtimes.shared.config import AgenticSharedConfig, WorkflowRuntimeConfig

runtime = NatWorkflowAttemptRuntime(
    WorkflowRuntimeConfig(shared=AgenticSharedConfig(nvidia_api_key=os.environ.get("NVIDIA_API_KEY")))
)
orchestrator = AgenticEvalOrchestrator(runtime)
result = await orchestrator.run_agent_eval("workspace-basic-cli-easy")
```

See [COMPLIANCE.md](./COMPLIANCE.md) for the full `nat_runner` → runtime mapping.

## Migration status

Backend runtimes (one class per `nat_runner --agent-backend`):

| Backend | Runtime class | Status |
|---------|---------------|--------|
| `workflow` | `NatWorkflowAttemptRuntime` | Implemented |
| `aut` | `AutAgentAttemptRuntime` | Implemented |
| `claude-code` | `ClaudeCodeAgentAttemptRuntime` | Scaffold |
| `codex` | `CodexAgentAttemptRuntime` | Scaffold |
| `cursor-agent` | `CursorAgentAttemptRuntime` | Scaffold |

Design-doc implementation path (see [COMPLIANCE.md](./COMPLIANCE.md) for detail):

| Phase | Item | Status |
|-------|------|--------|
| B1 | Wrap `nat_runner` as `AgentAttemptRuntime`(s) | In progress (workflow + aut done; 3 CLI backends scaffolded) |
| B2 | `EnvironmentProvider` boundary | Implemented |
| B3 | Standardize environment authoring | Implemented (minimal) |
| B4 | Productize results + CI (persistence, gating, provenance) | Implemented |

## B1 — `result.json` import

`shared/result_adapter.py` imports an existing `nat_runner` run as an attempt:

- `attempt_from_result_dir(output_dir)` reads `<output_dir>/result.json`.
- `attempt_from_result(result_dict, output_dir=...)` projects a parsed record.

The verifier outcome is scored by `VerifierRewardMetric` (compatibility metric)
rather than baked into the attempt status.

## B2 — Environment boundary

Runtimes execute the agent through `shared/environment.py`
(`AgentEnvironmentProvider` → `AgentEnvironmentHandle`) rather than calling
Docker directly. `DockerEnvironmentProvider` is the default; inject another
provider (local, Harbor, NeMo Gym) via the runtime's `environment=` argument
without changing backend code.

## B3 — Environment authoring

Tasks can declare a reusable environment instead of hand-writing a Dockerfile.
`shared/environment_spec.py` loads `environment.yaml` from the task dir:

```yaml
environment:
  image: nemo-platform-agentic-base:2026.06
  profile: evaluator-platform
  dependencies:
    python:
      - pytest
      - nemo-evaluator-sdk
  setup:
    - seed-providers
```

Dockerfile escape hatch:

```yaml
environment:
  dockerfile: environment/Dockerfile
```

`load_environment_spec` falls back to detecting `environment/Dockerfile` so
existing tasks keep working without a spec. `plan_task_build` resolves a spec to
a `BuildPlan` (image-based specs generate a minimal `FROM <image>` + `pip install`
Dockerfile); the orchestrator's BUILD step builds it. `setup` steps are recorded
as metadata, not executed here (they are runtime concerns).

## B4 — CI / reporting + gating

The SDK persists the run bundle (`tasks.jsonl`, `attempts.jsonl`,
`results.jsonl`, `summary.json`, `report.html`) when `output_dir` is set.
`shared/reporting.py` adds the gate on top:

```python
from runtimes.shared.reporting import GateThresholds, evaluate_gate, load_baseline_summary, write_gate_report

report = evaluate_gate(
    run_result,
    thresholds=GateThresholds(min_pass_rate=1.0, max_token_regression_pct=0.0),
    baseline_summary=load_baseline_summary("baseline/gate.json"),
)
write_gate_report(report, run_result.output_dir)  # -> gate.json
```

The orchestrator emits `gate.json` automatically (`AgenticOrchestratorConfig.write_gate`,
`gate_thresholds`, `baseline_summary_path`). Gate semantics match
`passrate_token_policy_gate.py`, so summaries are interchangeable as baselines.

## Live VERIFY phase (through the B2 boundary)

`shared/verify.py` runs the task-local `tests/test_outputs.py` pytest verifier
through `AgentEnvironmentHandle.run_verifier`, in the same prepared environment
and against the same persisted workspace/state as the agent phase. Enable it via
`AgenticSharedConfig(run_verify=True)`; the runtime stamps `reward`/`passed`/
`verify_status` onto the attempt metadata, and the orchestrator attaches
`VerifierRewardMetric` so the reward scores through the Evaluator SDK and feeds
the gate.

```python
runtime = NatWorkflowAttemptRuntime(
    WorkflowRuntimeConfig(shared=AgenticSharedConfig(run_verify=True)),
)
```

Tasks without a `tests/test_outputs.py` skip verification (the spec builder
returns `None`), matching `nat_runner` behavior.
