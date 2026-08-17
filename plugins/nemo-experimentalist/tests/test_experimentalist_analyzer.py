# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for AgentAnalyzer client/workspace plumbing and retry budget.

The Experimentalist round-N analysis path used to silently skip every
``intake://`` trial trace because ``AgentAnalyzer`` never received (and never
forwarded) a platform ``client`` or the Intake ``workspace`` name. These tests
pin the plumbing: ``AgentAnalyzer.run`` must accept ``client`` / ``nmp_workspace``
and thread them into ``TraceAnalyzer.run``.

``AgentAnalyzer`` is built via ``object.__new__`` to skip its LLM-heavy
``__init__``, and the LLM-driven strategy methods (``select_trials``,
``classify_failures``, ``compare_with_peers``) are replaced by callable
*objects* — the agent framework's method guard rejects attaching plain
functions/methods to public attributes, but allows non-function callables.
The retry-budget test is the exception: it drives the real CodeAct harness with
a scripted model, because the budget it pins is the framework's.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from nemo_experimentalist_plugin.entities import EvaluationResult, MetricResult, TrialResult
from nemo_experimentalist_plugin.experimentalist.components import analyzer as analyzer_module
from nemo_experimentalist_plugin.experimentalist.components import cache
from nemo_experimentalist_plugin.experimentalist.components.analyzer import (
    AgentAnalyzer,
    AnalyzerConfig,
    FailureClassification,
    PeerComparison,
    TrialSelection,
)
from nemo_experimentalist_plugin.experimentalist.components.rationalizer import Rationale
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import Diagnostic
from nemo_platform_plugin.nooa_model_client import ConfiguredModelClients, activate_model_clients
from nooa.unifiedllm import FakeLLMClient, LLMResponse, ToolCall


@dataclass
class _FakeMetric:
    value: float


@dataclass
class _FakeTrial:
    id: str
    task_id: str
    trace: object
    metrics: dict[str, _FakeMetric]


@dataclass
class _FakeTask:
    id: str


@dataclass
class _FakeDataset:
    tasks: list[_FakeTask]

    def list_tasks(self) -> list[_FakeTask]:
        return self.tasks


@dataclass
class _FakeEvaluation:
    id: str = "eval-1"
    aggregate_metrics: dict[str, float] = field(default_factory=lambda: {"reward": 1.0})
    trials: list[_FakeTrial] = field(default_factory=list)


class _RecordingTraceAnalyzer:
    """Stand-in for TraceAnalyzer that records the run() call context.

    ``calls`` is a class attribute so subclasses can point it at a per-test list.
    """

    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, *, experiment_dir: Path, config: Any, framework_skills_dirs: list[Path] | None = None) -> None:
        self.experiment_dir = experiment_dir
        self.config = config
        self.framework_skills_dirs = framework_skills_dirs or []

    async def run(
        self,
        *,
        trial: Any,
        task: Any,
        agent_path: Any,
        rationale: Any = None,
        insight: Any = None,
        selection_reason: str = "",
        objective_metrics: list[dict[str, Any]] | None = None,
        regression_metrics: list[dict[str, Any]] | None = None,
        client: Any = None,
        workspace: Any = None,
    ) -> Diagnostic:
        type(self).calls.append(
            {
                "client": client,
                "workspace": workspace,
                "selection_reason": selection_reason,
                "objective_metrics": objective_metrics,
                "regression_metrics": regression_metrics,
            }
        )
        return Diagnostic(outcome="SUCCESS", summary="stub", failure_point=None, root_cause="stub")


class _FakeRationalizer:
    def __init__(self, *, workspace: Path, config: Any, framework_skills_dirs: list[Path] | None = None) -> None:
        self.workspace = workspace
        self.config = config
        self.framework_skills_dirs = framework_skills_dirs or []

    async def run(self, task: Any, agent_spec: Any = None) -> Rationale:
        return Rationale(task_name=task.id, steps=[])


# Callable *objects* (not functions) so the framework method guard permits
# assigning them to the analyzer's public strategy attributes.
class _SelectTrials:
    def __init__(self, trials: list[Any]) -> None:
        self._trials = trials

    async def __call__(
        self,
        agent_id: str,
        dataset: Any,
        evaluation: Any,
        objective_metrics: list[dict[str, Any]],
        regression_metrics: list[dict[str, Any]],
    ) -> list[TrialSelection]:
        return [
            TrialSelection(trial_id=trial.id, reason=f"Analyze {trial.id} for this test.") for trial in self._trials
        ]


class _ClassifyFailures:
    async def __call__(
        self,
        agent_id: str,
        diagnoses: Any,
        trials: Any,
        objective_metrics: list[dict[str, Any]],
        regression_metrics: list[dict[str, Any]],
    ) -> FailureClassification:
        return FailureClassification(systematic=[], mechanical=[])


class _CompareWithPeers:
    async def __call__(
        self,
        agent_id: str,
        evaluation: Any,
        diagnoses: Any,
        peer_evaluations: Any = None,
        objective_metrics: list[dict[str, Any]] | None = None,
        regression_metrics: list[dict[str, Any]] | None = None,
    ) -> PeerComparison:
        return PeerComparison(divergent_trials=[], complementary_patterns=[])


def _make_analyzer(tmp_path: Path, trials: list[Any]) -> AgentAnalyzer:
    """Build an AgentAnalyzer without the LLM-heavy __init__ and stub its strategies."""
    analyzer = object.__new__(AgentAnalyzer)
    analyzer._workspace_path = tmp_path
    analyzer._config = AnalyzerConfig()
    analyzer._framework_skills_dirs = []
    analyzer.select_trials = _SelectTrials(trials)  # type: ignore[method-assign,assignment]
    analyzer.classify_failures = _ClassifyFailures()  # type: ignore[method-assign,assignment]
    analyzer.compare_with_peers = _CompareWithPeers()  # type: ignore[method-assign,assignment]
    return analyzer


def _install_fakes(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    class _TA(_RecordingTraceAnalyzer):
        pass

    _TA.calls = calls
    monkeypatch.setattr(analyzer_module, "TraceAnalyzer", _TA)
    monkeypatch.setattr(analyzer_module, "Rationalizer", _FakeRationalizer)


def _fixtures() -> tuple[_FakeTrial, _FakeDataset, _FakeEvaluation]:
    trial = _FakeTrial(id="trial-1", task_id="task-1", trace=object(), metrics={"reward": _FakeMetric(0.0)})
    dataset = _FakeDataset(tasks=[_FakeTask(id="task-1")])
    return trial, dataset, _FakeEvaluation(trials=[trial])


def test_trace_cache_key_uses_trace_uri_namespace() -> None:
    """Trace-analysis cache files must not be named as agent-analysis cache files."""
    assert cache.trace_uri_hash("intake://trace-1:objective-metrics:[]").startswith("trace-uri-")


def test_peer_comparison_respects_minimize_metric_directions(tmp_path: Path) -> None:
    analyzer = _make_analyzer(tmp_path, [])
    focal = _FakeEvaluation(
        trials=[_FakeTrial("focal", "task-1", None, {"quality": _FakeMetric(0.8), "tokens": _FakeMetric(10.0)})]
    )
    peer = _FakeEvaluation(
        trials=[_FakeTrial("peer", "task-1", None, {"quality": _FakeMetric(0.7), "tokens": _FakeMetric(5.0)})]
    )
    directions = analyzer._metric_directions(
        [{"name": "quality", "direction": "maximize"}, {"name": "tokens", "direction": "minimize"}], []
    )

    pairs = analyzer._select_divergent_pairs("focal", cast(Any, focal), cast(Any, {"peer": peer}), directions)
    complementary = analyzer._find_complementary_failures(
        "focal", cast(Any, focal), cast(Any, {"peer": peer}), directions
    )

    assert pairs[0]["winner"] == "peer"
    assert complementary["task-1"]["quality"]["leaders"] == ["focal"]
    assert complementary["task-1"]["tokens"]["leaders"] == ["peer"]


@pytest.mark.asyncio
async def test_run_threads_client_and_workspace_into_trace_analyzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AgentAnalyzer.run forwards client and nmp_workspace to TraceAnalyzer.run."""
    calls: list[dict[str, Any]] = []
    _install_fakes(monkeypatch, calls)
    trial, dataset, evaluation = _fixtures()
    analyzer = _make_analyzer(tmp_path, [trial])

    sentinel_client = object()
    result = await analyzer.run(
        agent="agent-a",
        dataset=cast(Any, dataset),
        evaluation=cast(Any, evaluation),
        round=0,
        client=cast(Any, sentinel_client),
        nmp_workspace="tau2-airline-ws",
    )

    assert result.agent_id == "agent-a"
    assert len(calls) == 1
    assert calls[0]["client"] is sentinel_client
    assert calls[0]["workspace"] == "tau2-airline-ws"
    assert calls[0]["selection_reason"] == "Analyze trial-1 for this test."
    assert calls[0]["objective_metrics"] == []
    assert calls[0]["regression_metrics"] == []


@pytest.mark.asyncio
async def test_run_defaults_client_and_workspace_to_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting client/nmp_workspace still runs and forwards None (backward compat)."""
    calls: list[dict[str, Any]] = []
    _install_fakes(monkeypatch, calls)
    trial, dataset, evaluation = _fixtures()
    analyzer = _make_analyzer(tmp_path, [trial])

    await analyzer.run(agent="agent-a", dataset=cast(Any, dataset), evaluation=cast(Any, evaluation), round=0)

    assert len(calls) == 1
    assert calls[0]["client"] is None
    assert calls[0]["workspace"] is None


@pytest.mark.asyncio
async def test_run_threads_metric_contract_into_trace_analyzer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Trace analysis receives the same objective and regression metrics as selection."""
    calls: list[dict[str, Any]] = []
    _install_fakes(monkeypatch, calls)
    trial, dataset, evaluation = _fixtures()
    analyzer = _make_analyzer(tmp_path, [trial])
    objective_metrics = [{"name": "success_rate", "direction": "maximize"}]
    regression_metrics = [{"name": "tokens", "direction": "minimize"}]

    await analyzer.run(
        agent="agent-a",
        dataset=cast(Any, dataset),
        evaluation=cast(Any, evaluation),
        round=0,
        objective_metrics=objective_metrics,
        regression_metrics=regression_metrics,
    )

    assert calls[0]["objective_metrics"] == objective_metrics
    assert calls[0]["regression_metrics"] == regression_metrics


@pytest.mark.asyncio
async def test_run_threads_numeric_objective_targets_into_trace_analyzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that trace analysis receives a numeric objective target."""
    calls: list[dict[str, Any]] = []
    _install_fakes(monkeypatch, calls)
    trial, dataset, evaluation = _fixtures()
    analyzer = _make_analyzer(tmp_path, [trial])
    objective_metrics = [{"name": "reward", "direction": "maximize", "target": 1.0}]

    await analyzer.run(
        agent="agent-a",
        dataset=cast(Any, dataset),
        evaluation=cast(Any, evaluation),
        round=0,
        objective_metrics=objective_metrics,
    )

    assert calls[0]["objective_metrics"] == objective_metrics


def _placeholder_reply() -> LLMResponse:
    """A scripted turn where the model answers with a placeholder instead of a selection."""
    return LLMResponse(
        raw_response=None,
        content="<result>",
        tool_calls=[],
        finish_reason="stop",
        assistant_message={"role": "assistant", "content": "<result>"},
    )


def _selection_reply(trial_id: str) -> LLMResponse:
    """A scripted turn that returns a valid selection through the return_result tool."""
    result = [{"trial_id": trial_id, "reason": "Lowest reward of the round."}]
    return LLMResponse(
        raw_response=None,
        content="",
        tool_calls=[ToolCall(id="call_return", name="return_result", arguments=json.dumps({"result": result}))],
        finish_reason="tool_calls",
        assistant_message={"role": "assistant", "content": ""},
    )


@pytest.mark.asyncio
async def test_select_trials_allows_a_model_several_attempts_at_the_contract(tmp_path: Path) -> None:
    """Four placeholder answers, then a valid one, on the real CodeAct harness.

    The framework defaults stop at three, and two separate guards have to allow the
    extra room: the shared malformed-reply budget and the consecutive plain-text
    counter, which a placeholder answer spends at the same time.
    """
    fake = FakeLLMClient(scripted_responses=[*[_placeholder_reply() for _ in range(4)], _selection_reply("trial-weak")])
    evaluation = EvaluationResult(
        id="eval-1",
        aggregate_metrics={"reward": 0.0},
        trials=[
            TrialResult(
                id="trial-weak",
                task_id="task-1",
                status="completed",
                metrics={"reward": MetricResult(name="reward", value=0.0)},
            )
        ],
    )

    with activate_model_clients(ConfiguredModelClients(default=cast(Any, fake), fast=cast(Any, fake))):
        analyzer = AgentAnalyzer(workspace=tmp_path)
        selections = await analyzer.select_trials(
            "agent-0",
            cast(Any, _FakeDataset(tasks=[_FakeTask(id="task-1")])),
            evaluation,
            [{"name": "reward", "direction": "maximize"}],
            [],
        )

    assert [selection.trial_id for selection in selections] == ["trial-weak"]


@pytest.mark.asyncio
async def test_intake_availability_is_part_of_cache_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A trace-skipped (no client) result must not be replayed once a client is available."""
    calls: list[dict[str, Any]] = []
    _install_fakes(monkeypatch, calls)
    trial, dataset, evaluation = _fixtures()

    # Same workspace/tmp_path across both runs, so the on-disk cache persists.
    analyzer_no_client = _make_analyzer(tmp_path, [trial])
    await analyzer_no_client.run(agent="agent-a", dataset=cast(Any, dataset), evaluation=cast(Any, evaluation), round=0)

    analyzer_with_client = _make_analyzer(tmp_path, [trial])
    await analyzer_with_client.run(
        agent="agent-a",
        dataset=cast(Any, dataset),
        evaluation=cast(Any, evaluation),
        round=0,
        client=cast(Any, object()),
        nmp_workspace="ws-1",
    )

    # The second (intake-available) run must recompute rather than reuse the
    # trace-skipped cache entry from the first run.
    assert len(calls) == 2
    assert calls[0]["client"] is None
    assert calls[1]["client"] is not None
