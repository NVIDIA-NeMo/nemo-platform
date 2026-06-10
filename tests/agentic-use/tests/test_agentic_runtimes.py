# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for agentic-use AgentAttemptRuntime implementations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from runtimes.shared.config import AgenticSharedConfig, WorkflowRuntimeConfig
from runtimes.shared.environment import EnvCommandResult, EnvRunSpec
from runtimes.shared.layout import resolve_run_layout, task_image_tag
from runtimes.shared.task_loader import agentic_task_from_dir
from runtimes.workflow.command import build_workflow_agent_cmd
from runtimes.workflow.prep import prepare_workflow_for_runtime
from runtimes.workflow.runtime import NatWorkflowAttemptRuntime

TASKS_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_BASIC = TASKS_DIR / "workspace-basic-cli-easy"


def test_build_workflow_agent_cmd_matches_nat_runner_shape() -> None:
    cmd = build_workflow_agent_cmd("/tmp/nat_workflow.yml", "/tmp/nat_instruction.md")
    assert cmd[0] == "bash"
    assert "nat run" in cmd[2]
    assert "/tmp/nat_workflow.yml" in cmd[2]
    assert "intermediate_steps.jsonl" in cmd[2]


def test_prepare_workflow_for_runtime_injects_trace_exporter(tmp_path: Path) -> None:
    workflow_path = WORKSPACE_BASIC / "workflow.yml"
    prepared = prepare_workflow_for_runtime(
        workflow_path,
        tmp_path,
        "http://platform.test:9090",
        nat_model="test/model",
    )
    config = yaml.safe_load(prepared.read_text(encoding="utf-8"))
    tracing = config["general"]["telemetry"]["tracing"]
    assert tracing["agentic_use_file_trace"]["output_path"] == "/logs/agent/intermediate_steps.jsonl"
    assert "http://platform.test:9090" in prepared.read_text(encoding="utf-8")


def test_agentic_task_from_dir_loads_instruction() -> None:
    task = agentic_task_from_dir(WORKSPACE_BASIC, tasks_root=TASKS_DIR)
    assert task.id == "workspace-basic-cli-easy"
    assert "workspace" in task.intent.lower()
    # inputs stays agent-facing; runtime materialization (task_dir) lives in metadata.
    assert task.inputs == {"instruction": task.intent}
    assert task.metadata["task_dir"] == str(WORKSPACE_BASIC.resolve())
    # metrics are authored on the task, not injected by the orchestrator.
    assert [metric.type for metric in task.metrics] == ["agentic_use_agent_phase"]


class _FakeEnvHandle:
    def __init__(self, captured: dict[str, object], on_run: Callable[[EnvRunSpec], None] | None = None) -> None:
        self._captured = captured
        self._on_run = on_run

    async def run_agent(self, spec: EnvRunSpec) -> EnvCommandResult:
        self._captured["command"] = spec.command
        self._captured["env"] = spec.env
        self._captured["mounts"] = spec.mounts
        if self._on_run is not None:
            self._on_run(spec)
        return EnvCommandResult(exit_code=0)

    async def run_verifier(self, spec: EnvRunSpec) -> EnvCommandResult:
        return EnvCommandResult(exit_code=0)

    async def close(self) -> None:
        return None


class _FakeEnvProvider:
    def __init__(self, captured: dict[str, object], on_run: Callable[[EnvRunSpec], None] | None = None) -> None:
        self._captured = captured
        self._on_run = on_run

    async def prepare(self, task: object, config: object = None) -> _FakeEnvHandle:
        self._captured["image"] = task_image_tag(task.id)  # type: ignore[attr-defined]
        return _FakeEnvHandle(self._captured, self._on_run)


@pytest.mark.asyncio
async def test_workflow_runtime_run_tasks_with_mocked_env(tmp_path: Path) -> None:
    task = agentic_task_from_dir(WORKSPACE_BASIC, tasks_root=TASKS_DIR)
    layout = resolve_run_layout(task, AgenticSharedConfig(jobs_dir=tmp_path))
    captured: dict[str, object] = {}

    def write_log(_spec: EnvRunSpec) -> None:
        (layout.agent_log_dir / "nat_agent.log").write_text('{"usage":{"input_tokens":1,"output_tokens":2}}')

    runtime = NatWorkflowAttemptRuntime(
        WorkflowRuntimeConfig(shared=AgenticSharedConfig(jobs_dir=tmp_path)),
        environment=_FakeEnvProvider(captured, on_run=write_log),
    )
    attempts = await runtime.run_tasks([task.model_copy(update={"inputs": {**task.inputs}})])

    assert len(attempts) == 1
    assert attempts[0].metadata["agent_ok"] is True
    assert attempts[0].metadata["agent_runtime"] == "workflow"
    assert captured["image"] == "nmp-nat-workspace-basic-cli-easy:latest"
    assert "nat run" in captured["command"][2]  # type: ignore[index]


def test_runtime_for_backend_selects_workflow() -> None:
    from runtimes import runtime_for_backend

    runtime = runtime_for_backend("workflow")
    assert isinstance(runtime, NatWorkflowAttemptRuntime)


def test_runtime_for_backend_selects_codex_wrapper() -> None:
    from runtimes import runtime_for_backend
    from runtimes.codex.runtime import CodexAgentAttemptRuntime

    runtime = runtime_for_backend("codex", backend_kwargs={"agent_model": "gpt-test"})
    assert isinstance(runtime, CodexAgentAttemptRuntime)
    assert runtime.config.agent_model == "gpt-test"


def test_runtime_for_backend_rejects_unknown() -> None:
    from runtimes import runtime_for_backend

    with pytest.raises(ValueError, match="Unsupported"):
        runtime_for_backend("unknown-backend")


def test_build_agent_eval_attempt_metadata_matches_captured_schema(tmp_path: Path) -> None:
    from runtimes.shared.artifacts import build_agent_eval_attempt, to_captured_agent_attempt
    from runtimes.shared.layout import AgenticRunLayout

    task = agentic_task_from_dir(WORKSPACE_BASIC, tasks_root=TASKS_DIR)
    layout = AgenticRunLayout(
        run_dir=tmp_path,
        agent_log_dir=tmp_path / "agent",
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        instruction_path=tmp_path / "agent" / "instruction.md",
    )
    layout.agent_log_dir.mkdir(parents=True)
    (layout.agent_log_dir / "nat_agent.log").write_text("done", encoding="utf-8")

    attempt = build_agent_eval_attempt(
        task=task,
        layout=layout,
        runtime_name="workflow",
        agent_model="test-model",
        exit_code=0,
        agent_ok=True,
        run_id="run-1",
    )
    captured = to_captured_agent_attempt(task, attempt)

    assert attempt.metadata["agent_runtime"] == "workflow"
    assert attempt.metadata["agent_model"] == "test-model"
    assert captured.metadata.agent_runtime == "workflow"
    assert captured.metadata.agent_model == "test-model"
    assert captured.metadata.run_id == "run-1"

    # Evidence keys must follow the documented nat_runner -> AgentEvalAttempt map.
    assert attempt.evidence is not None
    evidence_names = set(attempt.evidence.descriptors)
    assert {"logs", "final_state", "state"} <= evidence_names
    assert attempt.evidence.descriptors["final_state"].metadata["role"] == "final_state"
    assert attempt.evidence.descriptors["logs"].ref == str(layout.agent_log_dir)


@pytest.mark.asyncio
async def test_codex_runtime_delegates_to_sdk_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalTask, AgentOutput
    from runtimes.codex import runtime as codex_runtime
    from runtimes.shared.config import CodexRuntimeConfig

    captured: dict[str, object] = {}

    class FakeSdkCodexCliAgentRuntime:
        def __init__(self, *, model: str | None = None) -> None:
            captured["model"] = model

        async def run_tasks(self, tasks: list[AgentEvalTask], config: object = None) -> list[AgentEvalAttempt]:
            captured["tasks"] = tasks
            captured["config"] = config
            return [
                AgentEvalAttempt(
                    id="task-1:codex",
                    task_id="task-1",
                    output=AgentOutput(text="answer"),
                )
            ]

    monkeypatch.setattr(codex_runtime, "SdkCodexCliAgentRuntime", FakeSdkCodexCliAgentRuntime)

    runtime = codex_runtime.CodexAgentAttemptRuntime(CodexRuntimeConfig(agent_model="gpt-test"))
    task = AgentEvalTask(id="task-1", intent="answer", inputs={})
    attempts = await runtime.run_tasks([task], config="config")  # type: ignore[arg-type]

    assert captured["model"] == "gpt-test"
    assert captured["tasks"] == [task]
    assert captured["config"] == "config"
    assert attempts[0].output is not None
    assert attempts[0].output.text == "answer"


def test_codex_runtime_uses_docker_delegate_with_auth_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from runtimes.codex import runtime as codex_runtime
    from runtimes.shared.config import CodexRuntimeConfig

    captured: dict[str, object] = {}

    class FakeSdkCodexDockerCliAgentRuntime:
        def __init__(self, *, model: str | None = None, auth_path: Path | None = None) -> None:
            captured["model"] = model
            captured["auth_path"] = auth_path

        async def run_tasks(self, tasks: list[object], config: object = None) -> list[object]:
            return []

    monkeypatch.setattr(codex_runtime, "SdkCodexDockerCliAgentRuntime", FakeSdkCodexDockerCliAgentRuntime)
    auth_path = tmp_path / "auth.json"

    runtime = codex_runtime.CodexAgentAttemptRuntime(
        CodexRuntimeConfig(agent_model="gpt-test", codex_auth_json=auth_path)
    )

    assert runtime.config.codex_auth_json == auth_path
    assert captured == {"model": "gpt-test", "auth_path": auth_path}


@pytest.mark.asyncio
async def test_aut_runtime_run_tasks_with_mocked_env(tmp_path: Path) -> None:
    from runtimes.aut.runtime import AutAgentAttemptRuntime
    from runtimes.shared.config import AutRuntimeConfig

    task = agentic_task_from_dir(WORKSPACE_BASIC, tasks_root=TASKS_DIR)
    captured: dict[str, object] = {}

    runtime = AutAgentAttemptRuntime(
        AutRuntimeConfig(
            shared=AgenticSharedConfig(jobs_dir=tmp_path),
            aut_agent_name="test-agent",
        ),
        environment=_FakeEnvProvider(captured),
    )
    attempts = await runtime.run_tasks([task])
    assert attempts[0].metadata["agent_runtime"] == "aut"
    assert attempts[0].metadata["agent_ok"] is True
    assert captured["env"]["AUT_AGENT_NAME"] == "test-agent"  # type: ignore[index]


def test_profbench_runtime_task_metadata_points_to_shared_env() -> None:
    from nemo_evaluator_sdk.agent_eval.types import AgentEvalTask
    from runtimes import profbench as profbench_runtime

    task = AgentEvalTask(id="profbench-row-1", intent="answer", inputs={"prompt": "answer"})
    runtime_task = profbench_runtime._profbench_runtime_task(task)

    assert runtime_task.metadata["task_dir"] == str(profbench_runtime.PROFBENCH_TASK_DIR.resolve())
    assert runtime_task.metadata["instruction_path"] == str(
        (profbench_runtime.PROFBENCH_TASK_DIR / "instruction.md").resolve()
    )
    assert runtime_task.metadata["agentic_use_run_subdir"] == "agent-runtime/profbench-row-1"


def test_profbench_output_dir_resolves_to_absolute_path(tmp_path: Path) -> None:
    from runtimes import profbench as profbench_runtime

    output_dir, run_id = profbench_runtime._resolve_profbench_run(tmp_path / "runs", "run-1")

    assert run_id == "run-1"
    assert output_dir == (tmp_path / "runs" / "run-1").resolve()
    assert output_dir.is_absolute()


@pytest.mark.asyncio
async def test_profbench_target_uses_single_shared_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_evaluator_sdk.agent_eval.types import AgentEvalTask
    from runtimes import profbench as profbench_runtime

    built: list[str] = []

    def fake_execute_build_plan(plan: object) -> None:
        built.append(plan.image_tag)  # type: ignore[attr-defined]

    class FakeTarget:
        environment: object = object()

    monkeypatch.setattr(profbench_runtime, "execute_build_plan", fake_execute_build_plan)

    target = profbench_runtime._prepare_target(FakeTarget(), skip_build=False)
    handle = await target.environment.prepare(AgentEvalTask(id="dataset-row", intent="answer", inputs={}))  # type: ignore[attr-defined]

    assert built == [profbench_runtime.PROFBENCH_IMAGE_TAG]
    assert handle.image == profbench_runtime.PROFBENCH_IMAGE_TAG


@pytest.mark.asyncio
async def test_run_agent_eval_routes_profbench_to_benchmark_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from nemo_evaluator_sdk.agent_eval import AgentEvalBenchmarkReports
    from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunResult, AgentEvalSummary
    from nemo_evaluator_sdk.values import Model, RunConfigOnlineModel
    from runtimes import run_agent_eval

    captured: dict[str, object] = {}

    def fake_runtime_for_backend(backend: str, **kwargs: object) -> object:
        raise AssertionError(f"ProfBench workflow must not load NAT runtime: {backend}, {kwargs}")

    async def fake_run_profbench_agent_eval(**kwargs: object) -> tuple[AgentEvalRunResult, AgentEvalBenchmarkReports]:
        captured["profbench_kwargs"] = kwargs
        return (
            AgentEvalRunResult(
                run_id="run-1",
                tasks=[],
                attempts=[],
                results=[],
                summary=AgentEvalSummary(),
            ),
            AgentEvalBenchmarkReports(paths=[tmp_path / "sdk-report.html", tmp_path / "report.html"]),
        )

    monkeypatch.setattr(run_agent_eval, "runtime_for_backend", fake_runtime_for_backend)
    monkeypatch.setattr(run_agent_eval, "run_profbench_agent_eval", fake_run_profbench_agent_eval)

    exit_code = await run_agent_eval._main(
        [
            "--task",
            "profbench",
            "--backend",
            "workflow",
            "--model",
            "meta/test",
            "--limit",
            "1",
            "--allow-dirty",
        ]
    )

    assert exit_code == 0
    kwargs = captured["profbench_kwargs"]
    target = kwargs["target"]
    assert isinstance(target, Model)
    assert target.name == "meta/test"
    assert isinstance(kwargs["params"], RunConfigOnlineModel)  # type: ignore[index]
    assert kwargs["params"].inference.max_tokens == run_agent_eval.DEFAULT_PROFBENCH_CANDIDATE_MAX_TOKENS  # type: ignore[index,union-attr]
    assert kwargs["config"].limit == 1  # type: ignore[index,union-attr]
    assert kwargs["config"].judge_api_key_env == "NVIDIA_API_KEY"  # type: ignore[index,union-attr]


@pytest.mark.asyncio
async def test_run_agent_eval_routes_profbench_codex_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from nemo_evaluator_sdk.agent_eval import AgentEvalBenchmarkReports
    from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunResult, AgentEvalSummary
    from runtimes import run_agent_eval

    captured: dict[str, object] = {}
    fake_runtime = object()

    def fake_runtime_for_backend(backend: str, **kwargs: object) -> object:
        captured["backend"] = backend
        captured["runtime_kwargs"] = kwargs
        return fake_runtime

    async def fake_run_profbench_agent_eval(**kwargs: object) -> tuple[AgentEvalRunResult, AgentEvalBenchmarkReports]:
        captured["profbench_kwargs"] = kwargs
        return (
            AgentEvalRunResult(
                run_id="run-1",
                tasks=[],
                attempts=[],
                results=[],
                summary=AgentEvalSummary(),
            ),
            AgentEvalBenchmarkReports(paths=[tmp_path / "sdk-report.html", tmp_path / "report.html"]),
        )

    monkeypatch.setattr(run_agent_eval, "runtime_for_backend", fake_runtime_for_backend)
    monkeypatch.setattr(run_agent_eval, "run_profbench_agent_eval", fake_run_profbench_agent_eval)

    exit_code = await run_agent_eval._main(
        [
            "--task",
            "profbench",
            "--backend",
            "codex",
            "--agent-model",
            "gpt-test",
            "--limit",
            "1",
        ]
    )

    assert exit_code == 0
    assert captured["backend"] == "codex"
    assert captured["profbench_kwargs"]["target"] is fake_runtime  # type: ignore[index]
    assert captured["profbench_kwargs"]["params"] is None  # type: ignore[index]


@pytest.mark.asyncio
async def test_run_agent_eval_keeps_non_profbench_orchestrator_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunResult, AgentEvalSummary
    from runtimes import run_agent_eval

    captured: dict[str, object] = {}
    fake_runtime = object()

    def fake_runtime_for_backend(backend: str, **kwargs: object) -> object:
        captured["backend"] = backend
        return fake_runtime

    class FakeOrchestrator:
        def __init__(self, runtime: object, *, config: object) -> None:
            captured["runtime"] = runtime
            captured["orchestrator_config"] = config

        async def run_agent_eval(self, task: str, *, output_dir: Path | None = None) -> AgentEvalRunResult:
            captured["task"] = task
            captured["output_dir"] = output_dir
            return AgentEvalRunResult(
                run_id="run-1",
                tasks=[],
                attempts=[],
                results=[],
                summary=AgentEvalSummary(),
            )

    monkeypatch.setattr(run_agent_eval, "runtime_for_backend", fake_runtime_for_backend)
    monkeypatch.setattr(run_agent_eval, "AgenticEvalOrchestrator", FakeOrchestrator)

    exit_code = await run_agent_eval._main(
        ["--task", "workspace-basic-cli-easy", "--backend", "workflow"]
    )

    assert exit_code == 0
    assert captured["backend"] == "workflow"
    assert captured["runtime"] is fake_runtime
    assert captured["task"] == "workspace-basic-cli-easy"


def test_attempt_from_result_maps_status_and_measurements(tmp_path: Path) -> None:
    from runtimes.shared.result_adapter import attempt_from_result

    output_dir = tmp_path / "20260101T000000Z-demo"
    (output_dir / "agent").mkdir(parents=True)
    (output_dir / "workspace").mkdir()
    (output_dir / "state").mkdir()
    (output_dir / "agent" / "nat_agent.log").write_text("final answer", encoding="utf-8")
    result = {
        "task": "demo",
        "agent_backend": "workflow",
        "agent_model": "test-model",
        "agent": "ok",
        "verify": "ok",
        "passed": True,
        "reward": 1,
        "runtime_sec": 12.5,
        "metrics": {"total_tokens": 42, "duration_ms": 900, "token_metrics_status": "available"},
        "provenance": {"run_id": "run-9", "commit": "abc123"},
        "candidate_id": "cand-1",
    }

    attempt = attempt_from_result(result, output_dir=output_dir)

    assert attempt.task_id == "demo"
    assert attempt.status == "completed"
    assert attempt.metadata["reward"] == 1
    assert attempt.metadata["passed"] is True
    assert attempt.metadata["total_tokens"] == 42
    assert attempt.metadata["run_id"] == "run-9"
    assert attempt.metadata["candidate_id"] == "cand-1"
    assert attempt.evidence is not None
    assert {"logs", "final_state", "state"} <= set(attempt.evidence.descriptors)


def test_attempt_from_result_marks_unsuccessful_agent_partial(tmp_path: Path) -> None:
    from runtimes.shared.result_adapter import attempt_from_result

    output_dir = tmp_path / "run"
    (output_dir / "agent").mkdir(parents=True)
    result = {"task": "demo", "agent_backend": "aut", "agent": "failed", "passed": False, "reward": 0}

    attempt = attempt_from_result(result, output_dir=output_dir)
    # An agent that ran but failed stays *scorable* ("partial"); the SDK excludes
    # "failed" from scoring, so we reserve it for true production failures.
    assert attempt.status == "partial"
    assert attempt.metadata["agent_ok"] is False
    assert attempt.output is not None


@pytest.mark.asyncio
async def test_score_captured_attempts_offline(tmp_path: Path) -> None:
    import json

    from runtimes.orchestrator import AgenticEvalOrchestrator
    from runtimes.workflow.runtime import NatWorkflowAttemptRuntime

    run_dir = tmp_path / "run"
    (run_dir / "agent").mkdir(parents=True)
    (run_dir / "workspace").mkdir()
    (run_dir / "agent" / "nat_agent.log").write_text("done", encoding="utf-8")
    (run_dir / "result.json").write_text(
        json.dumps(
            {
                "task": WORKSPACE_BASIC.name,
                "agent_backend": "workflow",
                "agent": "ok",
                "passed": True,
                "reward": 1,
                "metrics": {"total_tokens": 10},
            }
        ),
        encoding="utf-8",
    )

    orchestrator = AgenticEvalOrchestrator(
        NatWorkflowAttemptRuntime(WorkflowRuntimeConfig(shared=AgenticSharedConfig(jobs_dir=tmp_path))),
    )
    # Stored-attempt path: no Docker / agent execution, scores result.json directly.
    result = await orchestrator.score_captured_attempts(WORKSPACE_BASIC.name, result_dirs=[run_dir])

    assert [metric.type for metric in result.tasks[0].metrics] == ["agentic_use_agent_phase"]
    assert result.attempts[0].status == "completed"
    assert any(r.metric_type == "agentic_use_agent_phase" for r in result.results)


@pytest.mark.asyncio
async def test_verifier_reward_metric_reads_metadata() -> None:
    from nemo_evaluator_sdk.metrics.protocol import CandidateOutput, DatasetRow, MetricInput
    from runtimes.shared.metrics import VerifierRewardMetric

    metric = VerifierRewardMetric()
    candidate = CandidateOutput(output_text="x", metadata={"reward": 1})
    result = await metric.compute_scores(MetricInput(row=DatasetRow(data={}), candidate=candidate))
    assert result.outputs[0].value == 1.0


def _make_run_result(*, reward: float, total_tokens: int, runtime_sec: float, commit: str = "abc123"):
    from nemo_evaluator_sdk.agent_eval.types import (
        AgentEvalAttempt,
        AgentEvalRunResult,
        AgentEvalSummary,
        AgentEvalTask,
        AgentEvalTaskResult,
        AgentOutput,
    )
    from nemo_evaluator_sdk.metrics.protocol import MetricOutput

    task = AgentEvalTask(id="demo", intent="do it", inputs={})
    attempt = AgentEvalAttempt(
        id="demo:workflow",
        task_id="demo",
        status="completed",
        output=AgentOutput(text="ok"),
        metadata={
            "total_tokens": total_tokens,
            "runtime_sec": runtime_sec,
            "provenance": {"commit_sha": commit, "commit_short": commit[:7]},
        },
    )
    task_result = AgentEvalTaskResult(
        id="result-1",
        run_id="run-1",
        task_id="demo",
        attempt_id="demo:workflow",
        metric_type="agentic_use_verifier_reward",
        outputs=[MetricOutput(name="verifier_reward", value=reward)],
    )
    return AgentEvalRunResult(
        run_id="run-1",
        tasks=[task],
        attempts=[attempt],
        results=[task_result],
        summary=AgentEvalSummary(),
    )


def test_summarize_run_aggregates_pass_tokens_runtime_provenance() -> None:
    from runtimes.shared.reporting import summarize_run

    summary = summarize_run(_make_run_result(reward=1.0, total_tokens=120, runtime_sec=4.5))

    assert summary["total_tasks"] == 1
    assert summary["pass_rate"] == 1.0
    assert summary["total_tokens_sum"] == 120
    assert summary["runtime_sec_sum"] == 4.5
    assert summary["token_metrics_coverage"] == 1.0
    assert summary["provenance"]["commit_sha"] == "abc123"


def test_evaluate_gate_passes_then_flags_token_regression(tmp_path: Path) -> None:
    from runtimes.shared.reporting import GateThresholds, evaluate_gate, write_gate_report

    baseline = _make_run_result(reward=1.0, total_tokens=100, runtime_sec=4.0)
    candidate = _make_run_result(reward=1.0, total_tokens=200, runtime_sec=4.0)

    baseline_report = evaluate_gate(baseline, thresholds=GateThresholds())
    assert baseline_report.gate_passed is True

    candidate_report = evaluate_gate(
        candidate,
        thresholds=GateThresholds(),
        baseline_summary=baseline_report.summary,
    )
    assert candidate_report.gate_passed is False
    token_check = next(c for c in candidate_report.checks if c.name == "tokens_not_worse_than_baseline")
    assert token_check.passed is False

    gate_path = write_gate_report(candidate_report, tmp_path)
    assert gate_path.exists()
    assert "gate_passed" in gate_path.read_text(encoding="utf-8")


def test_evaluate_gate_blocks_cross_commit_comparison() -> None:
    from runtimes.shared.reporting import GateThresholds, evaluate_gate

    baseline = _make_run_result(reward=1.0, total_tokens=100, runtime_sec=4.0, commit="aaa111")
    candidate = _make_run_result(reward=1.0, total_tokens=100, runtime_sec=4.0, commit="bbb222")

    baseline_summary = evaluate_gate(baseline, thresholds=GateThresholds()).summary
    report = evaluate_gate(candidate, thresholds=GateThresholds(), baseline_summary=baseline_summary)

    cross = next(c for c in report.checks if c.name == "commit_sha_matches_baseline")
    assert cross.passed is False
    assert report.gate_passed is False

    allowed = evaluate_gate(
        candidate,
        thresholds=GateThresholds(allow_cross_commit=True),
        baseline_summary=baseline_summary,
    )
    cross_allowed = next(c for c in allowed.checks if c.name == "commit_sha_matches_baseline")
    assert cross_allowed.passed is True


def test_build_verify_run_spec_shape(tmp_path: Path) -> None:
    from runtimes.shared.layout import AgenticRunLayout
    from runtimes.shared.verify import build_verify_run_spec

    layout = AgenticRunLayout(
        run_dir=tmp_path,
        agent_log_dir=tmp_path / "agent",
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        instruction_path=tmp_path / "agent" / "instruction.md",
    )
    spec = build_verify_run_spec(
        WORKSPACE_BASIC,
        layout,
        nmp_base_url="http://platform.test:8080",
        agent_backend="workflow",
        agent_model="test-model",
    )
    assert spec is not None
    assert spec.command[0] == "bash"
    assert "pytest /tests/test_outputs.py" in spec.command[2]
    assert spec.env["NAT_AGENT_BACKEND"] == "workflow"
    assert (str(WORKSPACE_BASIC / "tests"), "/tests") in spec.mounts
    assert (tmp_path / "verifier").exists()


def test_build_verify_run_spec_returns_none_without_tests(tmp_path: Path) -> None:
    from runtimes.shared.layout import AgenticRunLayout
    from runtimes.shared.verify import build_verify_run_spec

    task_dir = tmp_path / "no-tests-task"
    task_dir.mkdir()
    layout = AgenticRunLayout(
        run_dir=tmp_path / "run",
        agent_log_dir=tmp_path / "run" / "agent",
        workspace_dir=tmp_path / "run" / "workspace",
        state_dir=tmp_path / "run" / "state",
        instruction_path=tmp_path / "run" / "agent" / "instruction.md",
    )
    spec = build_verify_run_spec(task_dir, layout, nmp_base_url="x", agent_backend="aut", agent_model="m")
    assert spec is None


@pytest.mark.asyncio
async def test_run_verify_reads_reward_file(tmp_path: Path) -> None:
    from runtimes.shared.environment import EnvCommandResult, EnvRunSpec
    from runtimes.shared.layout import AgenticRunLayout
    from runtimes.shared.verify import run_verify

    layout = AgenticRunLayout(
        run_dir=tmp_path,
        agent_log_dir=tmp_path / "agent",
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "state",
        instruction_path=tmp_path / "agent" / "instruction.md",
    )
    (tmp_path / "verifier").mkdir()

    class _Handle:
        async def run_agent(self, spec: EnvRunSpec) -> EnvCommandResult:
            return EnvCommandResult(exit_code=0)

        async def run_verifier(self, spec: EnvRunSpec) -> EnvCommandResult:
            (tmp_path / "verifier" / "reward.txt").write_text("1\n")
            (tmp_path / "verifier" / "test-stdout.txt").write_text("PASSED")
            return EnvCommandResult(exit_code=0)

        async def close(self) -> None:
            return None

    outcome = await run_verify(_Handle(), EnvRunSpec(command=["bash"]), layout)
    assert outcome.ran is True
    assert outcome.passed is True
    assert outcome.reward == 1
    assert "PASSED" in outcome.stdout


@pytest.mark.asyncio
async def test_workflow_runtime_runs_verify_through_handle(tmp_path: Path) -> None:
    from runtimes.shared.verify import verifier_log_dir

    task = agentic_task_from_dir(WORKSPACE_BASIC, tasks_root=TASKS_DIR)
    layout = resolve_run_layout(task, AgenticSharedConfig(jobs_dir=tmp_path))
    phases: list[str] = []

    class _Handle:
        async def run_agent(self, spec: EnvRunSpec) -> EnvCommandResult:
            phases.append("agent")
            (layout.agent_log_dir / "nat_agent.log").write_text("ok")
            return EnvCommandResult(exit_code=0)

        async def run_verifier(self, spec: EnvRunSpec) -> EnvCommandResult:
            phases.append("verify")
            (verifier_log_dir(layout) / "reward.txt").write_text("1\n")
            return EnvCommandResult(exit_code=0)

        async def close(self) -> None:
            return None

    class _Provider:
        async def prepare(self, task: object, config: object = None) -> _Handle:
            return _Handle()

    runtime = NatWorkflowAttemptRuntime(
        WorkflowRuntimeConfig(shared=AgenticSharedConfig(jobs_dir=tmp_path, run_verify=True)),
        environment=_Provider(),
    )
    attempts = await runtime.run_tasks([task.model_copy(update={"inputs": {**task.inputs}})])

    assert phases == ["agent", "verify"]
    assert attempts[0].metadata["verify_status"] == "ok"
    assert attempts[0].metadata["reward"] == 1
    assert attempts[0].metadata["passed"] is True


def test_load_environment_spec_prefers_yaml(tmp_path: Path) -> None:
    from runtimes.shared.environment_spec import load_environment_spec

    (tmp_path / "environment.yaml").write_text(
        "environment:\n"
        "  image: nemo-agentic-base:2026.06\n"
        "  profile: evaluator-platform\n"
        "  dependencies:\n"
        "    python:\n"
        "      - pytest\n"
        "      - nemo-evaluator-sdk\n"
        "  setup:\n"
        "    - seed-providers\n",
        encoding="utf-8",
    )
    spec = load_environment_spec(tmp_path)
    assert spec.image == "nemo-agentic-base:2026.06"
    assert spec.profile == "evaluator-platform"
    assert spec.python_dependencies == ["pytest", "nemo-evaluator-sdk"]
    assert spec.setup == ["seed-providers"]
    assert spec.dockerfile is None


def test_load_environment_spec_falls_back_to_dockerfile(tmp_path: Path) -> None:
    from runtimes.shared.environment_spec import load_environment_spec

    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    (env_dir / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    spec = load_environment_spec(tmp_path)
    assert spec.dockerfile == env_dir / "Dockerfile"
    assert spec.image is None


def test_load_environment_spec_missing_raises(tmp_path: Path) -> None:
    from runtimes.shared.environment_spec import load_environment_spec

    with pytest.raises(FileNotFoundError):
        load_environment_spec(tmp_path)


def test_plan_task_build_dockerfile_escape_hatch(tmp_path: Path) -> None:
    from runtimes.shared.environment_spec import plan_task_build

    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    (env_dir / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    plan = plan_task_build(tmp_path, "task-img:latest")
    assert plan.generated is False
    assert plan.dockerfile == env_dir / "Dockerfile"
    assert plan.context_dir == env_dir
    assert plan.image_tag == "task-img:latest"


def test_plan_task_build_generates_derived_dockerfile(tmp_path: Path) -> None:
    from runtimes.shared.environment_spec import plan_task_build

    (tmp_path / "environment.yaml").write_text(
        "environment:\n  image: base:1\n  dependencies:\n    python: [pytest]\n  setup: [seed-providers]\n",
        encoding="utf-8",
    )
    generated = tmp_path / "build"
    plan = plan_task_build(tmp_path, "task-img:latest", generated_dir=generated)

    assert plan.generated is True
    assert plan.base_image == "base:1"
    assert plan.setup == ["seed-providers"]
    content = plan.dockerfile.read_text(encoding="utf-8")
    assert content.startswith("FROM base:1")
    assert "pip install --no-cache-dir pytest" in content
