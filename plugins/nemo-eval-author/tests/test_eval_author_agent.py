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
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, MetricAuthoringResult
from nemo_experimentalist_plugin.entities import Dataset, DatasetValidationError, ResourceRef, Task, TrialResult
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
    train_dataset: Dataset
    validation_dataset: Dataset
    insight_suite: Dataset
    suite_discards: int = 0


class _MaterializedDataset(Dataset):
    def __init__(
        self,
        dataset_id: str,
        root: Path,
        events: list[str],
        validation_errors: list[str] | None = None,
    ) -> None:
        root.mkdir(parents=True)
        (root / "dataset.txt").write_text(dataset_id, encoding="utf-8")
        super().__init__(id=dataset_id, source=ResourceRef(uri=root.as_uri()))
        self.events = events
        self.validation_errors = validation_errors or []

    async def validate(self) -> None:
        self.events.append(f"validate:{self.id}")
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
    validation_errors: dict[str, list[str]] | None = None,
) -> _Calls:
    events: list[str] = []
    failures = validation_errors or {}
    train_dataset = _MaterializedDataset(
        "train",
        eval_author.experiment_dir / "datasets" / "train",
        events,
        failures.get("train"),
    )
    validation_dataset = _MaterializedDataset(
        "validation",
        eval_author.experiment_dir / "datasets" / "validation",
        events,
        failures.get("validation"),
    )
    materialized = _MaterializedDataset(
        "insight-suite",
        eval_author.experiment_dir / "insight-root" / "insight-suite",
        events,
        failures.get("insight"),
    )
    calls = _Calls(
        events=events,
        filled_refs=[],
        analyzed_refs=[],
        diagnostics=[],
        author_feedback=[],
        train_dataset=train_dataset,
        validation_dataset=validation_dataset,
        insight_suite=materialized,
    )
    analyzer_index = 0

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
            assert dataset is train_dataset
            calls.events.append("discover")
            return "runner conventions"

    class AuthorInsightMetrics:
        async def __call__(
            self,
            insight: Insight,
            diagnostics: list[tuple[str, Diagnostic]],
            authored_train_dataset: Dataset,
            authored_validation_dataset: Dataset,
            insight_suite: Dataset,
            runner_conventions: str,
            validation_feedback: str | None = None,
        ) -> MetricAuthoringResult:
            del insight, runner_conventions
            assert authored_train_dataset is train_dataset
            assert authored_validation_dataset is validation_dataset
            assert insight_suite is materialized
            calls.events.append("author")
            calls.diagnostics = diagnostics
            calls.author_feedback.append(validation_feedback)
            return MetricAuthoringResult(
                metric_keys=("uses_correct_tool",),
                summary="Authored tool-use metric.",
            )

    eval_author.fill_task_template = cast(Any, FillTaskTemplate())
    eval_author.discover_runner = cast(Any, DiscoverRunner())
    eval_author.author_insight_metrics = cast(Any, AuthorInsightMetrics())
    monkeypatch.setattr(eval_author_module, "InsightSuite", FakeInsightSuite)
    monkeypatch.setattr(eval_author_module, "TraceAnalyzer", FakeTraceAnalyzer)
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)
    monkeypatch.setattr(eval_author_module, "doc", lambda *_args, **_kwargs: "dataset docs")
    return calls


def test_metric_authoring_prompt_limits_edits_and_result_shape() -> None:
    prompt = " ".join((inspect.getdoc(EvalAuthor.author_insight_metrics) or "").split())

    assert "every task in ``train_dataset``, ``validation_dataset``, and ``insight_suite``" in prompt
    assert "task-specific verifier edits" in prompt.lower()
    assert "Do not hard-code scores for the production traces" in prompt
    assert "MetricAuthoringResult" in prompt
    assert "metric_keys" in prompt
    assert "verifier_bundle" not in prompt


@pytest.mark.asyncio
async def test_run_returns_input_datasets_without_trace_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path)
    calls = _install_pipeline(monkeypatch, eval_author, [])

    result = await eval_author.run(
        _insight([]),
        Path("agent"),
        Task(id="template"),
        calls.train_dataset,
        calls.validation_dataset,
        client=cast(Any, object()),
    )

    assert result.train_dataset is calls.train_dataset
    assert result.validation_dataset is calls.validation_dataset
    assert result.insight_suite is None
    assert result.insight_suite_identity is None
    assert result.metric_keys == ()
    assert cast(_ClosingShell, eval_author.shell).close_calls == 1


@pytest.mark.asyncio
async def test_run_materializes_authors_validates_and_returns_datasets(
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
        calls.train_dataset,
        calls.validation_dataset,
        client=cast(Any, object()),
    )

    assert calls.filled_refs == ["trace-1", "trace-2"]
    assert calls.analyzed_refs == ["trace-1", "trace-2"]
    assert calls.diagnostics == [("trace-1", diagnostic), ("trace-2", diagnostic)]
    assert calls.events == [
        "discover",
        "author",
        "validate:train",
        "validate:validation",
        "validate:insight-suite",
        "finalize",
    ]
    assert result.train_dataset is calls.train_dataset
    assert result.validation_dataset is calls.validation_dataset
    assert result.insight_suite is calls.insight_suite
    assert result.insight_suite_identity == f"sha256:{'a' * 64}"
    assert result.metric_keys == ("uses_correct_tool",)
    assert result.summary == "Authored tool-use metric."


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
        validation_errors={"validation": ["task 'task-a': tests/check.py: invalid syntax"]},
    )

    await eval_author.run(
        _insight(["trace-1"]),
        Path("agent"),
        Task(id="template"),
        calls.train_dataset,
        calls.validation_dataset,
        client=cast(Any, object()),
    )

    assert calls.author_feedback[0] is None
    assert "validation" in cast(str, calls.author_feedback[1])
    assert "invalid syntax" in cast(str, calls.author_feedback[1])
    assert calls.events.count("author") == 2
    assert calls.events.count("validate:train") == 2
    assert calls.events.count("validate:validation") == 2
    assert calls.events.count("validate:insight-suite") == 2


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
            calls.train_dataset,
            calls.validation_dataset,
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
            calls.train_dataset,
            calls.validation_dataset,
            client=cast(Any, object()),
        )

    assert "author" not in calls.events
