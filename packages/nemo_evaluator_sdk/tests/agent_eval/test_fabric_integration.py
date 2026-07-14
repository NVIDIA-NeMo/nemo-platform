# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests: a Fabric-driven agent eval end-to-end, scored by a metric that consumes the
captured trajectory evidence.

- ``test_fabric_runner_eval_exposes_trajectory_to_metric`` is hermetic (fake ``nemo_fabric``) and runs
  in CI: it proves the runner -> evaluator -> metric -> evidence chain, i.e. the metric receives and
  reads the trajectory (ATIF) evidence for the task.
- ``test_fabric_codex_live_eval_captures_atif_trajectory`` is the real fabric->codex->Relay run, gated
  behind the required binaries/checkout so CI skips it; run it locally after
  ``script/dev-install-fabric.sh``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.fabric import runtime as fabric_runtime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values.evidence import EVIDENCE_FORMAT_ATIF, EVIDENCE_TRACE


class _TrajectoryEvidenceMetric:
    """Scores 1.0 iff the trial exposes a readable ATIF trajectory with at least one step.

    Exercises exactly the concern under test: a grader receives the candidate evidence and can locate
    + read the captured trajectory (the ``trace`` descriptor) for the task.
    """

    @property
    def type(self) -> str:
        return "has-trajectory"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.boolean("has_trajectory")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:  # noqa: A002 - matches protocol
        steps = 0
        evidence = input.candidate.evidence
        if evidence is not None:
            descriptor = evidence.get(EVIDENCE_TRACE)
            if descriptor is not None and descriptor.ref:
                payload = json.loads(Path(descriptor.ref).read_text(encoding="utf-8"))
                steps = len(payload.get("steps") or [])
        return MetricResult(outputs=[MetricOutput(name="has_trajectory", value=steps > 0)])


def _task() -> AgentEvalTask:
    return AgentEvalTask(
        id="say-done",
        intent="Agent follows a trivial instruction and exits cleanly.",
        inputs={"instruction": "Reply with the single word DONE and nothing else."},
        metrics=[_TrajectoryEvidenceMetric()],
    )


# --- hermetic: fake nemo_fabric so CI exercises the runner+evaluator+metric+evidence chain ----------


class _FakeEnvironment:
    def __init__(self, *, provider: str = "local", workspace: str | None = None, artifacts: str | None = None) -> None:
        self.provider = provider
        self.workspace = workspace
        self.artifacts = artifacts


class _FakeRuntimeCfg:
    def __init__(self, artifacts: str | None = None) -> None:
        self.artifacts = artifacts


class _FakeConfig:
    """Stand-in for nemo_fabric.FabricConfig supporting the config-first helpers the runtime uses."""

    def __init__(self) -> None:
        self.environment: _FakeEnvironment | None = None
        self.runtime = _FakeRuntimeCfg()
        self.models: dict[str, Any] = {}
        self.relay: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> _FakeConfig:
        return cls()

    def model_copy(self, *, deep: bool = False) -> _FakeConfig:
        clone = _FakeConfig()
        clone.environment = copy.deepcopy(self.environment)
        clone.runtime = _FakeRuntimeCfg(self.runtime.artifacts)
        clone.models = copy.deepcopy(self.models)
        clone.relay = copy.deepcopy(self.relay)
        return clone

    def enable_relay(
        self, *, project: str | None = None, output_dir: str | None = None, config: Any = None
    ) -> _FakeConfig:
        self.relay = {"project": project, "output_dir": output_dir, "config": config}
        return self


class _FakeProfile:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> _FakeProfile:
        return cls(**mapping)


class _FakeArtifact:
    def __init__(self, name: str, kind: str, path: Path) -> None:
        self.name = name
        self.kind = kind
        self.path = path
        self.media_type = "application/json" if kind == "atif" else "text/plain"
        self.metadata: dict[str, Any] = {}


class _FakeManifest:
    def __init__(self, artifacts: list[_FakeArtifact]) -> None:
        self.root: Path | None = None
        self.artifacts = artifacts


class _FakeResult:
    def __init__(self, artifacts: list[_FakeArtifact]) -> None:
        self.status = "succeeded"
        self.output = {"adapter": "cli", "response": "DONE"}
        self.error = None
        self.harness = "codex"
        self.adapter_id = "nvidia.fabric.codex.cli"
        self.adapter_kind = "process"
        self.invocation_id = "inv-1"
        self.artifacts = _FakeManifest(artifacts)
        self.telemetry: list[Any] = []
        self.events: list[Any] = []

    def to_mapping(self) -> dict[str, Any]:
        return {"status": self.status, "output": self.output}


@pytest.mark.asyncio
async def test_fabric_runner_eval_exposes_trajectory_to_metric(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A real (fake-backed) ATIF file the promoted artifact points at.
    atif_path = tmp_path / "trajectory.atif.json"
    atif_path.write_text(json.dumps({"schema_version": "atif/v1", "steps": [{"kind": "message"}]}), encoding="utf-8")
    artifacts = [_FakeArtifact("relay_atif", "atif", atif_path), _FakeArtifact("stdout", "log", tmp_path / "out.txt")]
    (tmp_path / "out.txt").write_text("DONE\n", encoding="utf-8")

    class _FakeClient:
        # Fabric is a plain reusable facade (not an async context manager).
        async def run(self, agent: Any, **kwargs: Any) -> _FakeResult:
            return _FakeResult(artifacts)

    class _FakeRunRequest:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    module = types.ModuleType("nemo_fabric")
    module.Fabric = _FakeClient  # type: ignore[attr-defined]
    module.FabricConfig = _FakeConfig  # type: ignore[attr-defined]
    module.FabricProfileConfig = _FakeProfile  # type: ignore[attr-defined]
    module.EnvironmentConfig = _FakeEnvironment  # type: ignore[attr-defined]
    module.RunRequest = _FakeRunRequest  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nemo_fabric", module)
    # nemo_relay is a hard dependency (the trajectory profile is built from its real typed config), so
    # it is not stubbed — only the optional native nemo_fabric SDK is faked.

    runtime = fabric_runtime.FabricAgentRuntime(
        config={"metadata": {"name": "a"}, "harness": {"adapter_id": "nvidia.fabric.codex.cli"}},
        work_root=tmp_path / "fabric",
    )
    result = AgentEvaluator().run_sync(
        tasks=[_task()],
        target=runtime,
        config=AgentEvalRunConfig(output_dir=tmp_path / "out", parallelism=1, write_dashboard=False),
    )

    trial = result.trials[0]
    assert trial.status == "completed"
    # The trajectory is exposed under the standard trace key, as an existing ATIF file.
    trace = trial.evidence.descriptors[EVIDENCE_TRACE]
    assert trace.format == EVIDENCE_FORMAT_ATIF
    assert Path(trace.ref).exists()
    # The metric received the evidence and scored from the trajectory content.
    scores = [s for s in result.scores if s.metric_type == "has-trajectory"]
    assert scores and scores[0].trial_id == trial.id
    assert scores[0].outputs[0].name == "has_trajectory"
    assert scores[0].outputs[0].value in (True, 1.0)


# --- gated live: real fabric -> codex -> Relay ATIF ------------------------------------------------

_FABRIC_REPO = os.environ.get("NEMO_FABRIC_REPO", "")
_LIVE_READY = bool(
    _FABRIC_REPO
    and shutil.which("codex")
    and shutil.which("nemo-relay")
    and importlib.util.find_spec("nemo_fabric") is not None
)
requires_live_fabric = pytest.mark.skipif(
    not _LIVE_READY,
    reason="needs NEMO_FABRIC_REPO + codex + nemo-relay gateway + nemo_fabric (run script/dev-install-fabric.sh)",
)


@requires_live_fabric
@pytest.mark.timeout(300)
def test_fabric_codex_live_eval_captures_atif_trajectory(tmp_path: Path) -> None:
    codex_config = {
        "schema_version": "fabric.agent/v1alpha1",
        "metadata": {"name": "eval-fabric-live"},
        "harness": {
            "adapter_id": "nvidia.fabric.codex.cli",
            "resolution": "preinstalled",
            "settings": {"sandbox": "workspace-write", "skip_git_repo_check": True, "timeout_seconds": 180},
        },
        "runtime": {"mode": "oneshot", "transport": "cli", "input_schema": "text", "output_schema": "message"},
        "environment": {"provider": "local", "workspace": str(tmp_path / "ws")},
        "telemetry": {"enabled": False},
    }
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    runtime = fabric_runtime.FabricAgentRuntime(
        config=codex_config,
        base_dir=Path(_FABRIC_REPO),  # so the adapter registry resolves adapters/codex-cli
        work_root=tmp_path / "fabric",
        capture_trajectory=True,
    )

    result = AgentEvaluator().run_sync(
        tasks=[_task()],
        target=runtime,
        config=AgentEvalRunConfig(output_dir=tmp_path / "out", parallelism=1, write_dashboard=False),
    )

    trial = result.trials[0]
    assert trial.status == "completed", trial.metadata
    trace = trial.evidence.descriptors[EVIDENCE_TRACE]
    assert trace.format == EVIDENCE_FORMAT_ATIF
    atif = Path(trace.ref)
    assert atif.exists() and atif.stat().st_size > 0
    assert "steps" in json.loads(atif.read_text(encoding="utf-8"))
    # The metric read the real trajectory and scored on it.
    scores = [s for s in result.scores if s.metric_type == "has-trajectory"]
    assert scores and scores[0].outputs[0].value in (True, 1.0)
