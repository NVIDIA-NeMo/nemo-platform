# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical first-level Eval Author agent.

Experimentalist consumes this implementation to curate evaluator datasets
before beginning insight-driven optimization.
"""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nemo_eval_author_plugin.eval_author.materialization import InsightSuite
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_eval_author_plugin.model_config import (
    bridge_author_env_to_experimentalist,
    get_fast_model,
    get_smart_model,
)
from nemo_experimentalist_plugin.entities import Dataset, DatasetValidationError, ResourceRef, Task, TrialResult
from nemo_experimentalist_plugin.experimentalist.components import cache
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
from nemo_experimentalist_plugin.experimentalist.reporting import RunReporter
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform
from nooa import Agent, CodeActStrategy, strategy
from nooa.agentdoc import doc
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from nooa.tools import TodoManager

logger = logging.getLogger(__name__)


class EvalAuthorUnauthoredTasksError(DatasetValidationError):
    """Metric authoring left at least one task in the Insight suite untouched.

    Subclasses ``DatasetValidationError`` so the caller's repair loop treats a skipped
    task the same as a malformed one and feeds this message back as validation feedback.
    """

    def __init__(self, paths: Sequence[str]) -> None:
        """Name the tasks whose verifiers never changed, and what to do about it."""
        self.paths = tuple(paths)
        listed = "\n".join(f"  - {path}" for path in self.paths)
        super().__init__(
            f"Metric authoring left {len(self.paths)} of the Insight suite's verifiers byte-identical, "
            f"so those tasks carry no Insight metric:\n{listed}\n"
            "Every task in the suite needs the same Insight metric key set. Add it to each task listed above."
        )


def _assert_every_task_authored(suite: InsightSuite, before: dict[str, str]) -> None:
    """Fail when a task's verifier is unchanged since before metric authoring.

    A static comparison, so a skipped task costs seconds here instead of surfacing as an
    aggregation error after a full evaluation has already run. ``before`` stays pinned to
    the pre-authoring snapshot across repair attempts: the question is whether a task was
    ever authored, not whether it changed on the most recent attempt.
    """
    after = suite.verifier_hashes()
    unauthored = sorted(path for path, digest in after.items() if before.get(path) == digest)
    if unauthored:
        raise EvalAuthorUnauthoredTasksError(unauthored)


class EvalAuthor(Agent):
    """Insights are failure modes of an agent in production.

    The role of the Eval Author is to create or augment the evaluation suite in such a way that it can be used to detect the failure mode.
    This suite will be used for optimization and regression testing.
    """

    def __init__(
        self,
        experiment_dir: Path,
        config: EvalAuthorConfig | None = None,
        reporter: RunReporter | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Eval Author for the given experiment directory.

        Args:
            experiment_dir: Absolute path to the experiment root.
            config: Tuning parameters; defaults to ``EvalAuthorConfig()``.
            reporter: Optional parent run narrator (Experimentalist insight mode).
                When set, emits mid-run progress lines; never owns header/footer.
            **kwargs: Forwarded to ``Agent.__init__``.
        """
        # Eval Author still reuses a few Experimentalist agents (TraceAnalyzer,
        # TraceExplorer). They read NEMO_EXPERIMENTALIST_* when constructed, so bridge the
        # AUTHOR_* credentials before any of them is built.
        bridge_author_env_to_experimentalist()
        super().__init__(llm=kwargs.pop("llm", None) or get_smart_model(), **kwargs)
        self._config = config or EvalAuthorConfig()
        self._reporter = reporter
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
        runner_conventions: str,
        validation_feedback: str | None = None,
    ) -> str:
        """Author verifier metrics for the materialized tasks that capture the insight.

        Args:
            insight: The insight whose failure mode the tasks should detect.
            diagnostics: Per-trace ``(trace_ref, Diagnostic)`` pairs for concrete evidence.
            insight_suite: The materialized tasks recreated from the Insight's production traces.
            runner_conventions: Summary of how this dataset's runner works (from ``discover_runner``).
                Use this as the authoritative reference for what artifacts exist at
                evaluation runtime, how tasks are structured, and how to add metrics.
            validation_feedback: Actionable failures from mandatory validation of
                the previous metric-authoring attempt. If provided, repair every reported
                file before returning.

        Refer to ``self.context["dataset_documentation"]`` for the dataset-specific API
        and metric authoring conventions (file layout, how to add/remove/modify a metric).

        **Scope: new grades on the materialized Insight tasks**

        Add at least one new Insight-specific metric key to every task in ``insight_suite``.
        Use the same new metric key set and shared scoring semantics across the entire
        suite. Preserve every existing verifier metric, including the task's ordinary
        ``reward`` or ``score``; append the Insight signal instead of replacing the
        task's original notion of success.

        Only edit verifier files in the materialized Insight suite. Do not modify the
        user's train or validation datasets, and do not change task instructions,
        environments, solutions, or other agent-visible inputs. This work adds new
        grades to the new rows; it does not add new agent output to old benchmark rows.

        Name each new metric after the root-cause behavior, not a trace id or surface
        symptom. Measure the current Harbor run from runtime artifacts such as OTLP
        traces or agent outputs. Do not hard-code scores for the production traces that
        motivated the Insight.

        **Validate while authoring**

        After every verifier edit, call ``await insight_suite.validate()``. This performs
        evaluator-specific static checks without launching trials or executing verifier
        code. If it raises ``DatasetValidationError``, use its task, path, and source
        location diagnostics to repair the files, then call it again. Do not return until
        the suite passes validation. If ``validation_feedback`` is provided, the caller's
        mandatory validation found errors in the previous attempt; fix every reported
        failure and revalidate the suite.

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

        **Never score a trial you could not measure**

        ``0.0`` means the agent definitively exhibited the bad behavior, so it must never
        double as "the check could not run".  When the runtime artifact is missing or
        unparseable, a judge call raises, or a judge response will not parse, let the
        exception propagate and exit non-zero without writing the metric file.  The harness
        then marks the trial failed, excludes it from aggregation, and surfaces the error.

        An ``except Exception: score = 0.0`` fallback is forbidden.  It reports maximum
        failure on every trial, which no downstream consumer can tell apart from a real
        regression: the metric looks healthy, sits at a constant, and gives an optimizer
        nothing to climb.  Equally, never write a partial metric file and never drop the
        metric key while still exiting zero — completed trials that disagree on metric keys
        abort aggregation outright.

        Return a concise summary naming the new metric key(s), what they measure, and
        which runtime evidence they score. The caller retains the materialized suite and
        the user's unchanged train and validation datasets.
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
        reporter = self._reporter
        if reporter is not None:
            reporter.progress(phase="eval author · starting")

        resolved_agent = self.experiment_dir / agent_path
        insight_id = insight.id
        if not insight_id:
            raise ValueError("Eval Author requires a persisted Insight with a durable id")
        refs = insight.trace_refs[: self._config.max_traces]

        if not refs:
            if reporter is not None:
                reporter.note("no trace refs — nothing to analyze")
                reporter.progress(phase="eval author · complete")
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
            total_tasks = len(staged_tasks)
            if reporter is not None:
                reporter.progress(
                    phase="eval author · materializing tasks",
                    completed=0,
                    total=total_tasks,
                    unit="task",
                )
            for completed, staged in enumerate(staged_tasks, start=1):
                await self.fill_task_template(staged.trace_ref, staged.task, client, insight.workspace)
                insight_suite.validate(staged)
                if reporter is not None:
                    reporter.progress(
                        phase="eval author · materializing tasks",
                        completed=completed,
                        total=total_tasks,
                        unit="task",
                    )
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
        if reporter is not None:
            reporter.progress(
                phase="eval author · analyzing traces",
                completed=0,
                total=len(trials),
                unit="trace",
            )
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
                if reporter is not None:
                    reporter.note(f"trace analysis failed for {ref}: {result}")
                analysis_statuses[task.id] = ("failed", str(result))
                continue
            cache.store(self.experiment_dir, cache.task_hash(f"eval_author:{ref}"), result)
            diagnostics.append((ref, result))
            analysis_statuses[task.id] = ("completed", None)
        insight_suite.record_analysis(analysis_statuses)
        if reporter is not None:
            reporter.progress(
                phase="eval author · analyzing traces",
                completed=len(diagnostics),
                total=len(trials),
                unit="trace",
            )

        self.context["dataset_documentation"] = doc(type(materialized_dataset), inline_depth=1)
        if reporter is not None:
            reporter.progress(phase="eval author · discovering runner")
        runner_conventions = await self.discover_runner(materialized_dataset)
        if reporter is not None:
            reporter.progress(phase="eval author · authoring metrics")
        verifiers_before_authoring = insight_suite.verifier_hashes()
        summary = await self.author_insight_metrics(
            insight,
            diagnostics,
            materialized_dataset,
            runner_conventions,
        )
        for repair_attempt in range(self._config.max_validation_repair_attempts + 1):
            try:
                _assert_every_task_authored(insight_suite, verifiers_before_authoring)
                await materialized_dataset.validate()
            except DatasetValidationError as exc:
                if repair_attempt >= self._config.max_validation_repair_attempts:
                    raise
                logger.warning(
                    "Eval Author Insight metric validation failed; requesting repair attempt %d/%d: %s",
                    repair_attempt + 1,
                    self._config.max_validation_repair_attempts,
                    exc,
                )
                if reporter is not None:
                    reporter.progress(
                        phase="eval author · repairing metrics",
                        completed=repair_attempt + 1,
                        total=self._config.max_validation_repair_attempts,
                        unit="attempt",
                    )
                summary = await self.author_insight_metrics(
                    insight,
                    diagnostics,
                    materialized_dataset,
                    runner_conventions,
                    validation_feedback=str(exc),
                )
            else:
                finalized_suite = insight_suite.finalize()
                if reporter is not None:
                    reporter.progress(phase="eval author · complete")
                return EvalAuthorResult(
                    train_dataset=train_dataset,
                    validation_dataset=validation_dataset,
                    insight_suite=finalized_suite.dataset,
                    insight_suite_identity=finalized_suite.identity,
                    summary=summary,
                )

        raise AssertionError("unreachable")


def build_eval_author_agent(
    experiment_dir: Path,
    config: EvalAuthorConfig | None = None,
    reporter: RunReporter | None = None,
) -> EvalAuthor:
    """Build and return a configured top-level Eval Author agent."""
    return EvalAuthor(experiment_dir=experiment_dir, config=config, reporter=reporter)
