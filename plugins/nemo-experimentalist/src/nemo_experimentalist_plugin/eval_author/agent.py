# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical first-level Eval Author agent.

Experimentalist consumes this implementation to curate evaluator datasets
before beginning insight-driven optimization.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nemo_experimentalist_plugin.eval_author.materialization import InsightSuite
from nemo_experimentalist_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_experimentalist_plugin.experimentalist.components import cache
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    DatasetValidationError,
    Task,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import ResourceRef
from nemo_experimentalist_plugin.experimentalist.components.model_config import get_fast_model, get_smart_model
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
    """Validation failures from datasets returned by the Eval Author."""

    def __init__(self, failures: list[EvalAuthorDatasetValidationFailure]) -> None:
        self.failures = tuple(failures)
        details = "\n".join(f"{failure.split} dataset:\n{failure.error}" for failure in failures)
        super().__init__(f"Eval Author dataset validation failed:\n{details}")


async def _validate_eval_author_result(result: EvalAuthorResult) -> None:
    """Validate both Eval Author output splits and aggregate authoring failures."""
    failures: list[EvalAuthorDatasetValidationFailure] = []
    for split, dataset in (("train", result.train_dataset), ("validation", result.validation_dataset)):
        try:
            await dataset.validate()
        except DatasetValidationError as exc:
            failures.append(EvalAuthorDatasetValidationFailure(split=split, error=exc))

    if failures:
        first_failure = failures[0]
        raise EvalAuthorDatasetValidationError(failures) from first_failure.error


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
    async def augment_dataset(
        self,
        insight: Insight,
        diagnostics: list[tuple[str, Diagnostic]],
        train_dataset: Dataset,
        validation_dataset: Dataset,
        runner_conventions: str,
        validation_feedback: str | None = None,
    ) -> EvalAuthorResult:
        """Augment existing dataset tasks with evaluation metrics that capture the insight.

        Args:
            insight: The insight whose failure mode the tasks should detect.
            diagnostics: Per-trace ``(trace_ref, Diagnostic)`` pairs for concrete evidence.
            train_dataset: The train dataset to augment for optimization feedback.
            validation_dataset: The validation dataset to augment for scoring.
            runner_conventions: Summary of how this dataset's runner works (from ``discover_runner``).
                Use this as the authoritative reference for what artifacts exist at
                evaluation runtime, how tasks are structured, and how to add metrics.
            validation_feedback: Actionable failures from mandatory validation of
                the previous augmentation attempt. If provided, repair every reported
                file before returning.

        Refer to ``self.context["dataset_documentation"]`` for the dataset-specific API
        and metric authoring conventions (file layout, how to add/remove/modify a metric).

        **Scope: every task in both datasets**

        Add the metric to every task in ``train_dataset`` and ``validation_dataset``.
        A metric is only useful as a suite-wide signal, not a per-sample patch.

        **Validate while authoring**

        After every verifier edit, call ``await train_dataset.validate()`` and
        ``await validation_dataset.validate()``. These validation tools perform
        evaluator-specific static checks without launching trials or executing verifier
        code. If either raises ``DatasetValidationError``, use its task, path, and source
        location diagnostics to repair the files, then call the tools again. Do not return
        until both datasets pass validation. If ``validation_feedback`` is provided, it
        means the previous result failed the mandatory validation performed by the caller;
        fix all reported failures and revalidate both datasets.

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

        Return an ``EvalAuthorResult(train_dataset=..., validation_dataset=..., summary=...)``
        with the same dataset objects and a summary of what was added.
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
            train_dataset: The train dataset to augment.
            validation_dataset: The validation dataset to augment.
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
        insight_suite_ref = await insight_suite.publish_fileset(client, insight.workspace)

        self.context["dataset_documentation"] = doc(type(train_dataset), inline_depth=1)
        runner_conventions = await self.discover_runner(train_dataset)
        result = await self.augment_dataset(
            insight,
            diagnostics,
            train_dataset,
            validation_dataset,
            runner_conventions,
        )
        for repair_attempt in range(self._config.max_validation_repair_attempts + 1):
            try:
                await _validate_eval_author_result(result)
            except DatasetValidationError as exc:
                if repair_attempt >= self._config.max_validation_repair_attempts:
                    raise
                logger.warning(
                    "Eval Author dataset validation failed; requesting repair attempt %d/%d: %s",
                    repair_attempt + 1,
                    self._config.max_validation_repair_attempts,
                    exc,
                )
                result = await self.augment_dataset(
                    insight,
                    diagnostics,
                    result.train_dataset,
                    result.validation_dataset,
                    runner_conventions,
                    validation_feedback=str(exc),
                )
            else:
                return result.model_copy(update={"insight_suite": insight_suite_ref})

        raise AssertionError("unreachable")


def build_eval_author_agent(
    experiment_dir: Path,
    config: EvalAuthorConfig | None = None,
) -> EvalAuthor:
    """Build and return a configured top-level Eval Author agent."""
    return EvalAuthor(experiment_dir=experiment_dir, config=config)
