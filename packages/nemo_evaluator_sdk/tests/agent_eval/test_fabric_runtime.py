# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for FabricAgentRuntime using a fake nemo_fabric SDK (the native package is optional)."""

from __future__ import annotations

import copy
import json
import sys
import types
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.fabric import runtime as fabric_runtime
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.values.evidence import EVIDENCE_FORMAT_ATIF, EVIDENCE_TRACE


class _FakeEnvironment:
    """Stand-in for nemo_fabric.EnvironmentConfig (the runtime sets workspace/provider/artifacts)."""

    def __init__(self, *, provider: str = "local", workspace: str | None = None, artifacts: str | None = None) -> None:
        self.provider = provider
        self.workspace = workspace
        self.artifacts = artifacts


class _FakeRuntimeCfg:
    def __init__(self, artifacts: str | None = None) -> None:
        self.artifacts = artifacts


class _FakeConfig:
    """Stand-in for nemo_fabric.FabricConfig with the config-first helpers the runtime composes onto."""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self.mapping = mapping
        self.environment: _FakeEnvironment | None = None
        self.runtime = _FakeRuntimeCfg()
        self.models: dict[str, Any] = dict(mapping.get("models", {}))
        self.relay: dict[str, Any] | None = None  # records enable_relay(...)

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> _FakeConfig:
        return cls(mapping)

    def model_copy(self, *, deep: bool = False) -> _FakeConfig:
        clone = _FakeConfig(self.mapping)
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
    def __init__(self, *, name: str | None = None, models: Any = None, mapping: Any = None) -> None:
        self.name = name
        self.models = models
        self.mapping = mapping

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> _FakeProfile:
        return cls(name=mapping.get("name"), mapping=mapping)


class _FakeRunRequest:
    """Stand-in for nemo_fabric.RunRequest (Fabric.run folds input + request id into it)."""

    def __init__(self, *, input: Any = None, request_id: str | None = None) -> None:
        self.input = input
        self.request_id = request_id


class _FakeRelayConfig:
    """Stand-in for nemo_relay.observability's typed config objects (AtifConfig/AtofConfig/...)."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def to_dict(self) -> dict[str, Any]:
        return {key: (value.to_dict() if hasattr(value, "to_dict") else value) for key, value in self.kwargs.items()}


class _FakeComponentSpec:
    def __init__(self, *, config: Any, enabled: bool = True) -> None:
        self.config = config
        self.enabled = enabled

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "observability", "enabled": self.enabled, "config": self.config.to_dict()}


class _FakeArtifact:
    def __init__(self, name: str, kind: str, path: Path, media_type: str | None = None) -> None:
        self.name = name
        self.kind = kind
        self.path = path
        self.media_type = media_type


class _FakeManifest:
    def __init__(self, artifacts: list[_FakeArtifact]) -> None:
        self.root: Path | None = None
        self.artifacts = artifacts


class _FakeError:
    def __init__(self, stage: str, code: str, message: str) -> None:
        self.stage = stage
        self.code = code
        self.message = message


class _FakeTelemetry:
    def __init__(self, *, provider: str, kind: str, uri: str | None, trace_id: str | None) -> None:
        self.provider = provider
        self.kind = kind
        self.uri = uri
        self.trace_id = trace_id


class _FakeEvent:
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        self.message = message


class _FakeResult:
    def __init__(
        self,
        *,
        status: str,
        output: Any = None,
        error: _FakeError | None = None,
        artifacts: list[_FakeArtifact] | None = None,
    ) -> None:
        self.status = status
        self.output = output
        self.error = error
        self.harness = "codex"
        self.adapter_id = "nvidia.fabric.codex.cli"
        self.adapter_kind = "process"
        self.invocation_id = "inv-1"
        self.artifacts = _FakeManifest(artifacts or [])
        self.telemetry = [_FakeTelemetry(provider="relay", kind="trace", uri="file:///relay", trace_id="tid-1")]
        self.events = [_FakeEvent("runtime_start", "started")]

    def to_mapping(self) -> dict[str, Any]:
        return {"status": self.status, "output": self.output, "harness": self.harness}


def _install_fake_fabric(monkeypatch: pytest.MonkeyPatch, handler: Any) -> type:
    """Inject a fake ``nemo_fabric`` module (the runtime imports it lazily); return the client class."""

    class _FakeClient:
        # Fabric is a plain reusable facade (not an async context manager).
        recorded: list[dict[str, Any]] = []

        async def run(self, agent: Any, **kwargs: Any) -> Any:
            _FakeClient.recorded.append({"agent": agent, **kwargs})
            return handler(agent, kwargs)

    _FakeClient.recorded = []
    module = types.ModuleType("nemo_fabric")
    module.Fabric = _FakeClient  # type: ignore[attr-defined]
    module.FabricConfig = _FakeConfig  # type: ignore[attr-defined]
    module.FabricProfileConfig = _FakeProfile  # type: ignore[attr-defined]
    module.EnvironmentConfig = _FakeEnvironment  # type: ignore[attr-defined]
    module.RunRequest = _FakeRunRequest  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nemo_fabric", module)

    # The runtime builds the trajectory profile from nemo_relay's typed config objects (lazy import);
    # stub the optional package so trajectory-capture paths resolve without the native dependency.
    relay_mod = types.ModuleType("nemo_relay")
    observability_mod = types.ModuleType("nemo_relay.observability")
    observability_mod.AtifConfig = _FakeRelayConfig  # type: ignore[attr-defined]
    observability_mod.AtofConfig = _FakeRelayConfig  # type: ignore[attr-defined]
    observability_mod.ObservabilityConfig = _FakeRelayConfig  # type: ignore[attr-defined]
    observability_mod.ComponentSpec = _FakeComponentSpec  # type: ignore[attr-defined]
    relay_mod.observability = observability_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nemo_relay", relay_mod)
    monkeypatch.setitem(sys.modules, "nemo_relay.observability", observability_mod)
    return _FakeClient


_TASK = AgentEvalTask(id="task/1", intent="Answer.", inputs={"prompt": "Ping?"})
_CONFIG = {"metadata": {"name": "a"}, "harness": {"adapter_id": "nvidia.fabric.codex.cli"}}


@pytest.mark.asyncio
async def test_fabric_runtime_maps_succeeded_result_to_completed_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _FakeArtifact("stdout", "log", tmp_path / "stdout.txt")

    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(
            status="succeeded",
            output={"adapter": "cli", "response": "PONG", "returncode": 0},
            artifacts=[artifact],
        )

    client_cls = _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, model="openai/gpt-5.4", work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([_TASK])

    trial = trials[0]
    assert trial.status == "completed"
    assert trial.output is not None
    assert trial.output.output_text == "PONG"  # extracted from the adapter envelope's `response`
    assert trial.output.response == {"adapter": "cli", "response": "PONG", "returncode": 0}
    assert trial.metadata["harness"] == "codex"
    assert trial.metadata["adapter_id"] == "nvidia.fabric.codex.cli"
    assert trial.metadata["generated"] is True
    # agent_ok mirrors the Codex runtime so AgentPhaseSuccessMetric scores the phase as clean.
    assert trial.metadata["agent_ok"] is True
    # Evidence: the persisted result envelope + each Fabric artifact by name.
    assert trial.evidence is not None
    assert trial.evidence.descriptors["result"].ref.endswith("fabric_result.json")
    assert trial.evidence.descriptors["stdout"].ref == str(tmp_path / "stdout.txt")
    result_file = tmp_path / "fabric" / "000000-task-1" / "fabric_result.json"
    assert json.loads(result_file.read_text(encoding="utf-8"))["status"] == "succeeded"
    # Config-first: the model is set on the config's default model and relay (ATIF trajectory) is
    # enabled on the config, rather than layered as profile overlays.
    composed = client_cls.recorded[0]["agent"]
    assert composed.models["default"] == {"provider": "openai", "model": "openai/gpt-5.4"}
    assert composed.relay is not None  # capture_trajectory defaults on -> enable_relay(...) called
    assert client_cls.recorded[0]["request"].request_id == "task/1"
    # Telemetry reference is preserved end-to-end (uri + trace_id), not just provider/kind.
    assert trial.evidence.metadata["telemetry"][0]["uri"] == "file:///relay"
    assert trial.evidence.metadata["telemetry"][0]["trace_id"] == "tid-1"


@pytest.mark.asyncio
async def test_fabric_runtime_maps_atif_artifact_to_trace_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    atif = _FakeArtifact("relay_atif", "atif", tmp_path / "trajectory.atif.json", "application/json")

    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output={"response": "ok"}, artifacts=[atif])

    _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([_TASK])

    evidence = trials[0].evidence
    assert evidence is not None
    # The ATIF artifact is exposed both under its own name and the standard trace key.
    assert evidence.descriptors["relay_atif"].ref == str(tmp_path / "trajectory.atif.json")
    trace = evidence.descriptors[EVIDENCE_TRACE]
    assert trace.format == EVIDENCE_FORMAT_ATIF
    assert trace.ref == str(tmp_path / "trajectory.atif.json")


def _workspace_from_config(config: Any) -> Path:
    """Pull the staged workspace path out of the composed per-task config."""
    return Path(config.environment.workspace)


def _resolve_like_fabric(config: Any, profiles: list[Any], section: str, key: str) -> Any:
    """Mirror Fabric's resolver: start from the config, then apply each profile as a winning overlay in
    order (last wins). Used to assert what value actually reaches the harness for a config/profile key.
    """
    if section == "environment":
        value = getattr(config.environment, key, None) if config.environment is not None else None
    elif section == "models":
        value = config.models.get(key)
    else:  # pragma: no cover - only the two sections above are exercised
        raise ValueError(section)
    for profile in profiles:
        overlay = getattr(profile, "mapping", None)
        if isinstance(overlay, Mapping) and isinstance(overlay.get(section), Mapping):
            if overlay[section].get(key) is not None:
                value = overlay[section][key]
    return value


@pytest.mark.asyncio
async def test_caller_profiles_cannot_override_evaluator_owned_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fabric applies caller-supplied profiles over the config (last-wins), so the evaluator's per-task
    # workspace (isolation + `workspace` evidence integrity) and model-under-eval must remain the final,
    # authoritative layer. A caller profile that sets these must NOT win.
    caller_profile = {
        "name": "caller",
        "environment": {"workspace": "/caller/hijacked-workspace"},
        "models": {"default": {"provider": "openai", "model": "caller/rogue-model"}},
    }

    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output="ok")

    client_cls = _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(
        config=_CONFIG, model="openai/gpt-5.4", work_root=tmp_path / "fabric", profiles=[caller_profile]
    )

    await runtime.run_tasks([_TASK])

    config = client_cls.recorded[0]["agent"]
    profiles = client_cls.recorded[0]["profiles"]
    eval_workspace = config.environment.workspace  # the per-task dir the evaluator composed
    eval_model = config.models["default"]

    # After Fabric applies the caller profile, the evaluator's workspace + model must still win.
    assert _resolve_like_fabric(config, profiles, "environment", "workspace") == eval_workspace
    assert _resolve_like_fabric(config, profiles, "models", "default") == eval_model


@pytest.mark.asyncio
async def test_fabric_runtime_seeds_workspace_and_exposes_workspace_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = AgentEvalTask(
        id="fix/bug",
        intent="Fix the bug.",
        inputs={"instruction": "make the tests pass", "files": {"calc.py": "value = 1\n"}},
    )

    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        # The harness runs in the staged workspace; simulate an edit it leaves behind.
        workspace = _workspace_from_config(agent)
        (workspace / "result.txt").write_text("done", encoding="utf-8")
        return _FakeResult(status="succeeded", output={"response": "ok"})

    client_cls = _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([task])

    trial = trials[0]
    assert trial.status == "completed"
    # The composed config carries environment.workspace (the harness's cwd) with provider=local.
    composed = client_cls.recorded[0]["agent"]
    assert composed.environment.provider == "local"
    workspace = _workspace_from_config(composed)
    # The seed file is staged and the agent's edit is present in the same dir.
    assert (workspace / "calc.py").read_text(encoding="utf-8") == "value = 1\n"
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "done"
    # The final workspace is exposed as filesystem evidence (same key/kind as the Codex runtime).
    assert trial.evidence is not None
    workspace_evidence = trial.evidence.descriptors["workspace"]
    assert workspace_evidence.kind == "filesystem"
    assert workspace_evidence.ref == str(workspace)
    # Seed-file contents are listed by name in the input, not dumped inline (they are already on disk).
    harness_input = client_cls.recorded[0]["request"].input
    assert "calc.py" in harness_input
    assert "value = 1" not in harness_input


@pytest.mark.asyncio
async def test_fabric_runtime_stages_workspace_even_without_seed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every task gets a workspace, even with no inputs['files'] — the harness may still create files,
    # and the per-task dir is exposed as evidence uniformly (a from-scratch coding task, say).
    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output="ok")

    client_cls = _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([_TASK])  # _TASK has no 'files' input

    workspace = _workspace_from_config(client_cls.recorded[0]["agent"])
    assert workspace.is_dir()
    assert trials[0].evidence is not None
    assert trials[0].evidence.descriptors["workspace"].ref == str(workspace)


@pytest.mark.asyncio
async def test_fabric_runtime_bad_seed_fails_only_that_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A seed path escaping the workspace must fail just this task (as a failed trial), not abort the run.
    bad_task = AgentEvalTask(
        id="bad/seed",
        intent="unused",
        inputs={"files": {"../escape.py": "nope"}},
    )

    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output="unreached")

    _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([bad_task])

    assert trials[0].status == "failed"
    assert trials[0].metadata["error_type"] == "WorkspaceSeedError"


@pytest.mark.asyncio
async def test_fabric_runtime_capture_trajectory_false_skips_relay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output="ok")

    client_cls = _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric", capture_trajectory=False)

    await runtime.run_tasks([_TASK])

    assert client_cls.recorded[0]["agent"].relay is None


@pytest.mark.asyncio
async def test_fabric_runtime_maps_failed_result_to_failed_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(
            status="failed",
            error=_FakeError(stage="invoke", code="process_exit_nonzero", message="boom"),
        )

    _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([_TASK])

    trial = trials[0]
    assert trial.status == "failed"
    assert trial.output is None
    assert trial.metadata["error_type"] == "process_exit_nonzero"
    assert trial.metadata["error"] == "boom"
    assert trial.metadata["agent_ok"] is False
    assert trial.evidence is not None
    assert "error" in trial.evidence.descriptors


@pytest.mark.asyncio
async def test_fabric_runtime_maps_timeout_to_failed_trial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output="never")

    _install_fake_fabric(monkeypatch, handler)

    async def fake_wait_for(awaitable: Any, timeout: float) -> Any:
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(fabric_runtime.asyncio, "wait_for", fake_wait_for)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([_TASK])

    assert trials[0].status == "failed"
    assert trials[0].metadata["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_fabric_runtime_captures_run_exception_as_failed_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        raise RuntimeError("client blew up")

    _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trials = await runtime.run_tasks([_TASK])

    assert trials[0].status == "failed"
    assert trials[0].metadata["error_type"] == "RuntimeError"
    assert trials[0].metadata["error"] == "client blew up"


@pytest.mark.asyncio
async def test_fabric_runtime_raises_without_nemo_fabric(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # run_tasks surfaces a clear error when the optional native package can't be imported.
    monkeypatch.setitem(sys.modules, "nemo_fabric", None)  # forces ImportError on `import nemo_fabric`
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")
    with pytest.raises(RuntimeError, match="requires the `nemo-fabric` package"):
        await runtime.run_tasks([_TASK])


@pytest.mark.asyncio
async def test_fabric_runtime_trajectory_capture_requires_nemo_relay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Trajectory capture builds the profile from nemo_relay; surface a clear error when it is absent.
    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output="ok")

    _install_fake_fabric(monkeypatch, handler)  # installs fabric + relay stubs...
    monkeypatch.setitem(sys.modules, "nemo_relay.observability", None)  # ...then force ImportError on relay
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")
    with pytest.raises(RuntimeError, match="nemo-relay"):
        await runtime.run_tasks([_TASK])


@pytest.mark.asyncio
async def test_fabric_success_trial_scores_agent_phase_success_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression guard: AgentPhaseSuccessMetric reads candidate.metadata["agent_ok"]; a successful Fabric
    # trial must set it (via the same _trial_sample path the evaluator uses) so the metric scores True.
    from nemo_evaluator_sdk.agent_eval.evaluator import _metric_row, _trial_sample
    from nemo_evaluator_sdk.agent_eval.metrics import AgentPhaseSuccessMetric
    from nemo_evaluator_sdk.execution.samples import build_metric_input

    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output={"response": "ok"})

    _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trial = (await runtime.run_tasks([_TASK]))[0]
    metric_input = build_metric_input(_metric_row(_TASK, trial), _trial_sample(trial), 0)
    result = await AgentPhaseSuccessMetric().compute_scores(metric_input)

    assert result.outputs[0].name == "agent_phase_success"
    assert result.outputs[0].value is True


@pytest.mark.asyncio
async def test_fabric_runtime_normalizes_runoutput_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Newer Fabric wraps RunResult.output in a RunOutput Mapping (not a plain JSON value); the runtime
    # must copy it into a plain dict so it round-trips through the trial's JsonValue response field.
    class _FakeRunOutput(Mapping):
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = dict(data)

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

        def __iter__(self) -> Iterator[str]:
            return iter(self._data)

        def __len__(self) -> int:
            return len(self._data)

    def handler(agent: Any, kwargs: dict[str, Any]) -> _FakeResult:
        return _FakeResult(status="succeeded", output=_FakeRunOutput({"response": "PONG", "returncode": 0}))

    _install_fake_fabric(monkeypatch, handler)
    runtime = fabric_runtime.FabricAgentRuntime(config=_CONFIG, work_root=tmp_path / "fabric")

    trial = (await runtime.run_tasks([_TASK]))[0]

    assert trial.status == "completed"
    assert trial.output is not None
    assert trial.output.output_text == "PONG"  # extracted from the normalized mapping
    assert trial.output.response == {"response": "PONG", "returncode": 0}  # plain dict, not RunOutput
