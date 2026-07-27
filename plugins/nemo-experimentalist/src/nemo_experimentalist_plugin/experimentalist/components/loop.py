# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evolutionary optimization loop — ported from AAD ``optimizer/optimize_agent.py``.

The public entry point is :class:`EvolutionaryOptimizer`.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import random
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal, cast, get_args

from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.eval_author.agent import EvalAuthor
from nemo_experimentalist_plugin.experimentalist.components.analyzer import AgentAnalyzer, AnalyzerConfig
from nemo_experimentalist_plugin.experimentalist.components.coder import Coder, CoderConfig
from nemo_experimentalist_plugin.experimentalist.components.dataset_staging import stage_eval_author_inputs
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    Dataset,
    EvaluationResult,
    Evaluator,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import DatasetFactory, EvaluatorFactory
from nemo_experimentalist_plugin.experimentalist.components.goal_tree import (
    GoalTree,
    GoalTreeConfig,
    GoalTreeGenerator,
    leaf_weights_by_id,
    traverse_tree,
)
from nemo_experimentalist_plugin.experimentalist.components.holdout_utils import (
    ensure_heldout_hidden,
    restore_heldout_splits,
)
from nemo_experimentalist_plugin.experimentalist.components.insight_promotion import (
    select_insight_promotion_suggestions,
    write_insight_promotion_section,
)
from nemo_experimentalist_plugin.experimentalist.components.model_config import (
    get_fast_model,
    get_smart_model,
)
from nemo_experimentalist_plugin.experimentalist.components.models import (
    EvolutionTree,
    OptimizationType,
    pareto_front,
    pareto_sort,
)
from nemo_experimentalist_plugin.experimentalist.components.proposer import Improvement, Proposer, ProposerConfig
from nemo_experimentalist_plugin.experimentalist.components.terminator import Terminator
from nemo_experimentalist_plugin.experimentalist.components.tools import (
    GuardedShellTools,
    WorkspaceTool,
)
from nemo_experimentalist_plugin.experimentalist.components.trace_scorer import (
    GroupLeafScorer,
)
from nemo_experimentalist_plugin.experimentalist.deps import ExperimentalistDeps
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
    ExperimentalistBackend,
)
from nemo_experimentalist_plugin.experimentalist.result import ExperimentalistResult
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig
from nemo_platform import AsyncNeMoPlatform
from nooa import Agent, CodeActStrategy, strategy
from nooa.agentdoc import doc, spec
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from nooa.skill import Skill
from nooa.skill_registry import SkillRegistry
from nooa.tools import Match

from .util import load_framework_skills

logger = logging.getLogger(__name__)


_BASELINE_AGENT_LABEL = "agent-0"

_EXCLUDE_DIRS = {
    "eval-and-optimize",
    "__pycache__",
    ".git",
    ".runtime-cache",
    ".claude",
    ".uv",
    ".venv",
    "artifacts",
    "dataset",
    "scratch",
}
_EXCLUDE_GLOBS = {"*traces*", "*eval-and-optimize_*"}


def _warn_persistence_failure(operation: Literal["archive", "publish"], candidate: str, exc: Exception) -> None:
    """Log best-effort persistence failure context."""
    logger.warning(
        "[PERSISTENCE] %s failed for candidate %s; continuing: %s",
        operation,
        candidate,
        exc,
    )


def _ignore_patterns(directory: str, contents: list[str]) -> set[str]:
    ignored = set()
    for name in contents:
        if name in _EXCLUDE_DIRS:
            ignored.add(name)
        elif any(fnmatch.fnmatch(name, pattern) for pattern in _EXCLUDE_GLOBS):
            ignored.add(name)
    return ignored


def _coerce_optimization_type(optimization_type: str | None) -> OptimizationType | None:
    if optimization_type in get_args(OptimizationType):
        return cast(OptimizationType, optimization_type)
    return None


def _trajectory_detail_from_reward(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        reward_val = value.get("reward", value.get("score", 0.0))
        explanation = value.get("reason") or value.get("explanation") or ""
    else:
        reward_val = getattr(value, "reward", getattr(value, "score", value))
        explanation = getattr(value, "reason", "") or getattr(value, "explanation", "")
    detail: dict[str, Any] = {"reward": float(reward_val)}
    if explanation:
        detail["explanation"] = str(explanation)
    return detail


def _complete_trace_groups(
    traces_by_task: dict[str, dict[str, TrialResult]], agent_ids: list[str]
) -> dict[str, dict[str, TrialResult]]:
    required_agents = set(agent_ids)
    return {
        task_id: by_agent
        for task_id, by_agent in traces_by_task.items()
        if set(by_agent) == required_agents and all(by_agent[aid] for aid in required_agents)
    }


class AnalysisSkill(Skill):
    """Standard format for the per-round analysis file the optimizer writes each round.

    The round analysis merges every agent's per-agent analysis into one markdown file
    (``eval-and-optimize/analysis/round-N.md``). It is the record a human or the next
    round reads to understand what happened: which agents lead on which reward
    dimensions, where they diverge, and which failures are systematic vs mechanical.
    Follow this format exactly and fill every section with real data from the per-agent
    analyses and metadata — no placeholders.

    ---

    ```markdown
    # Round N Analysis

    ## Rewards

    **Show every dimension as its own column** so agents with different strengths are visible
    and easier to reason about for merging. An agent may have lower values on some dimensions
    but higher on others — that's a candidate to merge with a complementary agent.

    Train Reward:
    | Agent | <dim1> | <dim2> | <dim3> | ... | Ancestor | vs. Ancestor |
    | ----- | ------ | ------ | ------ | --- | -------- | ------------ |
    | agent-3 | 0.61 | 0.72 | 0.51 | ... | agent-0 | +0.16 |
    | agent-1 | 0.58 | 0.68 | 0.48 | ... | agent-0 | +0.13 |
    | agent-0 | 0.45 | 0.55 | 0.40 | ... | --- | baseline |

    Validation Reward:
    | Agent | <dim1> | <dim2> | <dim3> | ... | Ancestor | vs. Ancestor |
    | ----- | ------ | ------ | ------ | --- | -------- | ------------ |
    | agent-3 | 0.51 | 0.62 | 0.44 | ... | agent-0 | -0.10 |
    | agent-1 | 0.48 | 0.58 | 0.41 | ... | agent-0 | -0.10 |
    | agent-0 | 0.45 | 0.55 | 0.40 | ... | --- | baseline |

    Insight Suite Reward:
    | Agent | <insight-dim1> | <insight-dim2> | ... | vs. Baseline |
    | ----- | -------------- | -------------- | --- | ------------ |
    | agent-3 | 0.80 | 0.67 | ... | +0.40 |
    | agent-1 | 0.60 | 0.50 | ... | +0.20 |
    | agent-0 | 0.40 | 0.33 | ... | baseline |

    [Columns are the actual reward dimension keys from metadata. Order by any dimension that
    helps comparison — no dimension is privileged. Read Insight Suite Reward from
    `candidate.insight_reward`. Omit that table when `insight_reward` is absent or empty
    for every agent. Keep Insight Suite Reward separate from train and validation rewards:
    it reports performance on scenarios authored for the motivating Insight and is not a
    ranking or Pareto-selection input.]

    ## Trajectory Rewards

    Trajectory rewards measure intermediate step quality (goal-tree subgoal rollup).
    Read from metadata:

    ```python
    candidate = self.workspace.get_metadata(agent_id)
    traj = candidate.validation_trajectory_reward or {}
    # e.g. {"aggregate": 0.74, "parse-cli-input": 0.31, "search-web-sources": 0.78}
    details = candidate.validation_trajectory_reward_details or {}
    # details[node_id][task_id] = {"reward": 0.7, "explanation": "..."}
    ```

    | Agent | <step1> | <step2> | ... | aggregate |
    | ----- | ------- | ------- | --- | --------- |
    | agent-3 | 0.45 | 0.85 | ... | 0.78 |
    | agent-1 | 0.32 | 0.90 | ... | 0.75 |
    | agent-0 | 0.31 | 0.78 | ... | 0.74 |

    [Omit if `validation_trajectory_reward` is absent or empty. Show the `aggregate` key as the overall column
    and each node_id entry as its node column.
    When a trajectory reward explains a selection tradeoff or outcome-reward disagreement,
    quote/paraphrase the relevant `validation_trajectory_reward_details` explanation.]

    ## Divergent Trial Analysis

    For each agent pair with divergent results:

    ### agent-A vs agent-B

    | Task | agent-A | agent-B | Winner's Key Insight |
    |------|---------|---------|----------------------|
    | task-003 | ✓ 1.0 | ✗ 0.0 | Checked container type before classifying |
    | task-007 | ✗ 0.0 | ✓ 1.0 | Verified code reachability not just presence |

    **Divergence Pattern**: agent-A excels at X, agent-B excels at Y.
    **Transferable Insight**: agent-B's reachability check could be added to agent-A.

    ## Complementary Failures

    Agent pairs with complementary strengths (each passes tasks the other fails):

    - **agent-A + agent-B**: 5 complementary tasks (ensemble would score 0.85 vs 0.65/0.70 individual)
    - **agent-C + agent-D**: 2 complementary tasks

    ## Failure Patterns
    For each systematic failure pattern (≥2 tasks), describe:
    - Root cause description (in your own words, as specific as the evidence allows)
    - How many tasks affected (e.g. "5/8 tasks")
    - Concrete example: task name, what agent did, what it should have done
    - Trace evidence: session + turn + direct quote from the trace

    Example:
    - **Agent interprets "net revenue" as "gross revenue"** (4/7 tasks): In task `q3-analysis`,
      turn 3: agent wrote "I'll use total_sales which represents net revenue" — but total_sales
      is pre-discount. Root cause confirmed via trace.search("net revenue") returning 0 matches
      before the wrong computation.
      **agent-2 passes this task** by explicitly checking the column metadata for "net" vs "gross".

    ## Root Causes
    For each root cause, answer these three questions explicitly:
    1. **What** specifically did the agent do wrong? (concrete action or output)
    2. **Why** did it do that? (missing knowledge, wrong assumption, context issue, code bug)
    3. **What would fix it?** (the minimal change that addresses the root cause directly)
    4. **Which agents don't have this root cause?** — and what's different about them

    Do NOT write vague statements like "the agent misunderstood the task" without
    specifying what it misunderstood and why. Do NOT write "improve the prompt" without
    specifying what information is missing and where in the agent's reasoning it would help.

    ## Mechanical/Infrastructure Errors

    Errors that are NOT agent logic problems — fix these on the infrastructure side:

    | Task | Error Type | Issue | Suggested Fix |
    |------|------------|-------|---------------|
    | task-005 | environment | `ModuleNotFoundError: cryptography` | Add to container requirements |
    | task-012 | timeout | Agent hit 5min limit mid-analysis | Increase task timeout to 10min |
    | task-018 | dataset | Ground truth expects format X but instruction says Y | Fix instruction.md |
    | task-023 | api | CVE server returned 503 | Add retry logic to cve-server |
    | task-001 | config | `max_iterations` set to 100 | Increase `max_iterations` to 1000 |

    **Do NOT optimize agents to work around these issues.** Report them for infra fixes.

    Common mechanical error categories:
    - **config**: wrong config parameters, missing config, config limits exceeded
    - **environment**: missing packages, wrong versions, container config
    - **timeout**: legitimate work cut short by time limits
    - **dataset**: incorrect ground truth, ambiguous instructions, missing fixtures
    - **api/service**: external service failures, rate limits, network issues
    - **scorer**: evaluation bug, wrong expected format, edge case not handled

    **What qualifies as a mechanical error:**
    - Crashes or `sys.exit` on recoverable errors (e.g., scraping fails → exit instead of fallback)
    - Wrong output path, missing required fields, schema violations
    - Unhandled exceptions that silently discard valid data
    - Missing error handling where failure is expected (network calls, file I/O)
    - Misconfigured agent, llms, config, etc.

    **What is NOT a mechanical error** (use root cause analysis + improvements instead):
    - Shallow reasoning, poor query strategy, suboptimal architecture
    - The code works but produces low-quality output
    ```

    Fill in every section with real data from the per-agent analyses. No placeholders.
    Return the complete markdown content as a string — the caller writes it to disk.
    """


class EvolutionaryOptimizer(Agent, llm=get_smart_model()):
    """The Experimentalist's deterministic Pareto optimization loop.

    Orchestrates the baseline → [convergence-check → select → train-eval →
    analyze → propose → implement → record → validation-eval] cycle across
    rounds, mirroring the AAD ``EvolutionaryOptimizer``.
    """

    def __init__(
        self,
        working_dir: Path,
        config: EvolutionaryOptimizerConfig | None = None,
        framework_skills_dirs: list[Path] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.working_dir = working_dir.resolve()
        self.config = config or EvolutionaryOptimizerConfig()
        self._config = self.config
        self._workspace_path = self.working_dir
        self._framework_skills_dirs: list[Path] = framework_skills_dirs or []
        self.terminator = Terminator()
        self.shell = GuardedShellTools(cwd=self.working_dir)
        self.workspace = WorkspaceTool(workspace=self.working_dir)
        self.context["file_match"] = doc(Match)
        self.context["workspace_tool_documentation"] = doc(WorkspaceTool)
        self.skills: SkillRegistry = SkillRegistry(self)
        spec(self, "skills", hidden=True)
        load_framework_skills(self.skills, self._framework_skills_dirs)
        self.skills.register("ext.analysis_skill", AnalysisSkill())
        self.skills.activate(["cmd.*", "ext.*"])
        TokenBudgetSummarizer.install(
            self,
            llm=get_fast_model(),
            config=TokenBudgetConfig(max_tokens=self.config.max_summary_tokens),
        )

    @staticmethod
    def _coder_config(config: EvolutionaryOptimizerConfig) -> CoderConfig:
        coder_config = CoderConfig.model_validate(config.coder.model_dump())
        if config.model_catalog_path is None or coder_config.model_catalog_path is not None:
            return coder_config
        return coder_config.model_copy(update={"model_catalog_path": config.model_catalog_path})

    @staticmethod
    def _goal_tree_config(config: EvolutionaryOptimizerConfig) -> GoalTreeConfig:
        return GoalTreeConfig.model_validate(config.goal_config.model_dump())

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, deps: ExperimentalistDeps) -> ExperimentalistResult:
        """Run optimization and always close the owned shell session."""
        try:
            return await self._run(deps)
        finally:
            await self.shell.close()

    async def _run(self, deps: ExperimentalistDeps) -> ExperimentalistResult:
        """Run the Pareto evolutionary optimization loop.

        Args:
            deps: Per-run dependencies (workspace, insight_id, dataset,
                backend, optional config override).

        Returns:
            An :class:`ExperimentalistResult` committed to the entity store
            via ``backend.persist_result()``.
        """
        if deps.backend is None:
            raise ValueError("deps.backend must be set before calling run()")
        backend = deps.backend
        workspace = deps.workspace
        config = deps.config if deps.config is not None else self.config

        # ---- Preflight: fail fast when persistence is enabled but git is missing.
        if (config.storage.archive_candidates or config.storage.publish_winner) and shutil.which("git") is None:
            raise ValueError(
                "Candidate persistence is enabled (storage.archive_candidates/publish_winner) "
                "but 'git' is not on PATH, so nothing can be persisted. Install git, or disable "
                "storage to run without persistence."
            )

        # ---- Working directory structure ---------------------------------
        agents_dir, analysis_dir, results_dir = self._init_structure()
        evaluator_factory = EvaluatorFactory()
        evaluator = evaluator_factory.build_evaluator(
            deps.evaluator_type,
            config.evaluator,
            experiment_dir=self.working_dir,
        )
        dataset_factory = DatasetFactory()

        train_dataset_ref = deps.train_dataset
        validation_dataset_ref = deps.validation_dataset
        task_template_ref = deps.task_template
        insight_eval_dataset: Dataset | None = None
        if deps.insight is not None:
            if task_template_ref is None:
                raise ValueError("Task template is required for insight trace analysis")
            if backend.client is None:
                raise ValueError("Platform client is required for insight task template loading")
            staged_inputs = await stage_eval_author_inputs(
                self.working_dir,
                train_dataset=train_dataset_ref,
                validation_dataset=validation_dataset_ref,
                task_template=task_template_ref,
                client=backend.client,
                workspace=workspace,
            )
            train_dataset_ref = staged_inputs.train_dataset
            validation_dataset_ref = staged_inputs.validation_dataset
            task_template_ref = staged_inputs.task_template

        # ---- Resolve datasets to evaluator-domain objects -----------------
        train_eval_dataset = dataset_factory.build_dataset(
            deps.evaluator_type,
            train_dataset_ref,
        )

        validation_eval_dataset = dataset_factory.build_dataset(
            deps.evaluator_type,
            validation_dataset_ref,
        )

        # ---- Resolve insight (Mode 1) vs local agent (Mode 2) -----------
        insight = (
            await backend.get_insight(workspace=workspace, insight_id=str(deps.insight))
            if deps.insight is not None
            else None
        )
        agent_ref: str | Path | None = deps.agent
        if agent_ref is None and insight is not None:
            agent_ref = insight.agent
        if agent_ref is None:
            raise ValueError("Insight or agent is required")

        agent_path = self.working_dir / "eval-and-optimize" / "source-agent"
        await backend.get_agent_code(
            workspace=workspace,
            agent=agent_ref,
            dest=agent_path,
            clone_depth=config.source.clone_depth,
        )
        agent_name = str(agent_ref)

        agent_spec_path: Path | None = None
        if deps.agent_spec is not None:
            agent_spec_path = await backend.get_agent_spec(
                workspace=workspace,
                spec=deps.agent_spec,
                dest=self.working_dir / "AGENT-SPEC.md",
            )

        if insight is not None:
            insight_ref: str = str(deps.insight)
            # run the eval_author
            if backend.client is None:
                raise ValueError("Platform client is required for insight trace loading")
            assert task_template_ref is not None
            eval_author = EvalAuthor(experiment_dir=self.working_dir, config=config.eval_author)
            eval_author_result = await eval_author.run(
                insight=insight,
                agent_path=agent_path,
                task_template=dataset_factory.build_task_template(deps.evaluator_type, task_template_ref),
                train_dataset=train_eval_dataset,
                validation_dataset=validation_eval_dataset,
                client=backend.client,
            )
            train_eval_dataset = eval_author_result.train_dataset
            validation_eval_dataset = eval_author_result.validation_dataset
            insight_eval_dataset = eval_author_result.insight_suite
        else:
            # Mode 2: local agent directory as baseline, no insight required.
            insight = None
            insight_ref = ""

        # ---- Resume or fresh start ---------------------------------------
        if (round_num := self._detect_last_round()) is not None:
            logger.info(f"[RESUME] round {round_num}")
            self._delete_all_artifacts(from_round=round_num)
            evolution_tree = EvolutionTree.from_dir(agents_dir)
            candidates: list[Candidate] = list(evolution_tree.survivors(round_num))
            run_entity = self._load_run_entity() or await self._create_experiment_run(
                workspace=workspace,
                backend=backend,
                agent_name=agent_name or None,
                agent_path=agent_path,
                insight_ref=insight_ref or None,
                config=config,
            )
        else:
            round_num = 0
            logger.info("phase=baseline round=0")
            run_entity = await self._create_experiment_run(
                workspace=workspace,
                backend=backend,
                agent_name=agent_name or None,
                agent_path=agent_path,
                insight_ref=insight_ref or None,
                config=config,
            )

            try:
                # ---- Fetch + build baseline agent (agent-0) --------------
                baseline = await self._create_baseline_agent(
                    workspace=workspace,
                    backend=backend,
                    agents_dir=agents_dir,
                    agent_name=agent_name,
                    agent_path=agent_path,
                    run_id=run_entity.id or "",
                    config=config,
                )
                await self._update_candidate(
                    baseline,
                    workspace=workspace,
                    backend=backend,
                    run_id=run_entity.id or "",
                )
                evolution_tree = EvolutionTree.from_dir(agents_dir)
                candidates = list(evolution_tree.survivors(0))

                # ---- Baseline validation evaluation (round 0) ------------
                validation_candidate_results = await self._evaluate_validation_candidates(
                    dataset=validation_eval_dataset,
                    evaluator=evaluator,
                    candidates=candidates,
                )
                validation_result = validation_candidate_results[candidates[0].label]
                await backend.persist_evaluation(
                    workspace=workspace,
                    result=validation_result,
                    candidate=candidates[0],
                    split="validation",
                )
                await self._update_candidate(
                    candidates[0],
                    updates={
                        "validation_reward": validation_result.aggregate_metrics,
                        "validation_reward_details": validation_result.trials,
                    },
                    workspace=workspace,
                    backend=backend,
                    run_id=run_entity.id or "",
                )
            except Exception:
                run_entity.status = "failed"
                await backend.update_run(workspace=workspace, run=run_entity)
                raise

        run_id = run_entity.id or ""

        if insight_eval_dataset is not None:
            try:
                await self._evaluate_and_persist_insight_candidates(
                    dataset=insight_eval_dataset,
                    evaluator=evaluator,
                    candidates=candidates,
                    workspace=workspace,
                    backend=backend,
                    run_id=run_entity.id or "",
                )
            except Exception:
                run_entity.status = "failed"
                await backend.update_run(workspace=workspace, run=run_entity)
                raise

        # ---- Initial goal tree (idempotent) ------------------------------
        await self._generate_initial_goal_tree(
            dataset=train_eval_dataset,
            disable_trajectory_scoring=config.disable_trajectory_scoring,
            config=config,
            agent_spec_path=agent_spec_path,
        )

        phase: Literal["exploration", "exploitation"] = "exploration" if round_num % 2 == 0 else "exploitation"

        # ---- Pareto optimization loop (shared by fresh start and resume) --
        try:
            while True:
                prior_analysis = (
                    await self._load_round_analysis(analysis_dir=analysis_dir, round_num=round_num - 1)
                    if round_num > 0
                    else None
                )
                decision = await self.terminator.run(
                    round_num=round_num,
                    evolution_tree=evolution_tree,
                    prior_analysis=prior_analysis,
                    config=config,
                )
                if decision.stop:
                    logger.info(f"phase=terminate reason={decision.reason}")
                    break

                survivors = (
                    await self._select_survivors([c.slim() for c in candidates], k=config.max_survivors)
                    if len(candidates) > 1
                    else list(candidates)
                )
                survivor_labels = {s.label for s in survivors}
                killed = [c for c in candidates if c.label not in survivor_labels]
                for candidate in killed:
                    await self._update_candidate(
                        candidate,
                        workspace=workspace,
                        backend=backend,
                        run_id=run_id,
                        updates={"killed_round": round_num},
                    )

                train_candidate_results = await self._evaluate_train_candidates(
                    dataset=train_eval_dataset,
                    evaluator=evaluator,
                    survivors=survivors,
                    round_num=round_num,
                    max_train_batch_tasks=config.max_train_batch_tasks,
                    train_batch_seed=config.train_batch_seed,
                )
                for survivor in survivors:
                    if survivor.label in train_candidate_results:
                        await backend.persist_evaluation(
                            workspace=workspace,
                            result=train_candidate_results[survivor.label],
                            candidate=survivor,
                            split="train",
                        )
                        await self._update_candidate(
                            survivor,
                            workspace=workspace,
                            backend=backend,
                            run_id=run_id,
                            updates={
                                "train_reward": train_candidate_results[survivor.label].aggregate_metrics,
                                "train_reward_details": train_candidate_results[survivor.label].trials,
                            },
                        )
                analysis = await self._analyze_round(
                    analysis_dir=analysis_dir,
                    dataset=train_eval_dataset,
                    evaluations=train_candidate_results,
                    survivors=[c.slim() for c in survivors],
                    round_num=round_num,
                    config=config,
                    client=backend.client,
                    nmp_workspace=workspace,
                    agent_spec_path=agent_spec_path,
                )
                await self._update_goal_tree(
                    analysis_dir=analysis_dir,
                    round_num=round_num,
                    analysis=analysis,
                    dataset=train_eval_dataset,
                    config=config,
                    agent_spec_path=agent_spec_path,
                )

                improvements = await self._propose_improvements(
                    workspace=workspace,
                    backend=backend,
                    analysis=analysis,
                    evolution_tree=evolution_tree,
                    round_num=round_num,
                    phase=phase,
                    config=config,
                )
                new_candidates = [
                    self._create_agent(
                        agents_dir=agents_dir,
                        improvement=imp,
                        round_num=round_num + 1,
                        run_id=run_entity.id or "",
                    )
                    for imp in improvements
                ]
                # Persist metadata.json before Coder runs so snapshot can read it.
                for candidate in new_candidates:
                    await self._update_candidate(
                        candidate,
                        workspace=workspace,
                        backend=backend,
                        run_id=run_entity.id or "",
                    )
                new_candidates = await self._implement_candidates(
                    workspace=workspace,
                    backend=backend,
                    dataset=train_eval_dataset,
                    evaluator=evaluator,
                    candidates=new_candidates,
                    config=config,
                )
                for candidate in new_candidates:
                    await self._update_candidate(
                        candidate,
                        workspace=workspace,
                        backend=backend,
                        run_id=run_id,
                    )
                if insight_eval_dataset is not None:
                    await self._evaluate_and_persist_insight_candidates(
                        dataset=insight_eval_dataset,
                        evaluator=evaluator,
                        candidates=new_candidates,
                        workspace=workspace,
                        backend=backend,
                        run_id=run_id,
                    )
                for c in new_candidates:
                    evolution_tree.add(c)

                candidates = survivors + new_candidates
                round_num += 1
                phase = "exploration" if round_num % 2 == 0 else "exploitation"

                validation_candidate_results = await self._evaluate_validation_candidates(
                    dataset=validation_eval_dataset,
                    evaluator=evaluator,
                    candidates=candidates,
                )
                for candidate in candidates:
                    if candidate.label in validation_candidate_results:
                        await backend.persist_evaluation(
                            workspace=workspace,
                            result=validation_candidate_results[candidate.label],
                            candidate=candidate,
                            split="validation",
                        )
                        await self._update_candidate(
                            candidate,
                            workspace=workspace,
                            backend=backend,
                            run_id=run_id,
                            updates={
                                "validation_reward": validation_candidate_results[candidate.label].aggregate_metrics,
                                "validation_reward_details": validation_candidate_results[candidate.label].trials,
                            },
                        )
                if not config.disable_trajectory_scoring:
                    trajectory_results = await self._reward_trajectories(
                        workspace=workspace,
                        backend=backend,
                        dataset=validation_eval_dataset,
                        candidates=candidates,
                        config=config,
                        client=backend.client,
                    )
                    for candidate in candidates:
                        if candidate.label in trajectory_results:
                            await self._update_candidate(
                                candidate,
                                workspace=workspace,
                                backend=backend,
                                run_id=run_id,
                                updates={
                                    "validation_trajectory_reward": trajectory_results[candidate.label]["reward"],
                                    "validation_trajectory_reward_details": trajectory_results[candidate.label][
                                        "details"
                                    ],
                                },
                            )

                if config.storage.archive_candidates:
                    for candidate in new_candidates:
                        try:
                            await backend.archive_candidate(workspace=workspace, candidate=candidate)
                        except Exception as exc:  # noqa: BLE001 - archival must never fail the run
                            _warn_persistence_failure("archive", candidate.label, exc)

                run_entity.rounds_completed = round_num
                await backend.update_run(workspace=workspace, run=run_entity)

        except Exception:
            run_entity.status = "failed"
            await backend.update_run(workspace=workspace, run=run_entity)
            raise

        # ---- Finalize ----------------------------------------------------
        winner_entity = await self._finalize(
            workspace=workspace,
            backend=backend,
            agents_dir=agents_dir,
            run_entity=run_entity,
            evolution_tree=evolution_tree,
            agent_name=agent_name,
            insight_dataset=insight_eval_dataset,
        )

        baseline_entity = next(
            (node.candidate for node in evolution_tree.nodes.values() if node.round == 0),
            None,
        )
        result = ExperimentalistResult(
            summary=self._render_summary(
                rounds_completed=round_num,
                baseline=baseline_entity,
                winner=winner_entity,
            ),
            run_id=run_id,
            rounds_completed=round_num,
            winner=winner_entity,
        )

        # Persist the terminal result
        await backend.persist_result(workspace=workspace, result=result)

        # Publish the winner as a draft PR/MR
        if config.storage.publish_winner and winner_entity is not None and winner_entity.round != 0:
            try:
                url = await backend.publish_candidate(workspace=workspace, candidate=winner_entity)
                if url:
                    logger.info(f"[TERMINATOR] opened draft PR/MR for winner {winner_entity.label}: {url}")
            except Exception as exc:  # noqa: BLE001 - publishing must never fail the run
                _warn_persistence_failure("publish", winner_entity.label, exc)
        return result

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=100, cell_timeout=3600.0)))
    async def select_diverse_survivors(self, ranked: list[Candidate], k: int) -> list[Candidate]:  # pyright: ignore[reportReturnType]
        """Choose up to k survivors from Pareto-ranked candidates.

        ``ranked`` is already Pareto-sorted using outcome and trajectory scores:
        front 0 (non-dominated) first, then front 1, etc. Inside a front,
        candidates are incomparable, so prefer agents with distinct architecture
        changes, complementary task coverage, and different trajectory strengths.

        To avoid getting stuck on the same agents round after round:
        1. Always include at least 1 candidate that was newly created this round. Look up
           `self.workspace.get_metadata(c.name)["round"]` for each candidate; new candidates
           are the ones whose round equals the max round across `ranked`.
        2. Prefer candidates with different optimization_type values or that address different root causes.
        3. If all new candidates sit on a worse Pareto front, still include the best new candidate.

        ## MANDATORY: Prefer agents with complementary strengths

        Read each candidate's per-dimension validation rewards from metadata and
        prefer a set whose strong dimensions cover each other (one agent leads on
        dimensions where another trails):

        ```python
        rewards = {c.id: self.workspace.get_metadata(c.name).validation_reward or {} for c in ranked}
        ```

        Between 1 to 3 survivors per round.
        Return the selected subset, preserving the input's Pareto-front order.
        """
        ...

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=100, cell_timeout=3600.0)))
    async def merge_analysis(
        self,
        agent_ids: list[Candidate],
        round: int,
        per_agent_analyses: list[str],  # noqa: A002
    ) -> str:  # pyright: ignore[reportReturnType]
        """Merge per-agent analyses, compare agents, and write the round analysis file.

        ## Step 1: Compare agents at reward level

        Read each agent's per-dimension train rewards from metadata:

        ```python
        rewards = {c.id: self.workspace.get_metadata(c.name).train_reward or {} for c in agent_ids}
        insight_rewards = {
            c.id: self.workspace.get_metadata(c.name).insight_reward or {} for c in agent_ids
        }
        all_candidates = [
            self.workspace.get_metadata(agent_id).slim() for agent_id in self.workspace.list_agents()
        ]
        baseline = next((candidate for candidate in all_candidates if candidate.round == 0), None)
        ```

        - Compare siblings: which optimization strategy worked better this round?
        - Compare to ancestors: did the change actually fix the targeted root cause?
        - When any Insight Suite rewards are present, compare those dimensions to the
          round-zero baseline separately from train and validation rewards.

        ## Step 2: Analyze divergent and complementary patterns

        Using the per-dimension rewards above, identify where agents diverge (one
        leads, another trails on a dimension) and where their strengths are
        complementary. Ground observations in the per-agent analyses passed in.

        ## Step 3: Build the round analysis markdown

        First, discover reward dimensions from metadata:
        ```python
        candidate = self.workspace.get_metadata(agent_ids[0].name).slim()
        train_reward = candidate.train_reward or {}
        dim_keys = sorted(train_reward.keys())
        insight_dim_keys = sorted({key for reward in insight_rewards.values() for key in reward})
        ```

        Follow the `ext.analysis_skill` format exactly for every section (Rewards tables,
        including the conditional Insight Suite Reward table; Trajectory Rewards; Divergent
        Trial Analysis; Complementary Failures; Failure Patterns; Root Causes;
        Mechanical/Infrastructure Errors).

        If at least one agent has a non-empty `insight_reward`, the round analysis must name
        every available Insight Suite dimension and show its values in the separate Insight
        Suite Reward table. Never blend those metrics into train/validation rewards or imply
        that they affected ranking. Fill in every included section with real data. No placeholders.
        Return the complete markdown content as a string.
        """
        ...

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=100, cell_timeout=3600.0)))
    async def write_final_report(self, best_agent_id: str) -> None:  # pyright: ignore[reportReturnType]
        """Write the final optimization report to eval-and-optimize/OPTIMIZATION.md.

        ## MANDATORY: use self.workspace — DO NOT ls / cat / find manually

        ```python
        agent_ids = self.workspace.list_agents()
        candidate = self.workspace.get_metadata(agent_id).slim()
        insight_reward = candidate.insight_reward or {}
        analysis  = self.workspace.read_analysis_file(n)
        ```

        ## Steps
        1. Collect metadata for every agent.
        2. Read round analysis files.
        3. Build the lineage tree by following ancestor chains.
        4. Write eval-and-optimize/OPTIMIZATION.md with format:
           - Summary (baseline vs best rewards, rounds completed, total agents)
           - Reward Breakdown table (one row per agent, per-dimension columns)
           - Insight Suite Metrics table when available
           - Lineage Tree (ASCII tree with rewards and optimization type)
           - Round-by-Round Analysis
           - Optimization Insights

        When both the round-zero baseline and best agent have non-empty `insight_reward`,
        the Summary must state whether the Insight-specific scenarios improved and the
        Insight Suite Metrics table must show every available dimension with baseline,
        winner, and signed delta columns. Keep this table separate from generic train and
        validation rewards. Omit it only when Insight Suite rewards are unavailable.

        Fill in every section with real data. Every agent must appear in the lineage tree.
        Mark the best agent with * BEST.
        """
        ...

    # ------------------------------------------------------------------
    # Private helpers — concrete (no LLM, no evaluator)
    # ------------------------------------------------------------------

    def _init_structure(self) -> tuple[Path, Path, Path]:
        """Create the eval-and-optimize workspace directories; return (agents_dir, analysis_dir, results_dir)."""
        agents_dir = self.working_dir / "eval-and-optimize" / "agents"
        analysis_dir = self.working_dir / "eval-and-optimize" / "analysis"
        results_dir = self.working_dir / "eval-and-optimize" / "results"
        agents_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        return agents_dir, analysis_dir, results_dir

    def _load_run_entity(self) -> ExperimentRun | None:
        """Read run.json from the workspace; return None if absent or unparseable."""
        run_path = self.working_dir / "eval-and-optimize" / "run.json"
        if not run_path.exists():
            return None
        try:
            data = json.loads(run_path.read_text())
            # ExperimentRun._restore_id_from_json validator handles id restoration
            return ExperimentRun.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[RESUME] Could not parse run.json: {exc}")
            return None

    def _detect_last_round(self) -> int | None:
        """Return the last completed round by scanning analysis files, or None if starting fresh."""
        analysis_dir = self.working_dir / "eval-and-optimize" / "analysis"
        if not analysis_dir.exists():
            return None
        rounds = []
        for f in analysis_dir.glob("round-*.md"):
            try:
                rounds.append(int(f.stem.split("-")[1]))
            except (IndexError, ValueError):
                continue
        return max(rounds) if rounds else None

    def _delete_all_artifacts(self, from_round: int) -> None:
        """Delete agents and analysis files created after *from_round*.

        Rolls back any partial work so the loop can cleanly re-enter at
        the start of ``from_round + 1``.  Also clears stale ``killed_round``
        markers on surviving agents whose killer round was itself rolled back.
        """
        agents_dir = self.working_dir / "eval-and-optimize" / "agents"
        results_dir = self.working_dir / "eval-and-optimize" / "results"
        analysis_dir = self.working_dir / "eval-and-optimize" / "analysis"
        smoke_dataset_dir = self.working_dir / "eval-and-optimize" / "smoke-dataset"
        smoke_results_dir = self.working_dir / "eval-and-optimize" / "smoke-results"

        for agent_dir in sorted(agents_dir.iterdir()):
            if not (
                agent_dir.is_dir() and agent_dir.name.startswith("agent-") and agent_dir.name.split("-")[1].isdigit()
            ):
                continue
            meta_path = agent_dir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if (meta.get("round") or 0) > from_round:
                shutil.rmtree(agent_dir)
                for suffix in ("-train", "-validation", "-insight"):
                    rd = results_dir / f"{agent_dir.name}{suffix}"
                    if rd.exists():
                        shutil.rmtree(rd)
                for rd in (
                    smoke_results_dir / agent_dir.name,
                    smoke_dataset_dir / agent_dir.name,
                ):
                    if rd.exists():
                        shutil.rmtree(rd)

        # Clear stale killed_round markers whose killer round was rolled back.
        for agent_dir in sorted(agents_dir.iterdir()):
            if not (
                agent_dir.is_dir() and agent_dir.name.startswith("agent-") and agent_dir.name.split("-")[1].isdigit()
            ):
                continue
            meta_path = agent_dir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            killed = meta.get("killed_round")
            if killed is not None and killed > from_round:
                meta["killed_round"] = None
                meta_path.write_text(json.dumps(meta, indent=2))

        for pattern in ("round-*.md", "round-*-goal.json"):
            for f in analysis_dir.glob(pattern):
                try:
                    n = int(f.stem.split("-")[1])
                except (IndexError, ValueError):
                    continue
                if n > from_round:
                    f.unlink()

    async def _create_baseline_agent(
        self,
        *,
        workspace: str,
        backend: ExperimentalistBackend,
        agents_dir: Path,
        agent_name: str | None,
        agent_path: Path | None,
        run_id: str,
        config: EvolutionaryOptimizerConfig,
    ) -> Candidate:
        """Materialize the source agent into ``agents_dir/agent-0`` and return the baseline candidate.

        An explicit ``--agent`` (``agent_path``, a local dir or a git clone) takes
        precedence and is copied directly; otherwise the code is fetched by the
        insight's agent name via ``backend.get_agent_code``. Skips the copy when the
        directory already exists (resume case).
        """
        baseline_dir = agents_dir / _BASELINE_AGENT_LABEL
        if not baseline_dir.exists():
            if agent_path is not None:
                shutil.copytree(agent_path, baseline_dir, ignore=_ignore_patterns)
            elif agent_name:
                await backend.get_agent_code(workspace=workspace, agent=agent_name, dest=baseline_dir)
        await self._generate_architecture_doc(agent_dir=baseline_dir, config=config)
        candidate = Candidate(
            name=_BASELINE_AGENT_LABEL,
            label=_BASELINE_AGENT_LABEL,
            workspace=workspace,
            run_id=run_id,
            ancestor=None,
            round=0,
            optimization="baseline",
        )
        return candidate

    def _create_agent(
        self,
        *,
        agents_dir: Path,
        improvement: Improvement,
        round_num: int,
        run_id: str,
    ) -> Candidate:
        """Copy the ancestor directory to a new ``agent-N`` directory and return the candidate."""
        next_label = self._next_agent_label(agents_dir)
        ancestor_dir = agents_dir / improvement.ancestor
        candidate_dir = agents_dir / next_label
        generated_files = {
            "architecture.md",
        }

        def _ignore_agent_meta(directory: str, contents: list[str]) -> set[str]:
            ignored = _ignore_patterns(directory, contents)
            if Path(directory).resolve() != ancestor_dir.resolve():
                return ignored
            return ignored | {name for name in contents if name == "metadata.json" or name in generated_files}

        if ancestor_dir.is_dir():
            shutil.copytree(ancestor_dir, candidate_dir, ignore=_ignore_agent_meta)
        else:
            candidate_dir.mkdir(parents=True, exist_ok=True)
        opt_type = _coerce_optimization_type(improvement.optimization_type)
        candidate = Candidate(
            name=next_label,
            label=next_label,
            ancestor=improvement.ancestor,
            round=round_num,
            optimization=improvement.optimization,
            optimization_type=opt_type,
            task_ids=improvement.task_ids,
            run_id=run_id,
        )
        return candidate

    def _next_agent_label(self, agents_dir: Path) -> str:
        """Return the next sequential ``agent-N`` label based on existing directories."""
        nums = [
            int(d.name.split("-")[1])
            for d in agents_dir.iterdir()
            if d.is_dir() and d.name.startswith("agent-") and d.name.split("-")[1].isdigit()
        ]
        return f"agent-{max(nums, default=-1) + 1}"

    async def _load_round_analysis(
        self,
        *,
        analysis_dir: Path,
        round_num: int,
    ) -> str | None:
        """Return the cached analysis markdown for *round_num*, or None if absent."""
        path = analysis_dir / f"round-{round_num}.md"
        return path.read_text() if path.exists() else None

    async def _update_candidate(
        self,
        candidate: Candidate,
        *,
        workspace: str,
        backend: ExperimentalistBackend,
        run_id: str,
        updates: dict[str, Any] | None = None,
    ) -> None:
        """Sync candidates to the entity store.

        Fills in ``workspace`` and ``run_id`` from the call-site context
        (which is authoritative) before persisting.  On first persist the
        backend assigns a store id (``_id``); on subsequent calls it updates
        the existing record.
        """
        candidate.workspace = workspace
        candidate.run_id = run_id
        if updates is not None:
            for key, value in updates.items():
                setattr(candidate, key, value)
        if candidate.id:
            await backend.update_candidate(workspace=workspace, candidate=candidate)
        else:
            result = await backend.create_candidate(workspace=workspace, candidate=candidate)
            candidate._id = result._id  # type: ignore[attr-defined]

    def _goal_tree_path(self, round_num: int) -> Path:
        return self.working_dir / "eval-and-optimize" / "analysis" / f"round-{round_num}-goal.json"

    def _latest_goal_tree_path(self) -> Path | None:
        analysis_dir = self.working_dir / "eval-and-optimize" / "analysis"
        best: tuple[int, Path] | None = None
        for p in analysis_dir.glob("round-*-goal.json"):
            try:
                n = int(p.stem.split("-")[1])
            except (IndexError, ValueError):
                continue
            if best is None or n > best[0]:
                best = (n, p)
        return best[1] if best else None

    def _load_goal_tree(
        self,
        path: Path,
        goal_config: GoalTreeConfig,
        context: str,
    ) -> GoalTree | None:
        try:
            return GoalTree.from_path(path, config=goal_config)
        except (OSError, ValueError) as exc:
            logger.warning(f"[TRAJ] Failed to load {context} goal tree {path}: {exc}")
            return None

    def _format_evolution_table(self, evolution_tree: EvolutionTree) -> str:
        if not evolution_tree.nodes:
            return "(none yet — this is the first round)"
        return evolution_tree.to_markdown_table()

    def _copy_best_to_workspace(self, agent_id: str) -> None:
        src = self.working_dir / "eval-and-optimize" / "agents" / agent_id
        skip_names = {
            "metadata.json",
            "harbor_wrapper.py",
            "dind_environment.py",
            "architecture.md",
        }
        for entry in src.iterdir():
            if entry.name in skip_names:
                continue
            dst = self.working_dir / entry.name
            if entry.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(entry, dst)
            else:
                shutil.copy2(entry, dst)

    def _snapshot_metadata(self, candidate_name: str) -> str | None:
        """Read and return the metadata.json content for a candidate, or None if absent."""
        path = self.working_dir / "eval-and-optimize" / "agents" / candidate_name / "metadata.json"
        try:
            return path.read_text()
        except OSError:
            return None

    def _restore_metadata(self, candidate_name: str, content: str | None) -> None:
        """Restore metadata.json for a candidate to a previously snapshotted content."""
        if content is None:
            return
        path = self.working_dir / "eval-and-optimize" / "agents" / candidate_name / "metadata.json"
        try:
            path.write_text(content)
        except OSError:
            pass

    async def _evaluate_agent(
        self,
        candidate: Candidate,
        dataset: Dataset,
        evaluator: Evaluator,
        task_ids: list[str] | None = None,
    ) -> tuple[Candidate, EvaluationResult]:
        """Run evaluator for one candidate and return the candidate/result pair."""
        eval_dataset = dataset.subset(task_ids) if task_ids is not None else dataset
        # Force a unique job name per candidate so concurrent candidates don't
        # collide on the same results directory when the user sets a fixed job_name.
        options_dict = evaluator.options.model_dump()
        options_dict["job_name"] = f"{candidate.label}-{eval_dataset.id}"
        per_candidate_options = type(evaluator.options).model_validate(options_dict)
        result = await evaluator.run(
            agent=self.working_dir / "eval-and-optimize" / "agents" / candidate.label,
            dataset=eval_dataset,
            options=per_candidate_options,
        )
        return (candidate, result)

    # ------------------------------------------------------------------
    # Private step methods — implementations
    # ------------------------------------------------------------------

    async def _create_experiment_run(
        self,
        *,
        workspace: str,
        backend: ExperimentalistBackend,
        agent_name: str | None,
        agent_path: Path | None,
        insight_ref: str | None,
        config: EvolutionaryOptimizerConfig,
    ) -> ExperimentRun:
        """Create an ExperimentRun entity; return it with its store-assigned id."""
        run = ExperimentRun(
            workspace=workspace,
            agent=agent_name or str(agent_path or ""),
            insight=insight_ref,
            config_snapshot=config.model_dump(mode="json"),
            status="running",
            rounds_completed=0,
        )
        return await backend.create_run(workspace=workspace, run=run)

    async def _generate_architecture_doc(
        self,
        *,
        agent_dir: Path,
        config: EvolutionaryOptimizerConfig,
    ) -> None:
        """Generate ``architecture.md`` for *agent_dir* via Coder."""
        if (agent_dir / "architecture.md").exists():
            return
        agent_id = agent_dir.name
        await Coder(
            workspace=self.working_dir,
            config=self._coder_config(config),
            framework_skills_dirs=self._framework_skills_dirs,
        ).create_architecture_doc(
            agent_id,
            source_path=config.source.source_path,
            entrypoint=config.source.entrypoint,
        )

    async def _evaluate_validation_candidates(
        self,
        *,
        dataset: Dataset,
        evaluator: Evaluator,
        candidates: list[Candidate],
    ) -> dict[str, EvaluationResult]:
        """Evaluate candidates on the validation split; skip any that already have a reward."""
        pending = [c for c in candidates if c.validation_reward is None]
        if not pending:
            return {}
        if pending:
            splits = frozenset({"validation"})
            restore_heldout_splits(self.working_dir, splits=splits)
            try:
                candidate_results = await asyncio.gather(
                    *[
                        self._evaluate_agent(
                            c,
                            dataset,
                            evaluator,
                        )
                        for c in pending
                    ]
                )
            finally:
                ensure_heldout_hidden(self.working_dir, splits=splits)
        return {
            candidate_result[0].label: candidate_result[1]
            for candidate_result in candidate_results
            if candidate_result is not None
        }

    async def _evaluate_insight_candidates(
        self,
        *,
        dataset: Dataset,
        evaluator: Evaluator,
        candidates: list[Candidate],
    ) -> dict[str, EvaluationResult]:
        """Evaluate candidates that do not yet have metrics for this Insight suite."""
        if not list(dataset.list_tasks()):
            return {}
        pending = [candidate for candidate in candidates if candidate.insight_reward is None]
        evaluated = await asyncio.gather(
            *[self._evaluate_agent(candidate, dataset, evaluator) for candidate in pending]
        )
        return {candidate.label: result for candidate, result in evaluated}

    async def _evaluate_and_persist_insight_candidates(
        self,
        *,
        dataset: Dataset,
        evaluator: Evaluator,
        candidates: list[Candidate],
        workspace: str,
        backend: ExperimentalistBackend,
        run_id: str,
    ) -> None:
        """Evaluate and persist Insight-suite metrics for the supplied candidates."""
        results = await self._evaluate_insight_candidates(
            dataset=dataset,
            evaluator=evaluator,
            candidates=candidates,
        )
        for candidate in candidates:
            result = results.get(candidate.label)
            if result is None:
                continue
            await backend.persist_evaluation(
                workspace=workspace,
                result=result,
                candidate=candidate,
                split="insight",
            )
            await self._update_candidate(
                candidate,
                updates={
                    "insight_reward": result.aggregate_metrics,
                    "insight_reward_details": result.trials,
                },
                workspace=workspace,
                backend=backend,
                run_id=run_id,
            )

    async def _generate_initial_goal_tree(
        self,
        *,
        dataset: Dataset,
        disable_trajectory_scoring: bool,
        config: EvolutionaryOptimizerConfig,
        agent_spec_path: Path | None = None,
    ) -> None:
        """Generate and persist the round-0 goal tree if it does not already exist."""
        if disable_trajectory_scoring:
            return
        tree_path = self._goal_tree_path(0)
        if tree_path.exists():
            return
        try:
            tree = await GoalTreeGenerator(
                workspace=self.working_dir,
                config=self._goal_tree_config(config),
                framework_skills_dirs=self._framework_skills_dirs,
            ).generate(dataset, agent_spec=agent_spec_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[TRAJ] Failed to generate initial goal tree; continuing without trajectory scoring: {exc}")
            return
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        tree_path.write_text(tree.to_json())

    async def _select_survivors(
        self,
        candidates: list[Candidate],
        k: int,
    ) -> list[Candidate]:
        """Return the top-k Pareto-optimal and architecturally diverse candidates."""
        ranked = pareto_sort(candidates, lambda c: c.validation_reward or {})
        return await self.select_diverse_survivors(ranked, k)

    async def _evaluate_train_candidates(
        self,
        *,
        dataset: Dataset,
        evaluator: Evaluator,
        max_train_batch_tasks: int | None,
        train_batch_seed: int,
        survivors: list[Candidate],
        round_num: int,
    ) -> dict[str, EvaluationResult]:
        """Evaluate survivors on the train split.

        In full-dataset mode (``max_train_batch_tasks is None``) the eval set is
        identical every round, so a survivor's cached ``train_reward`` is reused and
        only survivors without one are evaluated. In batch mode the sampled batch
        changes per round, so cached rewards are not comparable within a round: every
        survivor is re-evaluated on the same freshly sampled batch.
        """
        if max_train_batch_tasks is None:
            # Full-dataset mode: the eval set is identical every round, so evaluate only
            # survivors that lack a reward and reuse each survivor's cached train reward.
            pending = [s for s in survivors if s.train_reward is None]
            evaluated: list[tuple[Candidate, EvaluationResult]] = []
            if pending:
                evaluated = await asyncio.gather(*[self._evaluate_agent(c, dataset, evaluator) for c in pending])
            results = {candidate.label: result for candidate, result in evaluated}
            for survivor in survivors:
                if survivor.label in results:
                    continue
                if survivor.train_reward is None and survivor.train_reward_details is None:
                    continue
                results[survivor.label] = EvaluationResult(
                    id=f"{survivor.label}-train",
                    aggregate_metrics=survivor.train_reward or {},
                    trials=list(survivor.train_reward_details or []),
                )
            return results

        # Batch mode: the sampled batch changes per round, so a cached reward computed on
        # a different task set is not comparable within a round. Re-evaluate every survivor
        # on the same freshly sampled batch instead of reusing cached rewards.
        if max_train_batch_tasks <= 0:
            raise ValueError("max_train_batch_tasks must be positive or None")
        all_task_ids = sorted(task.id for task in dataset.list_tasks())
        if not all_task_ids:
            raise ValueError(f"No train tasks found in dataset {dataset.id!r}")
        rng = random.Random(train_batch_seed + round_num)
        batch_size = min(max_train_batch_tasks, len(all_task_ids))
        task_ids = sorted(rng.sample(all_task_ids, batch_size))
        evaluated = await asyncio.gather(
            *[self._evaluate_agent(c, dataset, evaluator, task_ids=task_ids) for c in survivors]
        )
        return {candidate.label: result for candidate, result in evaluated}

    async def _analyze_round(
        self,
        *,
        analysis_dir: Path,
        dataset: Dataset,
        evaluations: dict[str, EvaluationResult],
        survivors: list[Candidate],
        round_num: int,
        config: EvolutionaryOptimizerConfig,
        client: AsyncNeMoPlatform | None = None,
        nmp_workspace: str | None = None,
        agent_spec_path: Path | None = None,
    ) -> str:
        """Run AgentAnalyzer per survivor, merge analyses, persist to disk.

        ``client`` and ``nmp_workspace`` are threaded into each ``AgentAnalyzer``
        so its ``TraceAnalyzer`` can load ``intake://`` trial traces; when
        ``None`` those traces are skipped (local ``file://`` traces still load).

        Returns the merged analysis markdown string.
        """
        analysis_path = analysis_dir / f"round-{round_num}.md"
        if analysis_path.exists():
            return analysis_path.read_text()

        per_agent = await asyncio.gather(
            *[
                AgentAnalyzer(
                    workspace=self.working_dir,
                    config=AnalyzerConfig.model_validate(config.analyzer.model_dump()),
                    framework_skills_dirs=self._framework_skills_dirs,
                ).run(
                    agent=s.label,
                    dataset=dataset,
                    evaluation=evaluations[s.label],
                    round=round_num,
                    peer_evaluations={k: v for k, v in evaluations.items() if k != s.label},
                    client=client,
                    nmp_workspace=nmp_workspace,
                    agent_spec=agent_spec_path,
                )
                for s in survivors
            ]
        )
        analysis = await self.merge_analysis(survivors, round_num, [str(a) for a in per_agent])
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(analysis)
        return analysis

    async def _update_goal_tree(
        self,
        *,
        analysis_dir: Path,
        round_num: int,
        analysis: str,
        dataset: Dataset,
        config: EvolutionaryOptimizerConfig,
        agent_spec_path: Path | None = None,
    ) -> None:
        """Refine and persist the goal tree for round *round_num* + 1."""
        next_goal_path = self._goal_tree_path(round_num + 1)
        if next_goal_path.exists():
            return
        goal_tree_path = self._latest_goal_tree_path()
        if goal_tree_path is None:
            return
        goal_config = self._goal_tree_config(config)
        goal_tree = self._load_goal_tree(goal_tree_path, goal_config, context="analysis")
        if goal_tree is None:
            return
        generator = GoalTreeGenerator(
            workspace=self.working_dir, config=goal_config, framework_skills_dirs=self._framework_skills_dirs
        )
        updated_tree = await generator.update(goal_tree, analysis, round_num, dataset, agent_spec=agent_spec_path)
        next_goal_path.parent.mkdir(parents=True, exist_ok=True)
        next_goal_path.write_text(updated_tree.to_json())

    async def _propose_improvements(
        self,
        *,
        workspace: str,
        backend: ExperimentalistBackend,
        analysis: str,
        evolution_tree: EvolutionTree,
        round_num: int,
        phase: Literal["exploration", "exploitation"],
        config: EvolutionaryOptimizerConfig,
    ) -> list[Improvement]:
        """Run Proposer; return up to ``config.max_candidates`` Improvements."""
        proposer = Proposer(
            workspace=self.working_dir,
            config=ProposerConfig.model_validate(config.proposer.model_dump()),
            framework_skills_dirs=self._framework_skills_dirs,
        )
        return await proposer.run(
            analysis=analysis,
            evolution_history=self._format_evolution_table(evolution_tree),
            evolution_tree=evolution_tree,
            round_num=round_num,
            phase=phase,
            max_candidates=config.max_candidates,
        )

    async def _implement_candidates(
        self,
        *,
        workspace: str,
        backend: ExperimentalistBackend,
        dataset: Dataset,
        evaluator: Evaluator,
        candidates: list[Candidate],
        config: EvolutionaryOptimizerConfig,
    ) -> list[Candidate]:
        """Apply proposed changes to each candidate via Coder; return the updated candidates."""
        snapshots = {c.name: self._snapshot_metadata(c.name) for c in candidates}
        try:
            results = await asyncio.gather(
                *[
                    Coder(
                        workspace=self.working_dir,
                        config=self._coder_config(config),
                        framework_skills_dirs=self._framework_skills_dirs,
                    ).run(
                        c,
                        dataset,
                        evaluator,
                        source_path=config.source.source_path,
                        entrypoint=config.source.entrypoint,
                    )
                    for c in candidates
                ],
                return_exceptions=True,
            )
        finally:
            for c in candidates:
                self._restore_metadata(c.name, snapshots[c.name])
        failed = {c.name for c, r in zip(candidates, results, strict=True) if isinstance(r, Exception)}
        # Persist a killed marker on failed candidates so a later resume via
        # EvolutionTree.from_dir does not resurrect them as active survivors
        # (a node is a survivor exactly when killed_round is None).
        for candidate in candidates:
            if candidate.name not in failed:
                continue
            logger.warning(f"Impl failed: {candidate.name}")
            await self._update_candidate(
                candidate,
                workspace=workspace,
                backend=backend,
                run_id=candidate.run_id,
                updates={"killed_round": candidate.round},
            )
        return [c for c in candidates if c.name not in failed]

    async def _reward_trajectories(
        self,
        *,
        workspace: str,
        backend: ExperimentalistBackend,
        dataset: Dataset,
        candidates: list[Candidate],
        config: EvolutionaryOptimizerConfig,
        client: AsyncNeMoPlatform | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Score candidates against the goal tree; return trajectory results keyed by candidate label."""
        tree_path = self._latest_goal_tree_path()
        if tree_path is None:
            logger.info("[TRAJ] No goal tree found, skipping trajectory scoring")
            return {}

        goal_tree = self._load_goal_tree(tree_path, self._goal_tree_config(config), context="trajectory scoring")
        if goal_tree is None:
            logger.info("[TRAJ] Invalid goal tree, skipping trajectory scoring")
            return {}

        pending = [c.label for c in candidates]
        if len(pending) == 1:
            logger.info("[TRAJ] Only one agent to score, skipping GRA")
            return {}

        logger.info(f"[TRAJ] Scoring {len(pending)} agents using GRA")

        nodes = traverse_tree(goal_tree.root)
        node_weights = leaf_weights_by_id(goal_tree.root)
        traces_by_task: dict[str, dict[str, TrialResult]] = {}
        for candidate in candidates:
            if candidate.validation_reward is None and candidate.validation_reward_details is None:
                continue
            for trial in candidate.validation_reward_details or []:
                if trial.trace is None:
                    continue
                traces_by_task.setdefault(trial.task_id, {}).setdefault(candidate.label, trial)

        # Only require agents that actually contributed traces; a candidate with no
        # traces at all (e.g. its validation run failed entirely) must not cause every
        # task to be dropped from scoring.
        agents_with_traces = {label for task_traces in traces_by_task.values() for label in task_traces}
        if len(agents_with_traces) < 2:
            logger.info("[TRAJ] Fewer than two agents have traces, skipping trajectory scoring")
            return {}
        complete_traces = _complete_trace_groups(traces_by_task, list(agents_with_traces))
        dropped = len(traces_by_task) - len(complete_traces)
        if dropped:
            logger.info(f"[TRAJ] Skipping {dropped} tasks missing traces for one or more agents")
        traces_by_task = complete_traces

        task_names = sorted(traces_by_task)
        total_tasks = len(task_names)
        max_tasks = config.max_trajectory_tasks
        if max_tasks and total_tasks > max_tasks:
            task_names = task_names[:max_tasks]
            traces_by_task = {t: traces_by_task[t] for t in task_names}
            logger.info(f"[TRAJ] Selected first {max_tasks}/{total_tasks} complete tasks")

        if not traces_by_task:
            logger.info("[TRAJ] No complete trace groups found, skipping")
            return {}

        scores_by_node_trial_agent: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        keys = [(node.id, task_id) for node in nodes for task_id in traces_by_task]
        logger.info(f"[TRAJ] Starting {len(keys)} GRA scoring tasks...")

        scorer = GroupLeafScorer(workspace=self.working_dir, client=client, nmp_workspace=workspace)
        scoring_results = await asyncio.gather(
            *[scorer.run(node, traces_by_task[task_id], dataset) for node in nodes for task_id in traces_by_task]
        )
        logger.info("[TRAJ] Scoring completed")
        for (node_id, task_id), group_scores in zip(keys, scoring_results, strict=True):
            for aid, gs in group_scores.items():
                scores_by_node_trial_agent[node_id][task_id][aid] = _trajectory_detail_from_reward(gs)

        trajectory_results: dict[str, dict[str, Any]] = {}
        for aid in pending:
            details: dict[str, dict[str, dict[str, Any]]] = {}
            for node in nodes:
                details[node.id] = {
                    tid: by_agent[aid]
                    for tid, by_agent in scores_by_node_trial_agent[node.id].items()
                    if aid in by_agent
                }
            node_means = {
                node.id: sum(item["reward"] for item in details[node.id].values()) / len(details[node.id])
                for node in nodes
                if details[node.id]
            }
            trajectory_reward = sum(node_weights[node.id] * node_means.get(node.id, 0.0) for node in nodes)
            trajectory_results[aid] = {
                "details": details,
                "reward": {
                    "aggregate": trajectory_reward,
                    **node_means,
                },
            }
            logger.info(f"[TRAJ] {aid}: trajectory_reward={trajectory_reward:.3f}")

        return trajectory_results

    async def _finalize(
        self,
        *,
        workspace: str,
        backend: ExperimentalistBackend,
        agents_dir: Path,
        run_entity: ExperimentRun,
        evolution_tree: EvolutionTree,
        agent_name: str,
        insight_dataset: Dataset | None,
    ) -> Candidate | None:
        """Select the winner, copy to workspace root, write final report."""
        # Only survivors that actually have a validation reward are eligible winners.
        scored = [n for n in evolution_tree.nodes.values() if n.is_survivor and n.val_reward]
        front = pareto_front(scored, lambda n: n.val_reward) if scored else []
        best_id = front[0].label if front else None

        restore_heldout_splits(self.working_dir)

        if best_id is None:
            logger.warning("[FINAL] no candidates to finalize")
            run_entity.status = "completed"
            await backend.update_run(workspace=workspace, run=run_entity)
            return None

        evolution_tree.mark_best(best_id)
        self._copy_best_to_workspace(best_id)

        try:
            await self.write_final_report(best_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FINAL] Failed to write final report: {exc}")

        if insight_dataset is not None:
            suggestions = select_insight_promotion_suggestions(
                insight_dataset,
                [node.candidate for node in evolution_tree.nodes.values()],
            )
            write_insight_promotion_section(
                self.working_dir / "eval-and-optimize" / "OPTIMIZATION.md",
                suggestions,
            )

        run_entity.status = "completed"
        run_entity.winner_agent = best_id
        await backend.update_run(workspace=workspace, run=run_entity)

        return evolution_tree.nodes[best_id].candidate

    def _render_summary(
        self,
        rounds_completed: int,
        baseline: Candidate | None,
        winner: Candidate | None,
    ) -> str:
        """Render a human-readable summary of the run outcome."""
        winner_str = winner.name if winner else "none"
        details: list[str] = []
        if winner:
            if winner.validation_reward:
                details.append(f"validation_reward={winner.validation_reward}")
            if baseline is not None and baseline.insight_reward and winner.insight_reward:
                details.append(f"insight_suite=(baseline={baseline.insight_reward}, winner={winner.insight_reward})")
        suffix = f", {', '.join(details)}" if details else ""
        return f"Optimization complete: {rounds_completed} round(s) completed, winner={winner_str}{suffix}"
