# Agentic-use AgentAttemptRuntime implementations

NeMo-Platform **adapter** over the generic agent-eval framework in
`nemo_evaluator_sdk.agent_eval`. The backend-agnostic building blocks (environment
boundary, gating, attempt/evidence helpers, orchestrator, verify mechanic,
coding-agent driver seam) now live in the SDK; this directory holds only the
NeMo-Platform glue (the `workflow`/`aut` backends, agentic task/result formats,
the pytest verifier, the platform Docker build/image-tag) plus a thin factory.

## Architecture: adapter over SDK

The backend-agnostic logic lives in `nemo_evaluator_sdk.agent_eval` and is
imported **directly** by the runtime scripts (no re-export shims). Everything
generic comes from these SDK homes:

| What | SDK home |
|------|----------|
| Docker CLI helpers | `agent_eval.runtimes.docker` |
| Environment boundary (`AgentEnvironmentProvider`/`Handle`, `EnvRunSpec`) | `agent_eval.runtimes.environment` |
| Environment authoring (`load_environment_spec`, `plan_task_build`, …) | `agent_eval.runtimes.environment_spec` |
| Gating (`GateThresholds`, `evaluate_gate`, `summarize_run`, …) | `agent_eval.gating` |
| Verify mechanic (`apply_verify_to_metadata`, `collect_verifier_outcome`) | `agent_eval.runtimes.verify` |
| `AgentPhaseSuccessMetric`, attempt-status + evidence helpers | `agent_eval.common_metrics`, `agent_eval.attempts` |
| Generic orchestrator + run layout | `agent_eval.orchestrator`, `agent_eval.runtimes.layout` |

All NeMo-Platform-specific glue is consolidated into a single module,
`shared/platform.py`: the run layout with the platform `state_dir`, the
`nmp-nat-<id>` image tag + `DockerEnvironmentProvider` default, the namespaced
`AgentPhaseSuccessMetric` + the `VerifierRewardMetric`, agent-log/usage parsing
and the shared container env, attempt construction (live + `result.json`), the
live VERIFY phase, and the agentic-use task loader.

The orchestrator (`orchestrator.py`) is a thin factory over
`agent_eval.orchestrator.AgentEvalOrchestrator`: it injects the platform image
build (`prepare_task`), the `run_verify`-derived `VerifierRewardMetric`
(`extra_metrics`), and the `result.json` `AgentAttemptSource`.

## Layout

```text
runtimes/
  shared/           # platform glue only:
                    #   platform.py  — all NeMo-Platform helpers (one file)
                    #   config.py    — runtime config dataclasses
                    #   constants.py — paths / container constants
  workflow/         # NatWorkflowAttemptRuntime (implemented, NeMo construct)
  aut/              # AutAgentAttemptRuntime (implemented, NeMo construct)
  claude_code/      # scaffold (stub) — see "Coding-agent runtimes" below
  codex/            # scaffold (stub)
  cursor_agent/     # scaffold (stub)
  orchestrator.py   # thin factory over agent_eval.orchestrator.AgentEvalOrchestrator
```

## Coding-agent runtimes (SDK driver seam)

Coding-agent CLIs plug into the SDK via
`agent_eval.runtimes.coding_agent`: `CliAgentDriver` (the reusable driver) +
`CodingAgentSpec` (per-agent command builder + trajectory→evidence parser).
Reference `ClaudeCodeSpec`/`CursorAgentSpec` are shipped. The profbench codex
runtime (`agent_eval.runtimes.codex`) remains a separate, standalone-CLI runtime.

The agentic-use `codex`/`claude_code`/`cursor_agent` backends here are still
stubs: wiring them to run the SDK driver *inside* the `nmp-agentic-base` Docker
environment (like `workflow`/`aut`) is bespoke per agent and a tracked follow-up.
`workflow` and `aut` stay in the adapter — they implement `AgentAttemptRuntime`
but are NeMo constructs, not general SDK runtimes.

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

## B1 — `result.json` import + stored-attempt scoring

`shared/platform.py` imports an existing `nat_runner` run as an attempt:

- `attempt_from_result_dir(output_dir)` reads `<output_dir>/result.json`.
- `attempt_from_result(result_dict, output_dir=...)` projects a parsed record.

Stored-attempt scoring is the SDK's first-class path. Score captured runs
without re-executing the agent (no Docker) via the orchestrator:

```python
await orchestrator.score_captured_attempts("my-task", result_dirs=["runs/abc"])
# or:  python run_agent_eval.py --task my-task --rescore-dir runs/abc
```

An agent that ran but failed maps to `status="partial"` (still scorable), not
`"failed"` — the SDK excludes `failed` from scoring, and a failed agent must
still count as a `0` for gating. The verifier outcome is scored by
`VerifierRewardMetric` (compatibility metric) rather than baked into the status.

Metrics are authored **on the task** (`agentic_task_from_dir` defaults to
`AgentPhaseSuccessMetric`); the orchestrator only *appends* `VerifierRewardMetric`
when `run_verify=True`. `inputs` holds only agent-facing `instruction`;
`task_dir` lives in `task.metadata`.

## B2 — Environment boundary

Runtimes execute the agent through the SDK environment boundary
(`AgentEnvironmentProvider` → `AgentEnvironmentHandle`) rather than calling
Docker directly. The platform `DockerEnvironmentProvider` (`shared/platform.py`,
defaulting to the `nmp-nat-<id>` image tag) is the default; inject another
provider (local, Harbor, NeMo Gym) via the runtime's `environment=` argument
without changing backend code.

## B3 — Environment authoring

Tasks can declare a reusable environment instead of hand-writing a Dockerfile.
`agent_eval.runtimes.environment_spec` loads `environment.yaml` from the task dir:

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
`agent_eval.gating` adds the gate on top:

```python
from nemo_evaluator_sdk.agent_eval.gating import GateThresholds, evaluate_gate, load_baseline_summary, write_gate_report

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

`shared/platform.py` runs the task-local `tests/test_outputs.py` pytest verifier
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
