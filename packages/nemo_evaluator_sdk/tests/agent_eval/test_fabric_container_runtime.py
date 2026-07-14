# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for FabricContainerRuntime over a fake sandbox provider.

No real Docker or image: a fake provider records the marshaled inputs and simulates the
in-container ``/out`` layout on ``download_dir``, so we can assert the evidence contract
(keys/kinds) and the success/failure/isolation paths the metrics depend on.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.fabric import container_runtime as crt
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.container_runtime import FabricContainerRuntime
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.base import (
    SandboxExecResult,
    SandboxHandle,
    SandboxSpec,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus
from nemo_evaluator_sdk.values.common import SecretRef

_CONFIG = {"metadata": {"name": "eval"}, "harness": {"adapter_id": "nvidia.fabric.hermes.sdk"}}


@pytest.fixture(autouse=True)
def _stub_image_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never build a real image in unit tests; the runtime asks for one per run."""
    monkeypatch.setattr(crt, "ensure_fabric_image", lambda **_kwargs: "fabric-img:test")


class _FakeResolver:
    """Resolves any SecretRef to a fixed value."""

    def __init__(self, value: str = "resolved-secret") -> None:
        self._value = value

    async def resolve_secret(self, secret_ref: SecretRef) -> str:
        return self._value


class _FakeProvider:
    """Simulates a sandbox: records seeds/uploads/execs, materializes /out on download."""

    name = "fake"

    def __init__(
        self,
        *,
        status: str = "succeeded",
        error_type: str | None = None,
        return_code: int = 0,
        write_result: bool = True,
        result_bytes: bytes | None = None,
        atif: bool = True,
    ) -> None:
        self._status = status
        self._error_type = error_type  # exec sandbox-runtime failure (e.g. "timeout")
        self._return_code = return_code
        self._write_result = write_result  # False => the CLI crashed before writing a RunResult
        self._result_bytes = result_bytes  # raw override for fabric_result.json (non-object / binary)
        self._atif = atif
        self.seeded: dict[str, str] = {}
        self.env: dict[str, str] = {}
        self.uploaded_dirs: list[tuple[Path, str]] = []
        self.execs: list[str] = []
        self.closed = 0
        self.aclosed = 0

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        self.seeded = dict(spec.files)
        self.env = dict(spec.env)
        return SandboxHandle(sandbox_id="fake-1", provider_name=self.name, raw=None)

    async def exec(self, handle: SandboxHandle, command: str, **kwargs: object) -> SandboxExecResult:
        self.execs.append(command)
        stderr = "stderr-boom" if (self._return_code or self._error_type) else ""
        return SandboxExecResult(stdout="", stderr=stderr, return_code=self._return_code, error_type=self._error_type)

    async def upload_file(self, handle: SandboxHandle, source_path: Path, target_path: str) -> None:
        return None

    async def upload_dir(self, handle: SandboxHandle, source_dir: Path, target_dir: str) -> None:
        self.uploaded_dirs.append((source_dir, target_dir))

    async def download_dir(self, handle: SandboxHandle, source_dir: str, target_dir: Path) -> None:
        # Materialize the /out layout `fabric run` would have produced.
        out = target_dir
        (out / "workspace").mkdir(parents=True, exist_ok=True)
        (out / "logs").mkdir(parents=True, exist_ok=True)
        (out / "logs" / "fabric-stderr.txt").write_text("stderr-boom", encoding="utf-8")
        if self._result_bytes is not None:  # raw override: non-object JSON, or non-UTF-8 garbage
            (out / "fabric_result.json").write_bytes(self._result_bytes)
            return
        if not self._write_result:  # crashed CLI wrote no RunResult
            return
        (out / "workspace" / "fib.py").write_text("def fib(n): return n", encoding="utf-8")
        envelope = {
            "status": self._status,
            "output": {"response": "fixed the bug"},
            "error": None if self._status == "succeeded" else {"stage": "run", "code": "E", "message": "nope"},
        }
        (out / "fabric_result.json").write_text(json.dumps(envelope), encoding="utf-8")
        if self._atif:
            # Relay nests the trajectory under a per-run subdir, as the live gateway does.
            run_dir = out / "relay" / "runtime-123-4"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "trajectory-abc.atif.json").write_text('{"steps": []}', encoding="utf-8")

    async def download_file(self, handle: SandboxHandle, source_path: str, target_path: Path) -> None:
        return None

    async def status(self, handle: SandboxHandle) -> object:
        return None

    async def close(self, handle: SandboxHandle) -> None:
        self.closed += 1

    async def aclose(self) -> None:
        self.aclosed += 1


def _runtime(provider: _FakeProvider, **kwargs: object) -> FabricContainerRuntime:
    return FabricContainerRuntime(_CONFIG, provider=provider, **kwargs)  # type: ignore[arg-type]


async def _run(runtime: FabricContainerRuntime, tasks: list[AgentEvalTask], tmp_path: Path) -> Sequence[AgentEvalTrial]:
    return await runtime.run_tasks(tasks, AgentEvalRunConfig(output_dir=tmp_path))


def _task() -> AgentEvalTask:
    return AgentEvalTask(
        id="fix-bug",
        intent="Fix the bug in fib.py",  # eval-side metadata; must NOT reach the agent
        inputs={
            "instruction": "Fix fib.py so fib(n) returns the nth Fibonacci number.",
            "files": {"fib.py": "def fib(n): return n  # buggy"},
        },
    )


async def test_success_maps_evidence_contract(tmp_path: Path) -> None:
    provider = _FakeProvider()
    trials = await _run(_runtime(provider), [_task()], tmp_path)
    (trial,) = trials

    assert trial.status == AgentEvalTrialStatus.COMPLETED
    assert trial.output is not None and trial.output.output_text == "fixed the bug"
    # Same evidence keys/kinds FabricAgentRuntime + Codex produce, so metrics work unchanged.
    ws = trial.evidence.require("workspace")
    assert ws.kind == "filesystem" and Path(ws.ref).is_dir()  # type: ignore[arg-type]
    trace = trial.evidence.require("trace")
    assert trace.kind == "trace" and trace.format == "atif"
    assert trial.evidence.require("result").kind == "json"
    assert provider.closed == 1
    assert provider.aclosed == 1  # the batch disposes the shared provider once, after all tasks


async def test_success_response_is_output_payload_not_full_envelope(tmp_path: Path) -> None:
    # The host FabricAgentRuntime sets AgentOutput.response to RunResult.output; the container path must
    # match so metrics reading `sample.response` see the same shape — the output payload, not the whole
    # normalized RunResult envelope (status/output/error).
    provider = _FakeProvider()
    (trial,) = await _run(_runtime(provider), [_task()], tmp_path)
    assert trial.output is not None
    assert trial.output.response == {"response": "fixed the bug"}  # output payload only, not the envelope


async def test_success_trial_stamps_agent_ok_true(tmp_path: Path) -> None:
    # AgentPhaseSuccessMetric reads metadata["agent_ok"] and treats a missing value as False, so a
    # successful container trial must set agent_ok=True (matching host Fabric + Codex) or every clean
    # container run is scored a failed phase.
    provider = _FakeProvider()
    (trial,) = await _run(_runtime(provider), [_task()], tmp_path)
    assert trial.metadata["agent_ok"] is True


async def test_failed_trial_stamps_agent_ok_false(tmp_path: Path) -> None:
    provider = _FakeProvider(status="failed")
    (trial,) = await _run(_runtime(provider), [_task()], tmp_path)
    assert trial.status == AgentEvalTrialStatus.FAILED
    assert trial.metadata["agent_ok"] is False


async def test_seeds_agent_config_profiles_and_execs_cli(tmp_path: Path) -> None:
    provider = _FakeProvider()
    await _run(_runtime(provider), [_task()], tmp_path)
    assert "/in/agent.yaml" in provider.seeded and "/in/input.txt" in provider.seeded
    # base profiles (none here) + the per-task workspace overlay + the trajectory profile.
    profile_files = sorted(key for key in provider.seeded if key.startswith("/in/profile-"))
    names = {json.loads(provider.seeded[path])["name"] for path in profile_files}
    assert names == {"eval_workspace", "eval_trajectory"}
    # Workspace seed files were staged and uploaded across the boundary.
    assert provider.uploaded_dirs and provider.uploaded_dirs[0][1] == "/out/workspace"
    # Execs Fabric's own CLI (not an in-image Python driver), redirecting the RunResult to /out.
    (cmd,) = provider.execs
    assert "fabric run /in/agent.yaml" in cmd
    assert "--profile /in/profile-0.yaml" in cmd and "--input-file /in/input.txt" in cmd
    assert "> /out/fabric_result.json" in cmd


async def test_agent_input_uses_instruction_not_intent(tmp_path: Path) -> None:
    provider = _FakeProvider()
    await _run(_runtime(provider), [_task()], tmp_path)
    agent_input = provider.seeded["/in/input.txt"]
    assert "Fix fib.py so fib(n) returns the nth Fibonacci number." in agent_input
    assert "Fix the bug in fib.py" not in agent_input  # the intent must not leak to the agent
    assert "fib.py" in agent_input  # seed file listed by name


async def test_secrets_are_resolved_and_injected_as_env(tmp_path: Path) -> None:
    provider = _FakeProvider()
    runtime = _runtime(provider, secrets={"NVIDIA_API_KEY": SecretRef(root="nvidia-build-api-key")})
    # The orchestrator (AgentEvaluator / backend) owns the resolver and resolves before running.
    await runtime.resolve_secrets(_FakeResolver("nvapi-xyz"))
    await _run(runtime, [_task()], tmp_path)
    assert provider.env == {"NVIDIA_API_KEY": "nvapi-xyz"}  # resolved value, keyed by the harness env var


async def test_no_run_result_fails_trial(tmp_path: Path) -> None:
    # The CLI crashed (non-zero exit) and produced no RunResult; the trial must fail (not silently complete).
    provider = _FakeProvider(return_code=1, write_result=False)
    (trial,) = await _run(_runtime(provider), [_task()], tmp_path)
    assert trial.status == AgentEvalTrialStatus.FAILED
    assert trial.evidence.require("error").kind == "error"
    assert "stderr-boom" in str(trial.metadata.get("error"))
    assert provider.closed == 1


async def test_fabric_error_status_fails_trial(tmp_path: Path) -> None:
    provider = _FakeProvider(status="failed")
    (trial,) = await _run(_runtime(provider), [_task()], tmp_path)
    assert trial.status == AgentEvalTrialStatus.FAILED
    assert trial.metadata["error"] == "nope"


async def test_exec_timeout_with_stale_success_file_fails(tmp_path: Path) -> None:
    # Finding #1: a timed-out / SIGKILLed exec that still left a status=succeeded file must NOT be COMPLETED.
    provider = _FakeProvider(error_type="timeout", return_code=125, status="succeeded")
    (trial,) = await _run(_runtime(provider), [_task()], tmp_path)
    assert trial.status == AgentEvalTrialStatus.FAILED
    assert provider.closed == 1


async def test_non_object_result_fails(tmp_path: Path) -> None:
    # Finding #2: fabric_result.json is valid JSON but not an object — must fail, not default to success.
    provider = _FakeProvider(result_bytes=b'"just a diagnostic string"')
    (trial,) = await _run(_runtime(provider), [_task()], tmp_path)
    assert trial.status == AgentEvalTrialStatus.FAILED


async def test_unreadable_result_is_isolated_not_batch_aborting(tmp_path: Path) -> None:
    # Finding #3: a non-UTF-8 / unparseable result must fail per-task, not raise and abort the whole batch.
    provider = _FakeProvider(result_bytes=b"\xff\xfe not utf-8 \x00")
    tasks = [_task(), AgentEvalTask(id="other", intent="x", inputs={"instruction": "do a thing"})]
    trials = await _run(_runtime(provider), tasks, tmp_path)  # must not raise
    assert len(trials) == 2
    assert all(trial.status == AgentEvalTrialStatus.FAILED for trial in trials)
    assert provider.closed == 2


def test_empty_instruction_is_rejected() -> None:
    # The container prompt is task.agent_prompt(): an empty/absent instruction cannot be evaluated, so
    # it raises here and the runtime turns that into a failed trial for just that task (see _run_task).
    with pytest.raises(ValueError, match="no instruction"):
        AgentEvalTask(id="x", intent="ignored", inputs={"instruction": ""}).agent_prompt()


def test_trajectory_profile_built_from_relay_types() -> None:
    # The trajectory telemetry is built from nemo_relay's own typed config (a hard dependency), so drift
    # in relay's schema fails construction here rather than silently emitting a malformed profile. Runs
    # in CI now that nemo-relay is declared — no importorskip. Asserts the shape metrics rely on.
    component = FabricContainerRuntime._trajectory_profile()["telemetry"]["config"]["components"][0]
    assert component["kind"] == "observability" and component["enabled"] is True
    cfg = component["config"]
    # The ATIF/ATOF file exporter is configured with the names both runtimes agree on.
    assert cfg["atif"]["enabled"] is True
    assert cfg["atif"]["filename_template"] == crt._common.ATIF_FILENAME_TEMPLATE
    assert cfg["atof"]["filename"] == crt._common.ATOF_FILENAME


async def test_sandbox_exception_is_isolated_per_task(tmp_path: Path) -> None:
    # A sandbox that blows up mid-run must yield a FAILED trial per task, not abort the gather.
    class _BrokenProvider(_FakeProvider):
        async def download_dir(self, handle: SandboxHandle, source_dir: str, target_dir: Path) -> None:
            raise RuntimeError("sandbox died")

    provider = _BrokenProvider()
    other = AgentEvalTask(id="other", intent="x", inputs={"instruction": "do a thing"})
    trials = await _run(_runtime(provider), [_task(), other], tmp_path)
    assert len(trials) == 2
    assert all(trial.status == AgentEvalTrialStatus.FAILED for trial in trials)
    assert {trial.task_id for trial in trials} == {"fix-bug", "other"}
    assert provider.closed == 2  # both sandboxes were torn down despite the mid-run failures
