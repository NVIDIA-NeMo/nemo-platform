# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end control flow for the Eval Author agent."""

import asyncio
import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from nemo_eval_author_plugin.eval_author import agent as eval_author_module
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor
from nemo_eval_author_plugin.eval_author.models import (
    ArtifactDescriptor,
    EvalAuthorConfig,
    MetricAuthoringResult,
)
from nemo_eval_author_plugin.eval_author.verifier_bundle import VerifierBundleValidationError
from nemo_experimentalist_plugin.entities import Dataset, DatasetValidationError, Task, TrialResult
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import (
    Diagnostic,
    TraceAnalyzerConfig,
)
from nemo_insights_plugin.entities import Insight


@dataclass
class _ClosingShell:
    close_calls: int = 0

    async def close(self) -> None:
        self.close_calls += 1


@dataclass
class _Calls:
    events: list[str]
    filled_refs: list[str]
    analyzed_refs: list[str]
    diagnostics: list[tuple[str, Diagnostic]]
    author_feedback: list[str | None]
    bundle_finalizations: int = 0
    suite_discards: int = 0


class _MaterializedDataset(Dataset):
    def __init__(self, events: list[str], validation_errors: list[str] | None = None) -> None:
        super().__init__(id="insight-suite")
        self.events = events
        self.validation_errors = validation_errors or []

    async def validate(self) -> None:
        self.events.append("validate")
        if self.validation_errors:
            raise DatasetValidationError(self.validation_errors.pop(0))


def _insight(trace_refs: list[str], *, insight_id: str = "insight-1") -> Insight:
    insight = Insight(
        workspace="workspace-a",
        title="Tool selection failures",
        description="The agent selects the wrong tool.",
        agent="research-agent",
        trace_refs=trace_refs,
    )
    insight._id = insight_id
    return insight


def _diagnostic(summary: str = "wrong tool") -> Diagnostic:
    return Diagnostic(outcome="FAILURE", summary=summary, failure_point=1, root_cause="wrong tool")


def _eval_author(
    tmp_path: Path,
    *,
    max_traces: int = 10,
    max_validation_repair_attempts: int = 5,
) -> EvalAuthor:
    eval_author = object.__new__(EvalAuthor)
    eval_author.experiment_dir = tmp_path
    eval_author._config = EvalAuthorConfig(
        max_traces=max_traces,
        max_validation_repair_attempts=max_validation_repair_attempts,
    )
    eval_author._reporter = None
    eval_author.context = {}
    eval_author.shell = cast(Any, _ClosingShell())
    return eval_author


def _install_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    eval_author: EvalAuthor,
    outcomes: Sequence[Diagnostic | BaseException],
    *,
    validation_errors: list[str] | None = None,
    bundle_failures: int = 0,
) -> _Calls:
    calls = _Calls(events=[], filled_refs=[], analyzed_refs=[], diagnostics=[], author_feedback=[])
    materialized = _MaterializedDataset(calls.events, validation_errors)
    analyzer_index = 0
    bundle_attempt = 0

    class FakeInsightSuite:
        def __init__(self, *, task_template: Task, **_: Any) -> None:
            self.task_template = task_template
            self.root = eval_author.experiment_dir / "insight-root"
            self.suite_dir = self.root / "insight-suite"

        def stage(self, trace_refs: list[str]) -> list[Any]:
            return [
                SimpleNamespace(trace_ref=trace_ref, task=self.task_template, result=None) for trace_ref in trace_refs
            ]

        def validate(self, staged: Any) -> None:
            staged.result = Task(id=f"task-{staged.trace_ref}", uri=f"file:///tasks/{staged.trace_ref}")

        def promote_local(self, trace_refs: list[str], staged_tasks: list[Any]) -> Dataset:
            assert trace_refs == [staged.trace_ref for staged in staged_tasks]
            materialized.tasks = [staged.result for staged in staged_tasks]
            return materialized

        def record_analysis(self, statuses: dict[str, tuple[str, str | None]]) -> None:
            del statuses

        def finalize(self) -> SimpleNamespace:
            calls.events.append("finalize")
            return SimpleNamespace(
                identity=f"sha256:{'a' * 64}",
                path=self.suite_dir,
                dataset=materialized,
            )

        def discard(self) -> None:
            calls.suite_discards += 1

    class FakeTraceAnalyzer:
        def __init__(self, *, experiment_dir: Path, config: TraceAnalyzerConfig) -> None:
            nonlocal analyzer_index
            del experiment_dir, config
            self.index = analyzer_index
            analyzer_index += 1

        async def run(
            self,
            *,
            trial: TrialResult,
            task: Task,
            agent_path: Path,
            insight: Insight,
            client: Any,
            workspace: str,
        ) -> Diagnostic:
            del task, agent_path, insight, client, workspace
            ref = cast(str, trial.metadata["trace_ref"])
            calls.analyzed_refs.append(ref)
            outcome = outcomes[self.index]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    class FillTaskTemplate:
        async def __call__(
            self,
            trace_ref: str,
            task_template: Task,
            client: Any,
            workspace: str,
        ) -> Task:
            del task_template, client, workspace
            calls.filled_refs.append(trace_ref)
            return Task(id=f"task-{trace_ref}", uri=f"file:///tasks/{trace_ref}")

    class DiscoverRunner:
        async def __call__(self, dataset: Dataset) -> str:
            assert dataset is materialized
            calls.events.append("discover")
            return "runner conventions"

    class AuthorInsightMetrics:
        async def __call__(
            self,
            insight: Insight,
            diagnostics: list[tuple[str, Diagnostic]],
            insight_suite: Dataset,
            runner_conventions: str,
            verifier_bundle_dir: Path,
            validation_feedback: str | None = None,
        ) -> MetricAuthoringResult:
            del insight, insight_suite, runner_conventions
            assert verifier_bundle_dir == eval_author.experiment_dir / "insight-root" / "verifier-bundle" / "files"
            calls.events.append("author")
            calls.diagnostics = diagnostics
            calls.author_feedback.append(validation_feedback)
            return MetricAuthoringResult(
                metric_keys=("uses_correct_tool",),
                summary="Authored tool-use metric.",
            )

    def finalize_verifier_bundle(
        bundle_root: Path,
        dataset: Dataset,
        *,
        metric_keys: tuple[str, ...],
    ) -> ArtifactDescriptor:
        nonlocal bundle_attempt
        assert dataset is materialized
        assert metric_keys == ("uses_correct_tool",)
        calls.events.append("bundle")
        bundle_attempt += 1
        if bundle_attempt <= bundle_failures:
            raise VerifierBundleValidationError("bundle file is not installed in every task")
        calls.bundle_finalizations += 1
        return ArtifactDescriptor(
            uri=bundle_root.resolve().as_uri(),
            identity=f"sha256:{'b' * 64}",
        )

    eval_author.fill_task_template = cast(Any, FillTaskTemplate())
    eval_author.discover_runner = cast(Any, DiscoverRunner())
    eval_author.author_insight_metrics = cast(Any, AuthorInsightMetrics())
    monkeypatch.setattr(eval_author_module, "InsightSuite", FakeInsightSuite)
    monkeypatch.setattr(eval_author_module, "TraceAnalyzer", FakeTraceAnalyzer)
    monkeypatch.setattr(eval_author_module, "finalize_verifier_bundle", finalize_verifier_bundle, raising=False)
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)
    monkeypatch.setattr(eval_author_module, "doc", lambda *_args, **_kwargs: "dataset docs")
    return calls


def test_metric_authoring_prompt_limits_edits_and_result_shape() -> None:
    prompt = " ".join((inspect.getdoc(EvalAuthor.author_insight_metrics) or "").split())

    assert "Only edit verifier files in the materialized Insight suite" in prompt
    assert "Add at least one new Insight-specific metric key to every task" in prompt
    assert "Do not hard-code scores for the production traces" in prompt
    assert "verifier_bundle_dir" in prompt
    assert "one reusable copy" in prompt
    assert "MetricAuthoringResult" in prompt
    assert "metric_keys" in prompt
    assert "reference inventory" not in prompt.lower()


@pytest.mark.asyncio
async def test_run_returns_explicit_no_artifacts_without_trace_refs(tmp_path: Path) -> None:
    eval_author = _eval_author(tmp_path)

    result = await eval_author.run(
        _insight([]),
        Path("agent"),
        Task(id="template"),
        client=cast(Any, object()),
    )

    assert result.task_set is None
    assert result.verifier_bundle is None
    assert result.metric_keys == ()
    assert cast(_ClosingShell, eval_author.shell).close_calls == 1


@pytest.mark.asyncio
async def test_run_materializes_authors_validates_extracts_and_returns_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path, max_traces=2)
    diagnostic = _diagnostic()
    calls = _install_pipeline(monkeypatch, eval_author, [diagnostic, diagnostic])

    result = await eval_author.run(
        _insight(["trace-1", "trace-2", "ignored"]),
        Path("agent"),
        Task(id="template"),
        client=cast(Any, object()),
    )

    assert calls.filled_refs == ["trace-1", "trace-2"]
    assert calls.analyzed_refs == ["trace-1", "trace-2"]
    assert calls.diagnostics == [("trace-1", diagnostic), ("trace-2", diagnostic)]
    assert calls.events == ["discover", "author", "validate", "bundle", "finalize"]
    assert result.task_set == ArtifactDescriptor(
        uri=(tmp_path / "insight-root" / "insight-suite").resolve().as_uri(),
        identity=f"sha256:{'a' * 64}",
    )
    assert result.verifier_bundle == ArtifactDescriptor(
        uri=(tmp_path / "insight-root" / "verifier-bundle").resolve().as_uri(),
        identity=f"sha256:{'b' * 64}",
    )
    assert result.metric_keys == ("uses_correct_tool",)
    assert result.summary == "Authored tool-use metric."


@pytest.mark.asyncio
async def test_bundle_validation_failure_uses_repair_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path, max_validation_repair_attempts=1)
    calls = _install_pipeline(
        monkeypatch,
        eval_author,
        [_diagnostic()],
        bundle_failures=1,
    )

    result = await eval_author.run(
        _insight(["trace-1"]),
        Path("agent"),
        Task(id="template"),
        client=cast(Any, object()),
    )

    assert result.verifier_bundle is not None
    assert calls.events == [
        "discover",
        "author",
        "validate",
        "bundle",
        "author",
        "validate",
        "bundle",
        "finalize",
    ]
    assert calls.author_feedback == [None, "bundle file is not installed in every task"]
    assert calls.bundle_finalizations == 1


@pytest.mark.asyncio
async def test_static_validation_failure_uses_same_repair_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path, max_validation_repair_attempts=1)
    calls = _install_pipeline(
        monkeypatch,
        eval_author,
        [_diagnostic()],
        validation_errors=["task 'task-a': tests/check.py: invalid syntax"],
    )

    await eval_author.run(
        _insight(["trace-1"]),
        Path("agent"),
        Task(id="template"),
        client=cast(Any, object()),
    )

    assert calls.author_feedback[0] is None
    assert "invalid syntax" in cast(str, calls.author_feedback[1])
    assert calls.events.count("author") == 2
    assert calls.events.count("bundle") == 1
    assert calls.bundle_finalizations == 1


@pytest.mark.asyncio
async def test_run_discards_staged_tasks_and_closes_shell_when_fill_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path)
    calls = _install_pipeline(monkeypatch, eval_author, [])

    class FailFill:
        async def __call__(self, *_: object) -> Task:
            raise RuntimeError("fill failed")

    eval_author.fill_task_template = cast(Any, FailFill())
    with pytest.raises(RuntimeError, match="fill failed"):
        await eval_author.run(
            _insight(["trace-1"]),
            Path("agent"),
            Task(id="template"),
            client=cast(Any, object()),
        )

    assert calls.suite_discards == 1
    assert cast(_ClosingShell, eval_author.shell).close_calls == 1


@pytest.mark.asyncio
async def test_run_propagates_trace_analysis_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path)
    calls = _install_pipeline(monkeypatch, eval_author, [asyncio.CancelledError()])

    with pytest.raises(asyncio.CancelledError):
        await eval_author.run(
            _insight(["trace-1"]),
            Path("agent"),
            Task(id="template"),
            client=cast(Any, object()),
        )

    assert "author" not in calls.events
