# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import ast  # noqa: F401
import asyncio  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
import re  # noqa: F401
from collections import Counter, defaultdict  # noqa: F401
from pathlib import Path
from typing import Any, Literal, Sequence

from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    EvaluationResult,
    Task,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DependencyRuntimeError
from nemo_platform import AsyncNeMoPlatform
from nooa import Agent, CodeActStrategy, strategy
from nooa.agentdoc import doc, spec
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from nooa.skill_registry import SkillRegistry
from nooa.tools import Match, TodoManager
from pydantic import BaseModel, Field

from . import cache
from .model_config import get_fast_model, get_smart_model
from .rationalizer import Rationale, Rationalizer, RationalizerConfig  # noqa: F401
from .tools import GuardedShellTools
from .trace_analyzer import Diagnostic, TraceAnalyzer, TraceAnalyzerConfig  # noqa: F401
from .trace_explorer import TraceExplorer  # noqa: F401
from .util import load_framework_skills


class AnalyzerConfig(BaseModel):
    """Configure tuning parameters for AgentAnalyzer."""

    max_summary_tokens: int = Field(
        default=80_000,
        description="Max tokens the token-budget summarizer may use.",
    )
    max_trials: int = Field(
        default=5,
        description="Max number of failing trials to analyze in depth per agent per round.",
    )
    max_divergent_pairs: int = Field(
        default=3,
        description="Max peer divergence pairs to narrate in the comparison report.",
    )
    rationalizer: RationalizerConfig = Field(
        default_factory=RationalizerConfig,
        description="Config forwarded to each Rationalizer instance spawned during analysis.",
    )
    trace_analyzer: TraceAnalyzerConfig = Field(
        default_factory=TraceAnalyzerConfig,
        description="Config forwarded to each TraceAnalyzer instance spawned during analysis.",
    )


class SystematicFailure(BaseModel):
    """Represent a failure pattern that recurs across multiple tasks with the same root cause."""

    root_cause: str
    affected_tasks: list[str]
    pattern: str


class MechanicalError(BaseModel):
    """Represent an infrastructure or tooling failure not attributable to agent logic."""

    task_id: str
    issue_type: Literal["environment", "infrastructure", "evaluation", "tool"]
    description: str


class FailureClassification(BaseModel):
    """Group failures into systematic patterns and one-off mechanical errors."""

    systematic: list[SystematicFailure]
    mechanical: list[MechanicalError]

    def __repr__(self) -> str:
        """Return markdown-formatted string representation.

        Returns:
            str: Markdown representation of failure classification.

        """
        lines = ["## Failure Classification"]
        lines.append("\n### Systematic Failures")
        for f in self.systematic:
            lines.append(f"- **{f.root_cause}** (tasks: {', '.join(f.affected_tasks)})")
            lines.append(f"  {f.pattern}")
        if not self.systematic:
            lines.append("None identified.")
        lines.append("\n### Mechanical Errors")
        for e in self.mechanical:
            lines.append(f"- [{e.issue_type}] {e.task_id}: {e.description}")
        if not self.mechanical:
            lines.append("None identified.")
        return "\n".join(lines)


class DivergentTrial(BaseModel):
    """Represent a task where one agent outperformed another with divergence analysis."""

    task_id: str
    winner: str
    loser: str
    divergence_point: str
    winner_insight: str
    loser_blind_spot: str
    transferable_lesson: str

    def __repr__(self) -> str:
        """Return markdown-formatted string representation.

        Returns:
            str: Markdown representation of divergent trial.

        """
        return (
            f"#### {self.task_id} — winner: {self.winner}, loser: {self.loser}\n"
            f"Divergence: {self.divergence_point}\n"
            f"Winner insight: {self.winner_insight}\n"
            f"Loser blind spot: {self.loser_blind_spot}\n"
            f"Lesson: {self.transferable_lesson}"
        )


class ComplementaryPattern(BaseModel):
    """Represent a task set where different agents have complementary pass/fail patterns."""

    agents: list[str]
    description: str


class PeerComparison(BaseModel):
    """Represent comparison results between an agent and its peers, including divergences."""

    divergent_trials: list[DivergentTrial]
    complementary_patterns: list[ComplementaryPattern]

    def __repr__(self) -> str:
        """Return markdown-formatted string representation.

        Returns:
            str: Markdown representation of peer comparison.

        """
        lines = ["## Peer Comparison"]
        lines.append("\n### Divergent Trials")
        for t in self.divergent_trials:
            lines.append(repr(t))
        if not self.divergent_trials:
            lines.append("None found.")
        lines.append("\n### Complementary Patterns")
        for p in self.complementary_patterns:
            lines.append(f"- {', '.join(p.agents)}: {p.description}")
        if not self.complementary_patterns:
            lines.append("None identified.")
        return "\n\n".join(lines)


class TrialAnalysis(BaseModel):
    """Represent a single trial's trace analysis result paired with its metrics."""

    task_id: str
    trial_id: str
    metrics: dict[str, float]
    diagnostic: Diagnostic

    def __repr__(self) -> str:
        """Return markdown-formatted string representation.

        Returns:
            str: Markdown representation of trial analysis.

        """
        metrics = ", ".join(f"{name}: {value:.3f}" for name, value in self.metrics.items()) or "no metrics"
        lines = [f"### {self.task_id} / {self.trial_id} ({metrics})"]
        lines.append(f"Outcome: {self.diagnostic.outcome}")
        lines.append(f"Summary: {self.diagnostic.summary}")
        if self.diagnostic.failure_point is not None:
            lines.append(f"Failure point: span {self.diagnostic.failure_point}")
        lines.append(f"Root cause: {self.diagnostic.root_cause}")
        return "\n".join(lines)


class AgentAnalysis(BaseModel):
    """Represent full analysis output for one agent: trials, failure classes, and peer comparisons."""

    agent_id: str
    aggregate_metrics: dict[str, float]
    trial_analyses: list[TrialAnalysis]
    failure_classification: FailureClassification
    peer_comparison: PeerComparison

    def __repr__(self) -> str:
        """Return markdown-formatted string representation.

        Returns:
            str: Markdown representation of agent analysis.

        """
        metrics = ", ".join(f"{name}: {value:.3f}" for name, value in self.aggregate_metrics.items()) or "no metrics"
        sections = [f"# Agent Analysis: {self.agent_id} ({metrics})"]
        sections.append("## Per-Trial Traces\n" + "\n\n".join(repr(t) for t in self.trial_analyses))
        sections.append(repr(self.failure_classification))
        sections.append(repr(self.peer_comparison))
        return "\n\n".join(sections)


class AgentAnalyzer(Agent, llm=get_smart_model()):
    """Analyze an agent's trace and failure patterns for a single optimization round."""

    def __init__(
        self,
        workspace: Path,
        config: AnalyzerConfig | None = None,
        framework_skills_dirs: list[Path] | None = None,
        **kwargs: Any,
    ):
        """Initialize the analyzer for the given workspace.

        Args:
            workspace: Absolute path to the eval-and-optimize workspace root.
            config: Tuning parameters; defaults to ``AnalyzerConfig()`` if ``None``.
            framework_skills_dirs: Optional list of directories containing framework skills to load.
            **kwargs: Forwarded to ``Agent.__init__``.

        """
        super().__init__(**kwargs)
        self._config = config or AnalyzerConfig()
        self._workspace_path = workspace
        self._framework_skills_dirs: list[Path] = framework_skills_dirs or []
        self.shell = GuardedShellTools(cwd=workspace)
        self.todos = TodoManager()
        self.context["file_match"] = doc(Match)
        self.skills: SkillRegistry = SkillRegistry(self)
        spec(self, "skills", hidden=True)
        load_framework_skills(self.skills, self._framework_skills_dirs)
        TokenBudgetSummarizer.install(
            self,
            llm=get_fast_model(),
            config=TokenBudgetConfig(max_tokens=self._config.max_summary_tokens),
        )

    @strategy(
        CodeActStrategy(config=CodeActConfig(max_iterations=20, cell_timeout=3600.0)),
        llm=get_fast_model(),
    )
    async def select_trials(
        self,
        agent_id: str,
        dataset: Dataset,
        evaluation: EvaluationResult,
    ) -> Sequence[TrialResult]:
        """Pick which trials to analyze in depth. Return their TrialResult objects.

        Args:
            agent_id: The agent to analyze.
            dataset: The dataset to analyze.
            evaluation: The evaluation result to analyze.

        Returns:
            Sequence[TrialResult]: The selected trials.

        ## Step 1: Get task and trial objects

        ```python
        tasks_by_id = {task.id: task for task in dataset.list_tasks()}
        trials = list(evaluation.trials)
        ```

        ## Step 2: Inspect metrics, outputs, resources, and errors

        ```python
        trial_metrics = [trial.metrics for trial in trials]
        trial_outputs = [trial.outputs for trial in trials]
        trial_resources = [trial.resources for trial in trials]
        trial_errors = [trial.error for trial in trials]
        ```

        ## Step 3: Triage — pick up to {self._config.max_trials} trials

        Prefer trials where:
        - status/error indicates the evaluator did not complete cleanly
        - one or more numeric metric values are below the task's expected passing
          value
        - the trace reference is missing or unloadable
        - outputs/resources suggest repeated failures across task ids

        Metric names are evaluator-defined. Do not assume particular metric
        names, result directories, private checks, or split paths.

        ## Step 4: Return TrialResult objects

        ```python
        return selected_trials
        ```
        """
        ...

    @strategy(
        CodeActStrategy(config=CodeActConfig(max_iterations=30, cell_timeout=3600.0)),
        llm=get_fast_model(),
    )
    async def classify_failures(
        self,
        agent_id: str,
        diagnoses: list[Diagnostic],
        trials: Sequence[TrialResult],
    ) -> FailureClassification:
        """Classify diagnoses into systematic vs. one-off and agent vs. mechanical failures.

        **Systematic vs. one-off**: a failure is systematic when ≥2 trials share the same
        root cause. One-offs are worth noting but should not drive hypotheses. Group the
        diagnoses by root_cause similarity and label each group accordingly.

        **Agent logic vs. mechanical errors**: some failures are not the agent's fault —
        infrastructure issues such as missing packages, network errors, evaluator bugs, API
        rate limits, or ambiguous ground truth. Cross-reference each diagnosis against
        `trials`: use `status`, `metrics`, `outputs`, `resources`, `error`, and
        `metadata`. Do not assume result folders, score files, private check
        outputs, or artifact manifests exist. Decide whether the failure is
        an agent logic error (optimizable) or a mechanical error (needs an infra
        fix). Do not penalise the agent for mechanical errors.

        Return a FailureClassification with:
        - `systematic`: list of SystematicFailure (root_cause, affected_tasks, pattern)
        - `mechanical`: list of MechanicalError (task_id, issue_type, description)

        """
        ...

    async def compare_with_peers(
        self,
        agent_id: str,
        evaluation: EvaluationResult,
        diagnoses: list[Diagnostic],
        peer_evaluations: dict[str, EvaluationResult] | None = None,
    ) -> PeerComparison:
        """Compare this agent to peers and return divergent trials and complementary patterns.

        Args:
            agent_id: The agent to compare against its peers.
            evaluation: Evaluation result for the focal agent.
            diagnoses: Per-trial diagnostics for this agent (used by the narration step).
            peer_evaluations: Optional peer evaluation results keyed by agent id.

        Returns:
            PeerComparison: divergent trial narratives and complementary failure patterns.

        """
        if not peer_evaluations:
            return PeerComparison(divergent_trials=[], complementary_patterns=[])

        top_divergent = self._select_divergent_pairs(
            agent_id,
            evaluation,
            peer_evaluations,
            k=self._config.max_divergent_pairs,
        )
        complementary_raw = self._find_complementary_failures(agent_id, evaluation, peer_evaluations)

        return await self._narrate_peer_comparison(agent_id, top_divergent, complementary_raw, diagnoses)

    def _select_divergent_pairs(
        self,
        agent_id: str,
        evaluation: EvaluationResult,
        peer_evaluations: dict[str, EvaluationResult],
        k: int = 3,
    ) -> list[dict[str, Any]]:
        """Pick top-k divergent (peer, task) pairs ordered by absolute score delta.

        Args:
            agent_id: The focal agent to compare against each peer.
            evaluation: Evaluation result for the focal agent.
            peer_evaluations: Peer evaluation results keyed by agent id.
            k: Maximum number of pairs to return.

        Returns:
            list[dict[str, Any]]: up to k dicts each with keys ``task_id``,
            ``winner``, ``loser``, ``winner_metrics``, ``loser_metrics`` (per-metric
            means), ``delta`` (L1 magnitude of the per-metric difference),
            ``breakdown_delta`` (per-metric winner minus loser), ``winner_trace_ref``,
            ``loser_trace_ref`` (``None`` when unavailable).

        """
        pairs: list[dict[str, Any]] = []
        focal_means = self._task_metric_means(evaluation)
        focal_traces = self._task_trace_refs(evaluation)
        for peer, peer_evaluation in peer_evaluations.items():
            peer_means = self._task_metric_means(peer_evaluation)
            peer_traces = self._task_trace_refs(peer_evaluation)
            for task_id in sorted(set(focal_means) & set(peer_means)):
                fm = focal_means[task_id]
                pm = peer_means[task_id]
                focal_delta = {m: fm.get(m, 0.0) - pm.get(m, 0.0) for m in sorted(set(fm) | set(pm))}
                magnitude = sum(abs(v) for v in focal_delta.values())
                if magnitude == 0.0:
                    continue
                wins = sum(1 for v in focal_delta.values() if v > 0)
                losses = sum(1 for v in focal_delta.values() if v < 0)
                focal_is_winner = wins > losses or (wins == losses and sum(focal_delta.values()) >= 0)
                winner = agent_id if focal_is_winner else peer
                loser = peer if focal_is_winner else agent_id
                sign = 1.0 if focal_is_winner else -1.0
                pairs.append(
                    {
                        "task_id": task_id,
                        "winner": winner,
                        "loser": loser,
                        "winner_metrics": fm if focal_is_winner else pm,
                        "loser_metrics": pm if focal_is_winner else fm,
                        "delta": magnitude,
                        "breakdown_delta": {m: sign * d for m, d in focal_delta.items()},
                        "winner_trace_ref": (focal_traces if focal_is_winner else peer_traces).get(task_id),
                        "loser_trace_ref": (peer_traces if focal_is_winner else focal_traces).get(task_id),
                    }
                )
        pairs.sort(key=lambda p: -p["delta"])
        return pairs[:k]

    def _task_trace_refs(self, evaluation: EvaluationResult) -> dict[str, str]:
        """Return the first trace URI per task id."""
        refs: dict[str, str] = {}
        for trial in evaluation.trials:
            if trial.trace is not None and trial.task_id not in refs:
                refs[trial.task_id] = trial.trace.uri
        return refs

    def _task_metric_means(self, evaluation: EvaluationResult) -> dict[str, dict[str, float]]:
        """Return average value per metric name, keyed by task id."""
        per_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for trial in evaluation.trials:
            for metric_name, metric in trial.metrics.items():
                per_task[trial.task_id][metric_name].append(float(metric.value))
        return {
            task_id: {name: sum(values) / len(values) for name, values in metrics.items()}
            for task_id, metrics in per_task.items()
        }

    def _find_complementary_failures(
        self,
        agent_id: str,
        evaluation: EvaluationResult,
        peer_evaluations: dict[str, EvaluationResult],
    ) -> dict[str, dict[str, dict[str, list[str]]]]:
        """Find tasks where agents split on leaders vs. trailers, per metric.

        Leadership is relative and metric-agnostic: on each metric the agents
        holding the best mean value are leaders, the rest are trailers. A task
        is reported only when at least one metric splits the agents.
        """
        all_means = {agent_id: self._task_metric_means(evaluation)}
        all_means.update({peer: self._task_metric_means(pe) for peer, pe in peer_evaluations.items()})

        task_ids: set[str] = set()
        for means in all_means.values():
            task_ids.update(means)

        complementary: dict[str, dict[str, dict[str, list[str]]]] = {}
        for task_id in sorted(task_ids):
            metric_names: set[str] = set()
            for means in all_means.values():
                metric_names.update(means.get(task_id, {}))
            per_metric: dict[str, dict[str, list[str]]] = {}
            for metric in sorted(metric_names):
                values = {
                    agent: means[task_id][metric]
                    for agent, means in all_means.items()
                    if metric in means.get(task_id, {})
                }
                if len(values) < 2 or min(values.values()) == max(values.values()):
                    continue
                best = max(values.values())
                per_metric[metric] = {
                    "leaders": sorted(agent for agent, value in values.items() if value == best),
                    "trailers": sorted(agent for agent, value in values.items() if value < best),
                }
            if per_metric:
                complementary[task_id] = per_metric
        return complementary

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=40, cell_timeout=3600.0)))
    async def _narrate_peer_comparison(
        self,
        agent_id: str,
        top_divergent: list[dict[str, Any]],
        complementary_raw: dict[str, dict[str, dict[str, list[str]]]],
        diagnoses: list[Diagnostic],
    ) -> PeerComparison:
        """Write the DivergentTrial and ComplementaryPattern narratives from pre-computed data.

        ## Inputs

        `top_divergent` is a list of up to 3 dicts, each with:
          - `task_id`, `winner`, `loser`
          - `winner_metrics`, `loser_metrics`: per-metric mean values for each agent
          - `delta`: L1 magnitude of the per-metric difference (ranking signal)
          - `breakdown_delta`: per-metric (winner - loser); positive means the
            winner did better on that dimension
          - `winner_trace_ref`, `loser_trace_ref`: trace URIs if the evaluator emits
            traces, otherwise None

        `complementary_raw` is
        `{task_id: {metric: {"leaders": [agents], "trailers": [agents]}}}`
        — per-metric splits between the best-scoring agents and the rest.

        ## For each divergent pair

        Produce one DivergentTrial:
          - `task_id`, `winner`, `loser` come from the input dict
          - If both `winner_trace_ref` and `loser_trace_ref` are non-None:
            use TraceExplorer on both to find the earliest turn where reasoning
            diverged. The `breakdown_delta` tells you which dimensions matter
            most (e.g., big insight delta → focus on the moment the loser
            stopped going deeper). Fill in `divergence_point`, `winner_insight`,
            `loser_blind_spot`, `transferable_lesson` from what you see.
          - If either trace ref is None: infer divergence from `breakdown_delta`
            and available metric differences.
            Note in the narrative that this is breakdown-inferred (no trace
            comparison was possible).

        Always emit a DivergentTrial — missing traces is the worse signal, not a
        reason to skip the pair.

        ## For complementary patterns

        Group tasks by which agents lead/trail on each metric. Flag:
          - pairs of agents whose trailing sets are disjoint across metrics (high
            ensemble potential)
          - agents that lead on a metric where higher-scoring peers trail
          - unexpected weaknesses (an agent trailing on a metric it usually leads)

        Build ComplementaryPattern entries with `agents` (the agent set involved)
        and `description` (one or two sentences naming the pattern).

        If `complementary_raw` is empty, return an empty `complementary_patterns` list.

        Return a PeerComparison.
        """
        ...

    def _agent_id_and_path(self, agent: Path | str) -> tuple[str, Path]:
        """Return stable agent id and local path for analyzer calls."""
        if isinstance(agent, Path):
            return agent.name, agent
        return agent, self._workspace_path / "eval-and-optimize" / "agents" / agent

    def _tasks_by_id(self, dataset: Dataset) -> dict[str, Task]:
        """Return dataset tasks keyed by id."""
        return {task.id: task for task in dataset.list_tasks()}

    async def run(
        self,
        agent: Path | str,
        dataset: Dataset,
        evaluation: EvaluationResult,
        round: int | None = None,  # noqa: A002
        peer_evaluations: dict[str, EvaluationResult] | None = None,
        client: AsyncNeMoPlatform | None = None,
        nmp_workspace: str | None = None,
        agent_spec: Path | None = None,
    ) -> AgentAnalysis:
        """Run the full analysis pipeline for one agent in one optimization round.

        Args:
            agent: The agent path or stable agent id to analyze.
            dataset: The dataset to analyze.
            evaluation: The evaluation result to analyze.
            round: Current optimization round number, if available.
            peer_evaluations: Optional peer evaluation results keyed by agent id.
            client: NeMo Platform client used to load ``intake://`` trial traces.
                When ``None``, Intake traces cannot be loaded and are skipped.
            nmp_workspace: NeMo Platform (Intake) workspace *name* — the request
                context for ``intake://`` trace lookups. Distinct from the
                constructor's ``workspace: Path`` (the filesystem eval dir).

        Returns:
            AgentAnalysis: per-trial diagnostics, failure classification, and peer
            comparison for the given agent.

        """
        agent_id, agent_path = self._agent_id_and_path(agent)
        round_key = f":round:{round}" if round is not None else ""
        # Fold intake availability into the key: when no client/workspace is
        # supplied, intake:// trial traces are skipped and the analysis is
        # trace-starved. Keying on availability prevents such a degraded result
        # from being replayed on a later run that *can* load those traces.
        intake_key = ":intake:1" if client is not None and nmp_workspace is not None else ":intake:0"
        cache_key = cache.agent_hash(f"{agent_id}:evaluation:{evaluation.id}{round_key}{intake_key}")
        cached = cache.load(self._workspace_path, cache_key, AgentAnalysis)
        if cached is not None:
            return cached

        trials = await self.select_trials(agent_id, dataset, evaluation)
        tasks_by_id = self._tasks_by_id(dataset)

        missing_task_diagnostics: dict[str, Diagnostic] = {}
        trial_tasks: list[tuple[TrialResult, Task]] = []
        for trial in trials:
            task = tasks_by_id.get(trial.task_id)
            if task is None:
                missing_task_diagnostics[trial.id] = Diagnostic(
                    outcome="FAILURE",
                    summary=f"Trial {trial.id} references missing task {trial.task_id!r}.",
                    failure_point=None,
                    root_cause="evaluation_result_references_unknown_task",
                )
                continue
            trial_tasks.append((trial, task))

        unique_tasks = {task.id: task for _, task in trial_tasks}
        rationales_list = await asyncio.gather(
            *[
                Rationalizer(
                    workspace=self._workspace_path,
                    config=self._config.rationalizer,
                    framework_skills_dirs=self._framework_skills_dirs,
                ).run(task, agent_spec=agent_spec)
                for task in unique_tasks.values()
            ],
            return_exceptions=True,
        )
        rationales: dict[str, Rationale] = {}
        for task_id, result in zip(unique_tasks, rationales_list, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, DependencyRuntimeError):
                raise result
            if isinstance(result, BaseException):
                logging.getLogger(__name__).warning(f"Rationalizer failed for {agent_id}/{task_id}: {result}")
                continue
            rationales[task_id] = result

        diagnoses_list = await asyncio.gather(
            *[
                TraceAnalyzer(
                    experiment_dir=self._workspace_path,
                    config=self._config.trace_analyzer,
                    framework_skills_dirs=self._framework_skills_dirs,
                ).run(
                    trial=trial,
                    task=task,
                    agent_path=agent_path,
                    rationale=rationales.get(task.id),
                    client=client,
                    workspace=nmp_workspace,
                )
                for trial, task in trial_tasks
            ],
            return_exceptions=True,
        )
        diagnostics_by_trial_id = dict(missing_task_diagnostics)
        for (trial, _), result in zip(trial_tasks, diagnoses_list, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, DependencyRuntimeError):
                raise result
            if isinstance(result, BaseException):
                logging.getLogger(__name__).warning(
                    "TraceAnalyzer failed for %s/%s: %s",
                    agent_id,
                    trial.task_id,
                    result,
                )
                diagnostics_by_trial_id[trial.id] = Diagnostic(
                    outcome="FAILURE",
                    summary=f"Trace analysis failed: {result}",
                    failure_point=None,
                    root_cause="analysis_error",
                )
                continue
            diagnostics_by_trial_id[trial.id] = result

        trial_analyses = [
            TrialAnalysis(
                task_id=trial.task_id,
                trial_id=trial.id,
                metrics={name: float(metric.value) for name, metric in trial.metrics.items()},
                diagnostic=diagnostics_by_trial_id[trial.id],
            )
            for trial in trials
            if trial.id in diagnostics_by_trial_id
        ]
        diagnoses = [analysis.diagnostic for analysis in trial_analyses]

        classification, comparison = await asyncio.gather(
            self.classify_failures(agent_id, diagnoses, trials),
            self.compare_with_peers(agent_id, evaluation, diagnoses, peer_evaluations),
        )

        analysis_out = AgentAnalysis(
            agent_id=agent_id,
            aggregate_metrics={name: float(value) for name, value in evaluation.aggregate_metrics.items()},
            trial_analyses=trial_analyses,
            failure_classification=classification,
            peer_comparison=comparison,
        )
        cache.store(self._workspace_path, cache_key, analysis_out)
        return analysis_out
