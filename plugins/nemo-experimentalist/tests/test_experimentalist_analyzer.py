# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for AgentAnalyzer client/workspace plumbing.

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
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from nemo_experimentalist_plugin.experimentalist.components import analyzer as analyzer_module
from nemo_experimentalist_plugin.experimentalist.components.analyzer import (
    AgentAnalyzer,
    AnalyzerConfig,
    FailureClassification,
    PeerComparison,
)
from nemo_experimentalist_plugin.experimentalist.components.model_config import ModelTiers
from nemo_experimentalist_plugin.experimentalist.components.rationalizer import Rationale
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import Diagnostic


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


class _RecordingTraceAnalyzer:
    """Stand-in for TraceAnalyzer that records the run() call context.

    ``calls`` is a class attribute so subclasses can point it at a per-test list.
    """

    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(
        self,
        *,
        experiment_dir: Path,
        config: Any,
        framework_skills_dirs: list[Path] | None = None,
        models: Any = None,
    ) -> None:
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
        client: Any = None,
        workspace: Any = None,
    ) -> Diagnostic:
        type(self).calls.append({"client": client, "workspace": workspace})
        return Diagnostic(outcome="SUCCESS", summary="stub", failure_point=None, root_cause="stub")


class _FakeRationalizer:
    def __init__(
        self,
        *,
        workspace: Path,
        config: Any,
        framework_skills_dirs: list[Path] | None = None,
        models: Any = None,
    ) -> None:
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

    async def __call__(self, agent_id: str, dataset: Any, evaluation: Any) -> list[Any]:
        return self._trials


class _ClassifyFailures:
    async def __call__(self, agent_id: str, diagnoses: Any, trials: Any) -> FailureClassification:
        return FailureClassification(systematic=[], mechanical=[])


class _CompareWithPeers:
    async def __call__(
        self, agent_id: str, evaluation: Any, diagnoses: Any, peer_evaluations: Any = None
    ) -> PeerComparison:
        return PeerComparison(divergent_trials=[], complementary_patterns=[])


def _make_analyzer(tmp_path: Path, trials: list[Any]) -> AgentAnalyzer:
    """Build an AgentAnalyzer without the LLM-heavy __init__ and stub its strategies."""
    analyzer = object.__new__(AgentAnalyzer)
    analyzer._workspace_path = tmp_path
    analyzer._config = AnalyzerConfig()
    analyzer._framework_skills_dirs = []
    # __init__ is skipped, so supply what run() reads: it hands its tiers to the
    # sub-components it builds.
    analyzer._models = ModelTiers()
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
    return trial, dataset, _FakeEvaluation()


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


def test_a_method_level_tier_reaches_the_model_it_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The canary for tier injection: nothing else proves a method-level ``llm=`` works.

    ``AgentAnalyzer`` binds the smart tier at the class level but overrides
    ``select_trials`` onto the fast one. The tests above deliberately stub past the
    decorator, so if that override silently stopped resolving — a nooa pin bump dropping
    callable ``llm=`` support is how it would happen — every one of them would still pass
    while the run quietly moved to the wrong, more expensive model.

    Resolved through nooa's own ``resolve_method_llm`` rather than by calling the method,
    so this asserts on our wiring and needs no LLM.

    The tiers are set through the environment rather than passed to
    ``ExperimentalistConfig``, because for a ``NemoConfig`` the environment wins over
    constructor arguments — passing them here would read back whatever the suite's
    conftest exported, and all three tiers would collapse onto one client.
    """
    from nemo_experimentalist_plugin.experimentalist.components.model_config import ModelTiers
    from nemo_experimentalist_plugin.settings import ExperimentalistConfig
    from nemo_platform_plugin.config import Configuration
    from nooa.method_llm import resolve_method_llm

    monkeypatch.setenv("NEMO_EXPERIMENTALIST_API_BASE", "http://canary.invalid/v1")
    monkeypatch.setenv("NEMO_EXPERIMENTALIST_API_KEY", "canary-key")
    for tier in ("SMART", "MID", "FAST"):
        monkeypatch.setenv(f"NEMO_EXPERIMENTALIST_MODELS_{tier}", f"canary/{tier.lower()}")
    Configuration.clear_cache()

    tiers = ModelTiers(ExperimentalistConfig())
    assert tiers.fast is not tiers.smart, "the tiers must be distinguishable for this to prove anything"
    analyzer = AgentAnalyzer(workspace=tmp_path, models=tiers)

    resolved = resolve_method_llm(
        AgentAnalyzer.select_trials._strategy_llm,  # type: ignore[attr-defined]
        analyzer,
        "select_trials",
    )

    assert resolved is tiers.fast
    assert resolved is not tiers.smart, "the method-level override never took effect"
