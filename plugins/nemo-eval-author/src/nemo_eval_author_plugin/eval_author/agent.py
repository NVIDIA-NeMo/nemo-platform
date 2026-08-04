# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical first-level Eval Author agent.

Experimentalist consumes this implementation to curate evaluator datasets
before beginning insight-driven optimization.
"""

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Populates EXPERIMENTALIST_* from AUTHOR_*, which the Experimentalist agent imports below
# read when their class bodies execute. Must stay ahead of them; isort keeps it there.
import nemo_eval_author_plugin._env_bridge  # noqa: F401
from nemo_eval_author_plugin.eval_author.materialization import (
    INSIGHT_TRAIN_SPLIT,
    INSIGHT_VALIDATION_SPLIT,
    InsightSuite,
    materialize_insight_split,
    verifier_hashes,
)
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_eval_author_plugin.model_config import get_fast_model, get_smart_model
from nemo_experimentalist_plugin.experimentalist.components import cache
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    DatasetValidationError,
    Task,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import ResourceRef
from nemo_experimentalist_plugin.experimentalist.components.tools import GuardedShellTools
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import (
    Diagnostic,
    TraceAnalyzer,
    TraceAnalyzerConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import (
    SearchResult,
    SessionData,
    SessionSummary,
    TraceExplorer,
    TurnInfo,
)
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform
from nooa import Agent, CodeActStrategy, strategy
from nooa.agentdoc import doc
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from nooa.tools import TodoManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalAuthorDatasetValidationFailure:
    """Validation failure for one Eval Author dataset split."""

    split: str
    error: DatasetValidationError


class EvalAuthorDatasetValidationError(DatasetValidationError):
    """Aggregated validation failures across every dataset the Eval Author authored."""

    def __init__(self, failures: list[EvalAuthorDatasetValidationFailure]) -> None:
        self.failures = tuple(failures)
        details = "\n".join(f"{failure.split} dataset:\n{failure.error}" for failure in failures)
        super().__init__(f"Eval Author dataset validation failed:\n{details}")


@dataclass(frozen=True)
class EvalAuthorUnauthoredTasks:
    """Tasks in one split whose verifier metric authoring never touched."""

    split: str
    task_ids: tuple[str, ...]


class EvalAuthorUnauthoredTasksError(DatasetValidationError):
    """Raised when metric authoring skipped tasks, leaving their verifiers unchanged.

    Subclasses ``DatasetValidationError`` so the caller's repair loop treats a skipped
    task like any other authoring defect and feeds this message back as feedback.
    """

    def __init__(self, unauthored: Sequence[EvalAuthorUnauthoredTasks]) -> None:
        self.unauthored = tuple(unauthored)
        details = "\n".join(f"{entry.split} dataset: {', '.join(entry.task_ids)}" for entry in unauthored)
        super().__init__(
            "Insight metric authoring left these task verifiers byte-identical, so they emit "
            "none of the new metric keys and every downstream comparison against them fails:\n"
            f"{details}\n"
            "Add the same metric key set to each listed task's verifier. Every task in every "
            "dataset must emit the identical key set."
        )


async def _validate_authored_datasets(splits: Sequence[tuple[str, Dataset]]) -> None:
    """Validate every authored split, reporting which splits failed rather than only the first."""
    failures: list[EvalAuthorDatasetValidationFailure] = []
    for split, dataset in splits:
        try:
            await dataset.validate()
        except DatasetValidationError as exc:
            failures.append(EvalAuthorDatasetValidationFailure(split=split, error=exc))

    if failures:
        raise EvalAuthorDatasetValidationError(failures) from failures[0].error


def _assert_every_task_authored(
    splits: Sequence[tuple[str, Dataset]],
    baseline: Mapping[str, Mapping[str, str]],
) -> None:
    """Fail when authoring left any task's verifier identical to its pre-authoring state.

    ``dataset.validate()`` only checks that each task is structurally sound, and a task
    nobody touched always is. Comparing verifier hashes is what distinguishes "authored"
    from "skipped", and it needs no knowledge of the metric's name.

    Without this the shared metric contract is enforced for the first time by
    ``validate_insight_evaluation_result`` at baseline, one full evaluation later: a
    skipped task costs a round of trials before anyone learns it was skipped, and a
    skipped task in a single-task Insight half fails the run outright.

    Only pass splits whose tasks are rebuilt from source on every run. Re-running into an
    existing experiment directory reuses already-staged copies of the user's datasets, so
    their verifiers legitimately start out authored and an unchanged hash proves nothing.
    """
    unauthored: list[EvalAuthorUnauthoredTasks] = []
    for split, dataset in splits:
        before = baseline.get(split, {})
        unchanged = tuple(
            task_id
            for task_id, digest in verifier_hashes(dataset.list_tasks()).items()
            if before.get(task_id) == digest
        )
        if unchanged:
            unauthored.append(EvalAuthorUnauthoredTasks(split=split, task_ids=unchanged))

    if unauthored:
        raise EvalAuthorUnauthoredTasksError(unauthored)


class EvalAuthor(Agent, llm=get_smart_model()):
    """Insights are failure modes of an agent in production.

    The role of the Eval Author is to create or augment the evaluation suite in such a way that it can be used to detect the failure mode.
    This suite will be used for optimization and regression testing.
    """

    def __init__(self, experiment_dir: Path, config: EvalAuthorConfig | None = None, **kwargs: Any) -> None:
        """Initialize the Eval Author for the given experiment directory.

        Args:
            experiment_dir: Absolute path to the experiment root.
            config: Tuning parameters; defaults to ``EvalAuthorConfig()``.
            **kwargs: Forwarded to ``Agent.__init__``.
        """
        super().__init__(**kwargs)
        self._config = config or EvalAuthorConfig()
        self.experiment_dir = experiment_dir
        self.shell = GuardedShellTools(cwd=experiment_dir)
        self.todos = TodoManager()
        self.context["trace_documentation"] = doc(
            TraceExplorer,
            SessionSummary,
            TurnInfo,
            SessionData,
            SearchResult,
            inline_depth=2,
        )
        TokenBudgetSummarizer.install(
            self,
            llm=get_fast_model(),
            config=TokenBudgetConfig(max_tokens=self._config.max_summary_tokens),
        )

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=15, cell_timeout=60.0)))
    async def discover_runner(self, dataset: Dataset) -> str:
        """Discover how this dataset's evaluation runner works.

        ``self.context["dataset_documentation"]`` contains the full API reference
        for this dataset type — read it first.

        Then read a few task directories from the dataset (resolve ``task.uri``
        from ``dataset.list_tasks()`` to get the on-disk path) and inspect
        the actual files.

        Return a concise summary of the conventions observed (file layout,
        how to write add metrics).
        """  # noqa: D413
        ...

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=60, cell_timeout=3600.0)))
    async def author_insight_metrics(
        self,
        insight: Insight,
        diagnostics: list[tuple[str, Diagnostic]],
        insight_suite: Dataset,
        train_dataset: Dataset,
        validation_dataset: Dataset,
        runner_conventions: str,
        validation_feedback: str | None = None,
    ) -> str:
        """Author verifier metrics that capture the insight across every evaluated dataset.

        Args:
            insight: The insight whose failure mode the tasks should detect.
            diagnostics: Per-trace ``(trace_ref, Diagnostic)`` pairs for concrete evidence.
            insight_suite: The materialized tasks recreated from the Insight's production traces.
            train_dataset: The user's train dataset, augmented with the same metric keys.
            validation_dataset: The user's validation dataset, augmented with the same metric keys.
            runner_conventions: Summary of how this dataset's runner works (from ``discover_runner``).
                Use this as the authoritative reference for what artifacts exist at
                evaluation runtime, how tasks are structured, and how to add metrics.
            validation_feedback: Actionable failures from mandatory validation of
                the previous metric-authoring attempt. If provided, repair every reported
                file before returning.

        Refer to ``self.context["dataset_documentation"]`` for the dataset-specific API
        and metric authoring conventions (file layout, how to add/remove/modify a metric).

        **Scope: every task in all three datasets**

        Add at least one new Insight-specific metric key to every task in ``insight_suite``,
        ``train_dataset``, and ``validation_dataset``. A metric is only useful as a
        suite-wide signal, not a per-sample patch. Preserve every existing verifier
        metric, including the task's ordinary ``reward`` or ``score``; append the Insight
        signal instead of replacing the task's original notion of success.

        **The metric key set must be identical across all three datasets.** Every task
        everywhere emits exactly the same new key names with the same scoring semantics.
        This is a hard requirement, not a preference: the scores are compared against each
        other downstream, and a key present in one dataset but missing from another fails
        the run.

        Only add grades. Do not change task instructions, environments, solutions, or any
        other agent-visible input in any of the three datasets. Adding a verifier metric is
        additive; changing an instruction changes what the benchmark asks.

        Name each new metric after the root-cause behavior, not a trace id or surface
        symptom. Measure the current Harbor run from runtime artifacts such as OTLP
        traces or agent outputs. Do not hard-code scores for the production traces that
        motivated the Insight.

        **Validate while authoring**

        After every verifier edit, call ``await insight_suite.validate()``,
        ``await train_dataset.validate()``, and ``await validation_dataset.validate()``.
        These perform evaluator-specific static checks without launching trials or
        executing verifier code. If any raises ``DatasetValidationError``, use its task,
        path, and source location diagnostics to repair the files, then call it again. Do
        not return until all three pass validation. If ``validation_feedback`` is provided,
        the caller's mandatory validation found errors in the previous attempt; it names
        which dataset failed. Fix every reported failure and revalidate all three.

        **Metric quality**

        Focus the metric on the root cause, not the surface symptom.  Prefer graded
        partial scores over binary 0/1 whenever the evidence supports measuring severity,
        frequency, or progress toward the desired behavior.  Use binary scores only when
        the behavior is genuinely all-or-nothing.  For LLM judges: instruct the judge to
        return calibrated partial-credit floats with a short rationale, not pass/fail.

        **Metric scale — higher is always better, never use raw counts**

        Every metric value must be a float in ``[0.0, 1.0]`` where ``1.0`` means perfect
        and ``0.0`` means complete failure.  Raw counts (error_count, call_count, …) are
        forbidden as metric values — they have no upper bound and make optimization
        direction ambiguous.  Convert counts to rates or invert them:

        - Error rate → ``max(0.0, 1.0 - errors / total_calls)``
        - Presence of a behavior → ``1.0`` if present, ``0.0`` if absent
        - Partial credit → fraction of required steps completed correctly

        Example: the symptom is that the agent fails to return X when a customer asks for Y.
        The root cause is that the agent does not retrieve the full set of relevant database
        objects for Y, so X is missing from its context.  Measure whether the agent retrieves
        all required objects, not merely whether X appears in the final answer.

        Return a concise summary naming the new metric key(s), what they measure, and
        which runtime evidence they score. The caller retains all three datasets.
        """  # noqa: D413
        ...

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=20, cell_timeout=60.0)))
    async def fill_task_template(
        self,
        trace_ref: str,
        task_template: Task,
        client: AsyncNeMoPlatform,
        workspace: str,
    ) -> Task:
        """Fill a pre-staged task template with values from a production trace.

        Steps:
        1. Read the staged task directory at ``task_template.uri`` (file:// URI).
           The caller has already copied the template to its durable candidate path;
           edit this directory in place and do not copy or rename it.
        2. Fetch the trace via ``client`` and populate the template's placeholders
           with values from the trace (instruction, environment config, etc.).
           Leave unfillable placeholders as-is.
        3. Keep ``task.toml`` parseable and keep ``[task] name`` in ``org/name``
           format. The caller will deterministically finalize the name and provenance.
        4. Return a Task whose ``uri`` still points at the staged directory.

        Args:
            trace_ref: Production trace identifier.
            task_template: Pre-staged task copy; resolve its directory from ``task_template.uri``.
            client: NeMo Platform client for fetching the trace.
            workspace: Workspace the trace belongs to.
        """
        ...

    def _trace_trial(
        self,
        insight: Insight,
        task: Task,
        trace_ref: str,
        index: int,
        insight_id: str,
    ) -> TrialResult:
        """Return TrialResult wrapper for an insight production trace."""
        return TrialResult(
            id=f"insight-trace-{index}",
            task_id=task.id,
            status="completed",
            trace=ResourceRef(uri=f"intake://{trace_ref}", description="Production trace attached to the insight."),
            metadata={
                "source": "insight",
                "trace_ref": trace_ref,
                "insight_id": insight_id,
            },
        )

    async def run(
        self,
        insight: Insight,
        agent_path: Path,
        task_template: Task,
        train_dataset: Dataset,
        validation_dataset: Dataset,
        *,
        client: AsyncNeMoPlatform,
    ) -> EvalAuthorResult:
        """Curate an evaluation suite and always close the owned shell session."""
        try:
            return await self._run(
                insight=insight,
                agent_path=agent_path,
                task_template=task_template,
                train_dataset=train_dataset,
                validation_dataset=validation_dataset,
                client=client,
            )
        finally:
            await self.shell.close()

    async def _run(
        self,
        insight: Insight,
        agent_path: Path,
        task_template: Task,
        train_dataset: Dataset,
        validation_dataset: Dataset,
        *,
        client: AsyncNeMoPlatform,
    ) -> EvalAuthorResult:
        """Curate an evaluation suite from an Insight and its production traces.

        Args:
            insight: The Insight to investigate with relevant traces.
            agent_path: Agent root, relative to ``experiment_dir`` or absolute.
            task_template: Parsed evaluator task containing explicit placeholders.
            train_dataset: The train dataset, returned unchanged.
            validation_dataset: The validation dataset, returned unchanged.
            client: Existing NeMo Platform client used for Intake requests.
        """
        resolved_agent = self.experiment_dir / agent_path
        insight_id = insight.id
        if not insight_id:
            raise ValueError("Eval Author requires a persisted Insight with a durable id")
        refs = insight.trace_refs[: self._config.max_traces]

        if not refs:
            return EvalAuthorResult(
                train_dataset=train_dataset,
                validation_dataset=validation_dataset,
                summary="No trace refs on insight — nothing to analyze.",
            )

        insight_suite = InsightSuite(
            experiment_dir=self.experiment_dir,
            insight_id=insight_id,
            task_template=task_template,
        )
        try:
            staged_tasks = insight_suite.stage(refs)
            for staged in staged_tasks:
                await self.fill_task_template(staged.trace_ref, staged.task, client, insight.workspace)
                insight_suite.validate(staged)
            materialized_dataset = insight_suite.promote_local(refs, staged_tasks)
        except BaseException:
            insight_suite.discard()
            raise
        tasks = list(materialized_dataset.list_tasks())
        trials = [
            self._trace_trial(insight, task, ref, index, insight_id)
            for index, (task, ref) in enumerate(zip(tasks, refs, strict=True), start=1)
        ]
        diagnostics: list[tuple[str, Diagnostic]] = []
        analyzer_config = TraceAnalyzerConfig(max_summary_tokens=self._config.max_summary_tokens)
        analyzers = [TraceAnalyzer(experiment_dir=self.experiment_dir, config=analyzer_config) for _ in trials]
        raw_diagnostics: list[Diagnostic | BaseException] = list(
            await asyncio.gather(
                *[
                    analyzer.run(
                        trial=trial,
                        task=task,
                        agent_path=resolved_agent,
                        insight=insight,
                        client=client,
                        workspace=insight.workspace,
                    )
                    for analyzer, trial, task in zip(analyzers, trials, tasks, strict=True)
                ],
                return_exceptions=True,
            )
        )
        analysis_statuses: dict[str, tuple[str, str | None]] = {}
        for task, ref, result in zip(tasks, refs, raw_diagnostics, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                logger.warning("Trace analysis failed for %s: %s", ref, result)
                analysis_statuses[task.id] = ("failed", str(result))
                continue
            cache.store(self.experiment_dir, cache.task_hash(f"eval_author:{ref}"), result)
            diagnostics.append((ref, result))
            analysis_statuses[task.id] = ("completed", None)
        insight_suite.record_analysis(analysis_statuses)

        self.context["dataset_documentation"] = doc(type(materialized_dataset), inline_depth=1)
        runner_conventions = await self.discover_runner(materialized_dataset)
        authored_splits = (
            ("insight", materialized_dataset),
            ("train", train_dataset),
            ("validation", validation_dataset),
        )
        # Only the Insight suite: promote_local rebuilds it from the task template on every
        # run, so an unchanged verifier there really does mean authoring skipped the task.
        # The user's datasets are staged once and reused, so on a re-run they start out
        # already authored and an unchanged hash would be a false accusation.
        #
        # Snapshot before the first pass and keep it: a repair attempt is still measured
        # against the pre-authoring state, so a task every attempt skips stays flagged.
        insight_verifiers_before_authoring = {"insight": verifier_hashes(materialized_dataset.list_tasks())}
        summary = await self.author_insight_metrics(
            insight,
            diagnostics,
            materialized_dataset,
            train_dataset,
            validation_dataset,
            runner_conventions,
        )
        for repair_attempt in range(self._config.max_validation_repair_attempts + 1):
            try:
                await _validate_authored_datasets(authored_splits)
                _assert_every_task_authored(
                    (("insight", materialized_dataset),),
                    insight_verifiers_before_authoring,
                )
            except DatasetValidationError as exc:
                if repair_attempt >= self._config.max_validation_repair_attempts:
                    raise
                logger.warning(
                    "Eval Author Insight metric validation failed; requesting repair attempt %d/%d: %s",
                    repair_attempt + 1,
                    self._config.max_validation_repair_attempts,
                    exc,
                )
                summary = await self.author_insight_metrics(
                    insight,
                    diagnostics,
                    materialized_dataset,
                    train_dataset,
                    validation_dataset,
                    runner_conventions,
                    validation_feedback=str(exc),
                )
            else:
                # Split after authoring so both halves inherit the same metric keys.
                finalized_suite = insight_suite.finalize()
                dataset_dir = self.experiment_dir / "dataset"
                split = materialize_insight_split(
                    finalized_suite,
                    train_dir=dataset_dir / INSIGHT_TRAIN_SPLIT,
                    validation_dir=dataset_dir / INSIGHT_VALIDATION_SPLIT,
                )
                return EvalAuthorResult(
                    train_dataset=train_dataset,
                    validation_dataset=validation_dataset,
                    insight_train_suite=split.train.dataset if split.train else None,
                    insight_train_suite_identity=split.train.identity if split.train else None,
                    insight_validation_suite=split.validation.dataset if split.validation else None,
                    insight_validation_suite_identity=split.validation.identity if split.validation else None,
                    summary=summary,
                )

        raise AssertionError("unreachable")


def build_eval_author_agent(
    experiment_dir: Path,
    config: EvalAuthorConfig | None = None,
) -> EvalAuthor:
    """Build and return a configured top-level Eval Author agent."""
    return EvalAuthor(experiment_dir=experiment_dir, config=config)
