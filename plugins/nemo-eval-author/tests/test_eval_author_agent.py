# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic contract tests for the canonical top-level Eval Author agent."""

import asyncio
import inspect
import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast, get_type_hints

import pytest
from nemo_eval_author_plugin.eval_author import agent as eval_author_module
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor
from nemo_eval_author_plugin.eval_author.inventory import ReferenceTaskSetInventory
from nemo_eval_author_plugin.eval_author.models import (
    AuthoredMetric,
    AuthoredMetricContract,
    EvalAuthorConfig,
    MetricAuthoringResult,
)
from nemo_experimentalist_plugin.entities import Dataset, DatasetValidationError, Task, TrialResult
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import (
    Diagnostic,
    TraceAnalyzerConfig,
)
from nemo_insights_plugin.entities import Insight


@dataclass
class _FillTaskTemplateCall:
    trace_ref: str
    task_template: Task
    client: Any
    workspace: str
    result: Task


@dataclass
class _AnalyzerInitCall:
    experiment_dir: Path
    config: TraceAnalyzerConfig


@dataclass
class _AnalyzerRunCall:
    trial: TrialResult
    task: Task
    agent_path: Path
    insight: Insight
    client: Any
    workspace: str


@dataclass
class _PipelineCalls:
    fill_task_template: list[_FillTaskTemplateCall]
    analyzer_init: list[_AnalyzerInitCall]
    analyzer_run: list[_AnalyzerRunCall]
    discovered_datasets: list[Dataset]
    author_args: list[
        tuple[
            Insight,
            list[tuple[str, Diagnostic]],
            Dataset,
            ReferenceTaskSetInventory,
            str,
            str | None,
        ]
    ]
    suite_discards: int


@dataclass
class _ClosingShell:
    close_calls: int = 0

    async def close(self) -> None:
        self.close_calls += 1


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


def _eval_author(
    tmp_path: Path,
    *,
    max_traces: int = 10,
    max_summary_tokens: int = 80_000,
    max_validation_repair_attempts: int = 5,
    reporter: Any = None,
) -> EvalAuthor:
    eval_author = object.__new__(EvalAuthor)
    eval_author.experiment_dir = tmp_path
    eval_author._config = EvalAuthorConfig(
        max_traces=max_traces,
        max_summary_tokens=max_summary_tokens,
        max_validation_repair_attempts=max_validation_repair_attempts,
    )
    eval_author._reporter = reporter
    eval_author.context = {}
    eval_author.shell = cast(Any, _ClosingShell())
    return eval_author


def _diagnostic(summary: str) -> Diagnostic:
    return Diagnostic(outcome="FAILURE", summary=summary, failure_point=1, root_cause="wrong tool")


def _authoring_result(summary: str = "authored insight metrics") -> MetricAuthoringResult:
    return MetricAuthoringResult(
        metric_contract=AuthoredMetricContract(
            metrics=(
                AuthoredMetric(
                    key="uses_correct_tool",
                    description="Measures whether the current run used the required tool.",
                    runtime_evidence=("Current-run OTLP tool spans",),
                ),
            )
        ),
        summary=summary,
    )


def _prompt(method: Any) -> str:
    prompt = inspect.getdoc(method)
    assert prompt is not None
    return " ".join(prompt.split())


def test_eval_author_prompts_scope_metrics_to_materialized_insight_suite() -> None:
    discover_prompt = _prompt(EvalAuthor.discover_runner)
    author_prompt = _prompt(EvalAuthor.author_insight_metrics)

    assert "read it first" in discover_prompt
    assert "inspect the actual files" in discover_prompt
    assert "authoritative reference for what artifacts exist at evaluation runtime" in author_prompt
    assert "how tasks are structured, and how to add metrics" in author_prompt
    assert "Add at least one new Insight-specific metric key to every task in ``insight_suite``" in author_prompt
    assert "Preserve every existing verifier metric" in author_prompt
    assert "Do not modify the user's train or validation datasets" in author_prompt
    assert "call ``await insight_suite.validate()``" in author_prompt
    assert "fix every reported failure and revalidate the suite" in author_prompt


def test_eval_author_prompts_retain_root_cause_and_normalized_scoring_guidance() -> None:
    prompt = _prompt(EvalAuthor.author_insight_metrics)

    assert "Focus the metric on the root cause, not the surface symptom" in prompt
    assert "Every metric value must be a float in ``[0.0, 1.0]``" in prompt
    assert "Error rate → ``max(0.0, 1.0 - errors / total_calls)``" in prompt
    assert "Presence of a behavior → ``1.0`` if present, ``0.0`` if absent" in prompt
    assert "Partial credit → fraction of required steps completed correctly" in prompt
    assert "Do not hard-code scores for the production traces" in prompt


def test_author_insight_metrics_has_structured_inventory_and_result_contract() -> None:
    signature = inspect.signature(EvalAuthor.author_insight_metrics)
    hints = get_type_hints(EvalAuthor.author_insight_metrics)

    assert "reference_inventory" in signature.parameters
    assert hints["reference_inventory"] is ReferenceTaskSetInventory
    assert hints["return"] is MetricAuthoringResult


def test_eval_author_prompts_retain_template_path_and_harbor_name_guidance() -> None:
    prompt = _prompt(EvalAuthor.fill_task_template)

    assert "``task_template.uri`` (file:// URI)" in prompt
    assert "edit this directory in place and do not copy or rename it" in prompt
    assert "Leave unfillable placeholders as-is" in prompt
    assert "keep ``[task] name`` in ``org/name``" in prompt
    assert "deterministically finalize the name and provenance" in prompt


def _install_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: Sequence[Diagnostic | BaseException],
    eval_author: EvalAuthor,
    *,
    materialized_dataset: Dataset | None = None,
) -> _PipelineCalls:
    calls = _PipelineCalls(
        fill_task_template=[],
        analyzer_init=[],
        analyzer_run=[],
        discovered_datasets=[],
        author_args=[],
        suite_discards=0,
    )
    next_analyzer = 0

    class FakeInsightSuite:
        def __init__(self, *, task_template: Task, **_: Any) -> None:
            self.task_template = task_template
            self.staged: list[Any] = []

        def stage(self, trace_refs: list[str]) -> list[Any]:
            self.staged = [
                type(
                    "StagedTask",
                    (),
                    {"trace_ref": trace_ref, "task": self.task_template, "result": None},
                )()
                for trace_ref in trace_refs
            ]
            return self.staged

        def validate(self, staged: Any) -> None:
            staged.result = calls.fill_task_template[-1].result

        def promote_local(self, trace_refs: list[str], staged_tasks: list[Any]) -> Dataset:
            assert trace_refs == [staged.trace_ref for staged in staged_tasks]
            tasks = [staged.result for staged in staged_tasks]
            if materialized_dataset is not None:
                materialized_dataset.tasks = tasks
                self.materialized_dataset = materialized_dataset
                return materialized_dataset
            self.materialized_dataset = Dataset(id="insight-suite", tasks=tasks)
            return self.materialized_dataset

        def discard(self) -> None:
            calls.suite_discards += 1

        def record_analysis(self, statuses: dict[str, tuple[str, str | None]]) -> None:
            pass

        def finalize(self) -> SimpleNamespace:
            identity = "sha256:" + "a" * 64
            scorer_identity = "sha256:" + "b" * 64
            self.materialized_dataset.metadata.update(
                {
                    "insight_suite_identity": identity,
                    "insight_suite_scorer_identity": scorer_identity,
                    "insight_suite_task_hashes": {
                        task.id: {
                            "content_hash": "sha256:" + "c" * 64,
                            "verifier_hash": "sha256:" + "d" * 64,
                        }
                        for task in self.materialized_dataset.list_tasks()
                    },
                }
            )
            return SimpleNamespace(
                dataset=self.materialized_dataset,
                identity=identity,
                scorer_identity=scorer_identity,
                path=eval_author.experiment_dir / "authored-task-set",
            )

    class FillTaskTemplate:
        async def __call__(
            self,
            trace_ref: str,
            task_template: Task,
            client: Any,
            workspace: str,
        ) -> Task:
            result = Task(id=f"task-{trace_ref}", uri=f"file:///tasks/{trace_ref}")
            calls.fill_task_template.append(
                _FillTaskTemplateCall(
                    trace_ref=trace_ref,
                    task_template=task_template,
                    client=client,
                    workspace=workspace,
                    result=result,
                )
            )
            return result

    class FakeTraceAnalyzer:
        def __init__(self, *, experiment_dir: Path, config: TraceAnalyzerConfig) -> None:
            nonlocal next_analyzer
            self._index = next_analyzer
            next_analyzer += 1
            calls.analyzer_init.append(_AnalyzerInitCall(experiment_dir=experiment_dir, config=config))

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
            calls.analyzer_run.append(
                _AnalyzerRunCall(
                    trial=trial,
                    task=task,
                    agent_path=agent_path,
                    insight=insight,
                    client=client,
                    workspace=workspace,
                )
            )
            outcome = outcomes[self._index]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    class DiscoverRunner:
        async def __call__(self, dataset: Dataset) -> str:
            calls.discovered_datasets.append(dataset)
            return "runner conventions"

    class AuthorInsightMetrics:
        async def __call__(
            self,
            insight: Insight,
            diagnostics: list[tuple[str, Diagnostic]],
            insight_suite: Dataset,
            reference_inventory: ReferenceTaskSetInventory,
            runner_conventions: str,
            validation_feedback: str | None = None,
        ) -> MetricAuthoringResult:
            calls.author_args.append(
                (
                    insight,
                    diagnostics,
                    insight_suite,
                    reference_inventory,
                    runner_conventions,
                    validation_feedback,
                )
            )
            return _authoring_result()

    eval_author.fill_task_template = cast(Any, FillTaskTemplate())
    eval_author.discover_runner = cast(Any, DiscoverRunner())
    eval_author.author_insight_metrics = cast(Any, AuthorInsightMetrics())
    monkeypatch.setattr(eval_author_module, "TraceAnalyzer", FakeTraceAnalyzer)
    monkeypatch.setattr(eval_author_module, "InsightSuite", FakeInsightSuite)
    return calls


@pytest.mark.asyncio
async def test_run_without_traces_returns_explicit_no_artifact_result(tmp_path: Path) -> None:
    eval_author = _eval_author(tmp_path)

    result = await eval_author.run(
        _insight([]),
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=cast(Any, object()),
    )

    assert result.task_set is None
    assert result.verifier_patch is None
    assert result.metric_contract is None
    assert result.summary == "No trace refs on insight — nothing to analyze."
    assert cast(_ClosingShell, eval_author.shell).close_calls == 1


@pytest.mark.asyncio
async def test_run_requires_persisted_insight_id(tmp_path: Path) -> None:
    insight = Insight(
        workspace="workspace-a",
        title="Tool selection failures",
        description="The agent selects the wrong tool.",
        agent="research-agent",
        trace_refs=["trace-1"],
    )

    with pytest.raises(ValueError, match="persisted Insight with a durable id"):
        await _eval_author(tmp_path).run(
            insight,
            Path("agent"),
            Task(id="template"),
            ReferenceTaskSetInventory.empty(),
            client=cast(Any, object()),
        )


@pytest.mark.asyncio
async def test_run_enforces_max_traces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = [_diagnostic("one"), _diagnostic("two")]
    eval_author = _eval_author(tmp_path, max_traces=2)
    calls = _install_pipeline(monkeypatch, diagnostics, eval_author)
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)

    await eval_author.run(
        _insight(["trace-1", "trace-2", "trace-3"]),
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=cast(Any, object()),
    )

    assert [call.trace_ref for call in calls.fill_task_template] == ["trace-1", "trace-2"]
    assert [call.trial.metadata["trace_ref"] for call in calls.analyzer_run] == ["trace-1", "trace-2"]


@pytest.mark.asyncio
async def test_run_discards_staged_suite_when_filling_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path)
    calls = _install_pipeline(monkeypatch, [], eval_author)

    class FailedFillTaskTemplate:
        async def __call__(self, *_: Any) -> Task:
            raise RuntimeError("fill failed")

    eval_author.fill_task_template = cast(Any, FailedFillTaskTemplate())

    with pytest.raises(RuntimeError, match="fill failed"):
        await eval_author.run(
            _insight(["trace-1"]),
            Path("agent"),
            Task(id="template"),
            ReferenceTaskSetInventory.empty(),
            client=cast(Any, object()),
        )

    assert calls.suite_discards == 1
    assert cast(_ClosingShell, eval_author.shell).close_calls == 1


def test_trace_trial_uses_intake_uri_and_insight_metadata(tmp_path: Path) -> None:
    insight = _insight(["trace-7"])

    trial = _eval_author(tmp_path)._trace_trial(insight, Task(id="task-7"), "trace-7", 3, insight.id)

    assert trial.id == "insight-trace-3"
    assert trial.task_id == "task-7"
    assert trial.status == "completed"
    assert trial.trace is not None
    assert trial.trace.uri == "intake://trace-7"
    assert trial.trace.description == "Production trace attached to the insight."
    assert trial.metadata == {
        "source": "insight",
        "trace_ref": "trace-7",
        "insight_id": insight.id,
    }


@pytest.mark.asyncio
async def test_run_caches_each_successful_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _diagnostic("first")
    second = _diagnostic("second")
    eval_author = _eval_author(tmp_path)
    _install_pipeline(monkeypatch, [first, second], eval_author)
    stored: list[tuple[Path, str, Diagnostic]] = []
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: stored.append(args))

    await eval_author.run(
        _insight(["trace-a", "trace-b"]),
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=cast(Any, object()),
    )

    assert stored == [
        (tmp_path, eval_author_module.cache.task_hash("eval_author:trace-a"), first),
        (tmp_path, eval_author_module.cache.task_hash("eval_author:trace-b"), second),
    ]


@pytest.mark.asyncio
async def test_run_skips_failed_trace_analysis_and_keeps_successes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    successful = _diagnostic("successful")
    eval_author = _eval_author(tmp_path)
    calls = _install_pipeline(monkeypatch, [RuntimeError("analysis failed"), successful], eval_author)
    stored: list[Diagnostic] = []
    monkeypatch.setattr(eval_author_module.cache, "store", lambda workspace, key, value: stored.append(value))
    insight = _insight(["trace-bad", "trace-good"])

    result = await eval_author.run(
        insight,
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=cast(Any, object()),
    )

    assert result.summary == "authored insight metrics"
    assert stored == [successful]
    assert calls.author_args[0][1] == [("trace-good", successful)]
    assert "Trace analysis failed for trace-bad: analysis failed" in caplog.text


@pytest.mark.asyncio
async def test_run_propagates_trace_analysis_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path)
    calls = _install_pipeline(monkeypatch, [asyncio.CancelledError()], eval_author)
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)

    with pytest.raises(asyncio.CancelledError):
        await eval_author.run(
            _insight(["trace-cancelled"]),
            Path("agent"),
            Task(id="template"),
            ReferenceTaskSetInventory.empty(),
            client=cast(Any, object()),
        )

    assert calls.author_args == []


@pytest.mark.asyncio
async def test_run_authors_metrics_on_materialized_insight_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic = _diagnostic("diagnostic")
    eval_author = _eval_author(tmp_path, max_summary_tokens=12_345)
    calls = _install_pipeline(monkeypatch, [diagnostic], eval_author)
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)
    documentation = object()
    doc_calls: list[tuple[type[Dataset], int]] = []

    def fake_doc(dataset_type: type[Dataset], *, inline_depth: int) -> object:
        doc_calls.append((dataset_type, inline_depth))
        return documentation

    monkeypatch.setattr(eval_author_module, "doc", fake_doc)
    insight = _insight(["trace-1"])
    task_template = Task(id="template")
    expected_reference_inventory = ReferenceTaskSetInventory.empty()
    client = cast(Any, object())

    result = await eval_author.run(
        insight,
        Path("relative-agent"),
        task_template,
        expected_reference_inventory,
        client=client,
    )

    assert result.summary == "authored insight metrics"
    assert len(calls.fill_task_template) == 1
    fill_call = calls.fill_task_template[0]
    assert fill_call.trace_ref == "trace-1"
    assert fill_call.task_template is task_template
    assert fill_call.client is client
    assert fill_call.workspace == "workspace-a"
    assert fill_call.result == Task(id="task-trace-1", uri="file:///tasks/trace-1")

    assert len(calls.analyzer_init) == 1
    assert calls.analyzer_init[0].experiment_dir == tmp_path
    assert type(calls.analyzer_init[0].config) is TraceAnalyzerConfig
    assert calls.analyzer_init[0].config.max_summary_tokens == 12_345

    assert len(calls.analyzer_run) == 1
    analyzer_call = calls.analyzer_run[0]
    assert analyzer_call.trial == eval_author._trace_trial(
        insight,
        fill_call.result,
        "trace-1",
        1,
        insight.id,
    )
    assert analyzer_call.task is fill_call.result
    assert analyzer_call.agent_path == tmp_path / "relative-agent"
    assert analyzer_call.insight is insight
    assert analyzer_call.client is client
    assert analyzer_call.workspace == "workspace-a"

    assert doc_calls == [(Dataset, 1)]
    assert eval_author.context["dataset_documentation"] is documentation
    assert len(calls.discovered_datasets) == 1
    materialized_dataset = calls.discovered_datasets[0]
    assert result.task_set is not None
    assert result.task_set.uri == (tmp_path / "authored-task-set").resolve().as_uri()
    assert result.task_set.identity == f"sha256:{'a' * 64}"
    assert result.verifier_patch is None
    assert result.metric_contract == _authoring_result().metric_contract
    assert materialized_dataset.id == "insight-suite"
    assert len(calls.author_args) == 1
    (
        authored_insight,
        diagnostics,
        authored_suite,
        authored_reference_inventory,
        runner_conventions,
        validation_feedback,
    ) = calls.author_args[0]
    assert authored_insight is insight
    assert diagnostics == [("trace-1", diagnostic)]
    assert authored_suite is materialized_dataset
    assert authored_reference_inventory is expected_reference_inventory
    assert runner_conventions == "runner conventions"
    assert validation_feedback is None


class _RepairableDataset(Dataset):
    def __init__(self, id: str, error: str | None) -> None:
        super().__init__(id=id)
        self.error = error
        self.validate_calls = 0

    async def validate(self) -> None:
        self.validate_calls += 1
        if self.error is not None:
            raise DatasetValidationError(self.error)


@pytest.mark.asyncio
async def test_run_feeds_validation_failures_back_for_one_repair_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path)
    insight_dataset = _RepairableDataset("insight-suite", "task 'insight-a': check.py:2:1: invalid syntax")
    _install_pipeline(
        monkeypatch,
        [_diagnostic("diagnostic")],
        eval_author,
        materialized_dataset=insight_dataset,
    )
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)
    client = cast(Any, object())
    feedback: list[str | None] = []

    class RepairInsightMetrics:
        async def __call__(
            self,
            insight: Insight,
            diagnostics: list[tuple[str, Diagnostic]],
            insight_suite: Dataset,
            reference_inventory: ReferenceTaskSetInventory,
            runner_conventions: str,
            validation_feedback: str | None = None,
        ) -> MetricAuthoringResult:
            feedback.append(validation_feedback)
            if validation_feedback is not None:
                insight_dataset.error = None
            return _authoring_result("repaired insight metric")

    eval_author.author_insight_metrics = cast(Any, RepairInsightMetrics())

    result = await eval_author.run(
        _insight(["trace-1"]),
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=client,
    )

    assert result.task_set is not None
    assert result.verifier_patch is None
    assert result.metric_contract == _authoring_result().metric_contract
    assert feedback[0] is None
    assert feedback[1] is not None
    assert "task 'insight-a': check.py:2:1: invalid syntax" in feedback[1]
    assert insight_dataset.validate_calls == 2


@pytest.mark.asyncio
async def test_run_raises_after_validation_repair_budget_is_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path, max_validation_repair_attempts=1)
    insight_dataset = _RepairableDataset("insight-suite", "task 'insight-a': check.py:2:1: invalid syntax")
    calls = _install_pipeline(
        monkeypatch,
        [_diagnostic("diagnostic")],
        eval_author,
        materialized_dataset=insight_dataset,
    )
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)

    with pytest.raises(DatasetValidationError) as exc_info:
        await eval_author.run(
            _insight(["trace-1"]),
            Path("agent"),
            Task(id="template"),
            ReferenceTaskSetInventory.empty(),
            client=cast(Any, object()),
        )

    assert "task 'insight-a': check.py:2:1: invalid syntax" in str(exc_info.value)
    assert len(calls.author_args) == 2
    assert calls.author_args[0][-1] is None
    assert calls.author_args[1][-1] is not None
    assert insight_dataset.validate_calls == 2


def test_eval_author_config_defaults_and_bounds_validation_repair_attempts() -> None:
    # Experimentalist's loop config asserts this default too, but from the other side of
    # the plugin boundary; owning it here is what keeps the default a plugin contract.
    assert EvalAuthorConfig().max_validation_repair_attempts == 5
    assert EvalAuthorConfig(max_validation_repair_attempts=10).max_validation_repair_attempts == 10
    with pytest.raises(ValueError, match="less than or equal to 10"):
        EvalAuthorConfig(max_validation_repair_attempts=11)


def _string_reporter() -> tuple[Any, io.StringIO]:
    from nemo_experimentalist_plugin.experimentalist.reporting import RunReporter

    sink = io.StringIO()
    return RunReporter(sink=sink), sink


@pytest.mark.asyncio
async def test_run_with_reporter_emits_start_note_and_complete_on_empty_traces(tmp_path: Path) -> None:
    reporter, sink = _string_reporter()
    eval_author = _eval_author(tmp_path, reporter=reporter)

    await eval_author.run(
        _insight([]),
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=cast(Any, object()),
    )

    out = sink.getvalue()
    assert "eval author · starting" in out
    assert "no trace refs — nothing to analyze" in out
    assert "eval author · complete" in out


@pytest.mark.asyncio
async def test_run_with_reporter_emits_pipeline_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporter, sink = _string_reporter()
    eval_author = _eval_author(tmp_path, reporter=reporter)
    _install_pipeline(
        monkeypatch,
        [_diagnostic("trace-1 failed"), _diagnostic("trace-2 failed")],
        eval_author,
    )
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)

    result = await eval_author.run(
        _insight(["trace-1", "trace-2"]),
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=cast(Any, object()),
    )

    out = sink.getvalue()
    assert "eval author · starting" in out
    assert "eval author · materializing tasks" in out
    assert "task 2/≤2" in out
    assert "eval author · analyzing traces" in out
    assert "eval author · discovering runner" in out
    assert "eval author · authoring metrics" in out
    assert "eval author · complete" in out
    assert "Finished" not in out
    assert result.summary == "authored insight metrics"


@pytest.mark.asyncio
async def test_run_with_reporter_emits_repair_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporter, sink = _string_reporter()
    eval_author = _eval_author(tmp_path, max_validation_repair_attempts=2, reporter=reporter)
    insight_dataset = _RepairableDataset("insight-suite", "task 'insight-a': check.py:2:1: invalid syntax")
    _install_pipeline(
        monkeypatch,
        [_diagnostic("diagnostic")],
        eval_author,
        materialized_dataset=insight_dataset,
    )
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)

    class RepairInsightMetrics:
        async def __call__(
            self,
            insight: Insight,
            diagnostics: list[tuple[str, Diagnostic]],
            insight_suite: Dataset,
            reference_inventory: ReferenceTaskSetInventory,
            runner_conventions: str,
            validation_feedback: str | None = None,
        ) -> MetricAuthoringResult:
            if validation_feedback is not None:
                insight_dataset.error = None
            return _authoring_result("repaired insight metric")

    eval_author.author_insight_metrics = cast(Any, RepairInsightMetrics())

    await eval_author.run(
        _insight(["trace-1"]),
        Path("agent"),
        Task(id="template"),
        ReferenceTaskSetInventory.empty(),
        client=cast(Any, object()),
    )

    out = sink.getvalue()
    assert "eval author · repairing metrics" in out
    assert "attempt 1/≤2" in out
    assert "eval author · complete" in out
