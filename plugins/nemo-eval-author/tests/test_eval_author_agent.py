# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic contract tests for the canonical top-level Eval Author agent."""

import asyncio
import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from nemo_eval_author_plugin.eval_author import agent as eval_author_module
from nemo_eval_author_plugin.eval_author.agent import EvalAuthor, EvalAuthorDatasetValidationError
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    DatasetValidationError,
    Task,
    TrialResult,
)
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
    author_args: list[tuple[Insight, list[tuple[str, Diagnostic]], Dataset, Dataset, Dataset, str, str | None]]
    suite_discards: int
    split_dirs: list[tuple[Path, Path]]


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
) -> EvalAuthor:
    eval_author = object.__new__(EvalAuthor)
    eval_author.experiment_dir = tmp_path
    eval_author._config = EvalAuthorConfig(
        max_traces=max_traces,
        max_summary_tokens=max_summary_tokens,
        max_validation_repair_attempts=max_validation_repair_attempts,
    )
    eval_author.context = {}
    eval_author.shell = cast(Any, _ClosingShell())
    return eval_author


def _diagnostic(summary: str) -> Diagnostic:
    return Diagnostic(outcome="FAILURE", summary=summary, failure_point=1, root_cause="wrong tool")


def _prompt(method: Any) -> str:
    prompt = inspect.getdoc(method)
    assert prompt is not None
    return " ".join(prompt.split())


def test_eval_author_prompts_scope_metrics_across_all_three_datasets() -> None:
    discover_prompt = _prompt(EvalAuthor.discover_runner)
    author_prompt = _prompt(EvalAuthor.author_insight_metrics)

    assert "read it first" in discover_prompt
    assert "inspect the actual files" in discover_prompt
    assert "authoritative reference for what artifacts exist at evaluation runtime" in author_prompt
    assert "how tasks are structured, and how to add metrics" in author_prompt
    assert (
        "Add at least one new Insight-specific metric key to every task in ``insight_suite``, "
        "``train_dataset``, and ``validation_dataset``" in author_prompt
    )
    assert "A metric is only useful as a suite-wide signal, not a per-sample patch." in author_prompt
    assert "Preserve every existing verifier metric" in author_prompt
    assert "The metric key set must be identical across all three datasets." in author_prompt
    assert "This is a hard requirement, not a preference" in author_prompt
    assert (
        "Do not change task instructions, environments, solutions, or any other agent-visible input "
        "in any of the three datasets." in author_prompt
    )
    assert "call ``await insight_suite.validate()``" in author_prompt
    assert "``await train_dataset.validate()``" in author_prompt
    assert "``await validation_dataset.validate()``" in author_prompt
    assert "Fix every reported failure and revalidate all three." in author_prompt


def test_eval_author_prompts_retain_root_cause_and_normalized_scoring_guidance() -> None:
    prompt = _prompt(EvalAuthor.author_insight_metrics)

    assert "Focus the metric on the root cause, not the surface symptom" in prompt
    assert "Every metric value must be a float in ``[0.0, 1.0]``" in prompt
    assert "Error rate → ``max(0.0, 1.0 - errors / total_calls)``" in prompt
    assert "Presence of a behavior → ``1.0`` if present, ``0.0`` if absent" in prompt
    assert "Partial credit → fraction of required steps completed correctly" in prompt
    assert "Do not hard-code scores for the production traces" in prompt


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
        split_dirs=[],
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
            train_dataset: Dataset,
            validation_dataset: Dataset,
            runner_conventions: str,
            validation_feedback: str | None = None,
        ) -> str:
            calls.author_args.append(
                (
                    insight,
                    diagnostics,
                    insight_suite,
                    train_dataset,
                    validation_dataset,
                    runner_conventions,
                    validation_feedback,
                )
            )
            return "authored insight metrics"

    def fake_materialize_split(finalized: Any, *, train_dir: Path, validation_dir: Path) -> SimpleNamespace:
        calls.split_dirs.append((train_dir, validation_dir))
        tasks = list(finalized.dataset.list_tasks())
        return SimpleNamespace(
            train=SimpleNamespace(
                dataset=Dataset(id="insight-train", tasks=tasks[0::2]),
                identity="sha256:" + "1" * 64,
            ),
            validation=(
                SimpleNamespace(
                    dataset=Dataset(id="insight-validation", tasks=tasks[1::2]),
                    identity="sha256:" + "2" * 64,
                )
                if tasks[1::2]
                else None
            ),
        )

    eval_author.fill_task_template = cast(Any, FillTaskTemplate())
    eval_author.discover_runner = cast(Any, DiscoverRunner())
    eval_author.author_insight_metrics = cast(Any, AuthorInsightMetrics())
    monkeypatch.setattr(eval_author_module, "TraceAnalyzer", FakeTraceAnalyzer)
    monkeypatch.setattr(eval_author_module, "InsightSuite", FakeInsightSuite)
    monkeypatch.setattr(eval_author_module, "materialize_insight_split", fake_materialize_split)
    return calls


@pytest.mark.asyncio
async def test_run_without_traces_returns_input_datasets_unchanged(tmp_path: Path) -> None:
    eval_author = _eval_author(tmp_path)
    train_dataset = Dataset(id="train")
    validation_dataset = Dataset(id="validation")

    result = await eval_author.run(
        _insight([]),
        Path("agent"),
        Task(id="template"),
        train_dataset,
        validation_dataset,
        client=cast(Any, object()),
    )

    assert result.train_dataset is train_dataset
    assert result.validation_dataset is validation_dataset
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
            Dataset(id="train"),
            Dataset(id="validation"),
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
        Dataset(id="train"),
        Dataset(id="validation"),
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
            Dataset(id="train"),
            Dataset(id="validation"),
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
        Dataset(id="train"),
        Dataset(id="validation"),
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
        Dataset(id="train"),
        Dataset(id="validation"),
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
            Dataset(id="train"),
            Dataset(id="validation"),
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
    train_dataset = Dataset(id="train")
    validation_dataset = Dataset(id="validation")
    client = cast(Any, object())

    result = await eval_author.run(
        insight,
        Path("relative-agent"),
        task_template,
        train_dataset,
        validation_dataset,
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
    assert materialized_dataset.id == "insight-suite"
    assert materialized_dataset is not train_dataset
    assert materialized_dataset is not validation_dataset

    # The loop consumes the halves, not the authored suite, which stays the provenance home.
    assert calls.split_dirs == [(tmp_path / "dataset" / "insight-train", tmp_path / "dataset" / "insight-validation")]
    assert result.insight_train_suite is not None
    assert result.insight_train_suite.id == "insight-train"
    assert result.insight_train_suite_identity == f"sha256:{'1' * 64}"
    # A single trace leaves the validation half empty.
    assert result.insight_validation_suite is None
    assert result.insight_validation_suite_identity is None

    assert len(calls.author_args) == 1
    (
        authored_insight,
        diagnostics,
        authored_suite,
        authored_train,
        authored_validation,
        runner_conventions,
        validation_feedback,
    ) = calls.author_args[0]
    assert authored_insight is insight
    assert diagnostics == [("trace-1", diagnostic)]
    assert authored_suite is materialized_dataset
    assert authored_train is train_dataset
    assert authored_validation is validation_dataset
    assert runner_conventions == "runner conventions"
    assert validation_feedback is None
    assert result.train_dataset is train_dataset
    assert result.validation_dataset is validation_dataset


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
    train_dataset = Dataset(id="train")
    validation_dataset = Dataset(id="validation")
    client = cast(Any, object())
    feedback: list[str | None] = []

    class RepairInsightMetrics:
        async def __call__(
            self,
            insight: Insight,
            diagnostics: list[tuple[str, Diagnostic]],
            insight_suite: Dataset,
            train_dataset: Dataset,
            validation_dataset: Dataset,
            runner_conventions: str,
            validation_feedback: str | None = None,
        ) -> str:
            feedback.append(validation_feedback)
            if validation_feedback is not None:
                insight_dataset.error = None
            return "repaired insight metric"

    eval_author.author_insight_metrics = cast(Any, RepairInsightMetrics())

    result = await eval_author.run(
        _insight(["trace-1"]),
        Path("agent"),
        Task(id="template"),
        train_dataset,
        validation_dataset,
        client=client,
    )

    assert result.train_dataset is train_dataset
    assert result.validation_dataset is validation_dataset
    assert feedback[0] is None
    assert feedback[1] is not None
    assert "task 'insight-a': check.py:2:1: invalid syntax" in feedback[1]
    assert insight_dataset.validate_calls == 2


@pytest.mark.asyncio
async def test_validation_failure_names_every_failing_split_not_just_the_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_author = _eval_author(tmp_path, max_validation_repair_attempts=0)
    insight_dataset = _RepairableDataset("insight-suite", "insight verifier is missing uses_required_tool")
    train_dataset = _RepairableDataset("train", "train verifier is missing uses_required_tool")
    validation_dataset = _RepairableDataset("validation", None)
    _install_pipeline(
        monkeypatch,
        [_diagnostic("diagnostic")],
        eval_author,
        materialized_dataset=insight_dataset,
    )
    monkeypatch.setattr(eval_author_module.cache, "store", lambda *args: None)

    with pytest.raises(EvalAuthorDatasetValidationError) as exc_info:
        await eval_author.run(
            _insight(["trace-1"]),
            Path("agent"),
            Task(id="template"),
            train_dataset,
            validation_dataset,
            client=cast(Any, object()),
        )

    assert [failure.split for failure in exc_info.value.failures] == ["insight", "train"]
    message = str(exc_info.value)
    assert "insight dataset:\ninsight verifier is missing uses_required_tool" in message
    assert "train dataset:\ntrain verifier is missing uses_required_tool" in message
    # Every split is validated even after one fails, so the repair prompt sees the whole picture.
    assert validation_dataset.validate_calls == 1


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
            Dataset(id="train"),
            Dataset(id="validation"),
            client=cast(Any, object()),
        )

    assert "task 'insight-a': check.py:2:1: invalid syntax" in str(exc_info.value)
    assert len(calls.author_args) == 2
    assert calls.author_args[0][-1] is None
    assert calls.author_args[1][-1] is not None
    assert insight_dataset.validate_calls == 2


def _authored_task(dataset_dir: Path, task_id: str) -> Task:
    """Write a minimal Harbor task whose verifier emits only the task's own reward."""
    task_dir = dataset_dir / task_id
    verifier_dir = task_dir / "tests"
    verifier_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(f'[task]\nname = "local/{task_id}"\n', encoding="utf-8")
    (verifier_dir / "test.sh").write_text("#!/bin/sh\npython3 /tests/evaluate.py\n", encoding="utf-8")
    return Task(id=task_id, uri=task_dir.as_uri())


def _add_metric(dataset_dir: Path, task_id: str) -> None:
    """Augment one task's verifier the way metric authoring is supposed to."""
    verifier_dir = dataset_dir / task_id / "tests"
    (verifier_dir / "check_escalation_restraint.py").write_text("print('escalation_restraint=1.0')\n", encoding="utf-8")
    (verifier_dir / "test.sh").write_text(
        "#!/bin/sh\npython3 /tests/evaluate.py\npython3 /tests/check_escalation_restraint.py\n",
        encoding="utf-8",
    )


def test_a_task_authoring_skipped_is_named_rather_than_silently_unscored(tmp_path: Path) -> None:
    # The failure this prevents: authoring augments most tasks and misses one, every
    # structural check still passes because a skipped task is a perfectly valid task, and
    # nobody finds out until that task evaluates without the shared metric key. When the
    # skipped task is the only one in an Insight half, the half scores nothing at all.
    insight_dir = tmp_path / "insight"
    train_dir = tmp_path / "train"
    insight_tasks = [_authored_task(insight_dir, "001-alpha"), _authored_task(insight_dir, "002-beta")]
    train_tasks = [_authored_task(train_dir, "train-1")]
    splits = (
        ("insight", Dataset(id="insight-suite", tasks=insight_tasks)),
        ("train", Dataset(id="train", tasks=train_tasks)),
    )
    before = {split: eval_author_module.verifier_hashes(dataset.list_tasks()) for split, dataset in splits}

    _add_metric(insight_dir, "001-alpha")
    _add_metric(train_dir, "train-1")

    with pytest.raises(eval_author_module.EvalAuthorUnauthoredTasksError) as exc_info:
        eval_author_module._assert_every_task_authored(splits, before)

    assert [entry.split for entry in exc_info.value.unauthored] == ["insight"]
    assert exc_info.value.unauthored[0].task_ids == ("002-beta",)
    # The message becomes the repair prompt, so it has to name the split and the task.
    assert "insight dataset: 002-beta" in str(exc_info.value)
    assert "001-alpha" not in str(exc_info.value)

    _add_metric(insight_dir, "002-beta")
    eval_author_module._assert_every_task_authored(splits, before)


def test_unauthored_task_check_is_a_dataset_validation_error_so_repair_retries_it() -> None:
    # The repair loop catches DatasetValidationError. Raising anything else would turn a
    # recoverable authoring miss into a hard run failure with no repair attempt.
    assert issubclass(eval_author_module.EvalAuthorUnauthoredTasksError, DatasetValidationError)


def test_the_check_detects_change_only_so_it_must_not_see_already_authored_splits(tmp_path: Path) -> None:
    # This is a pure change detector: a task that already carries the metric but did not
    # move this pass is still reported. That is correct for the Insight suite, which
    # promote_local rebuilds from the task template every run, and wrong for the user's
    # datasets, which dataset_staging._stage leaves in place once staged. Re-running into
    # an existing experiment directory therefore hands back train/validation copies the
    # previous run already authored, which is why run() scopes this to the Insight suite.
    dataset_dir = tmp_path / "already-authored"
    task = _authored_task(dataset_dir, "train-1")
    _add_metric(dataset_dir, "train-1")
    splits = (("train", Dataset(id="train", tasks=[task])),)
    baseline = {"train": eval_author_module.verifier_hashes([task])}

    with pytest.raises(eval_author_module.EvalAuthorUnauthoredTasksError):
        eval_author_module._assert_every_task_authored(splits, baseline)


def test_tasks_with_no_files_on_disk_are_not_accused_of_being_unauthored(tmp_path: Path) -> None:
    # Remote or synthetic tasks hash to nothing. Treating "cannot inspect" as "identical"
    # would fail every run whose datasets this cannot read off local disk.
    splits = (
        (
            "train",
            Dataset(
                id="train",
                tasks=[
                    Task(id="missing", uri=(tmp_path / "absent").as_uri()),
                    Task(id="remote", uri="s3://bucket/task"),
                    Task(id="no-uri"),
                ],
            ),
        ),
    )
    before = {split: eval_author_module.verifier_hashes(dataset.list_tasks()) for split, dataset in splits}

    assert before == {"train": {}}
    eval_author_module._assert_every_task_authored(splits, before)


def test_eval_author_config_defaults_and_bounds_validation_repair_attempts() -> None:
    # Experimentalist's loop config asserts this default too, but from the other side of
    # the plugin boundary; owning it here is what keeps the default a plugin contract.
    assert EvalAuthorConfig().max_validation_repair_attempts == 5
    assert EvalAuthorConfig(max_validation_repair_attempts=10).max_validation_repair_attempts == 10
    with pytest.raises(ValueError, match="less than or equal to 10"):
        EvalAuthorConfig(max_validation_repair_attempts=11)
