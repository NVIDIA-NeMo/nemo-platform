# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import Any, Literal, get_args

from nemo_experimentalist_plugin.experimentalist.components.models import (
    EvolutionTree,
    OptimizationType,
)
from nooa import Agent, CodeActStrategy, strategy
from nooa.agentdoc import doc, spec
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from nooa.skill_registry import SkillRegistry
from pydantic import BaseModel, Field

from .cards import Optimize
from .model_config import get_fast_model, get_smart_model
from .tools import WorkspaceTool
from .util import load_framework_skills


class Improvement(BaseModel):
    """A proposed single-change improvement for a specific ancestor agent."""

    ancestor: str
    root_cause: str = Field(
        min_length=1,
        description=(
            "The diagnosed cause of poor performance from the analysis — WHY the agent fails, "
            "not what would fix it. Must complete: 'The agent underperforms because...' "
            "Do not mention the proposed change or any remedy here."
        ),
    )
    optimization: str = Field(
        min_length=1,
        description=(
            "Graph-level description of the change in terms of the architecture diagram: "
            "which node is added, removed, or modified; which edge changes; which prompt is rewritten. "
            "Must NOT reference source file paths, line numbers, or implementation details."
        ),
    )
    optimization_type: OptimizationType
    task_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Task ids from the analysis that most directly exercise this root cause — "
            "the concrete tasks the agent fails (or barely passes) for this reason. "
            "The coder uses these to validate the fix, so pick tasks whose failure "
            "evidence in the analysis is caused by `root_cause`. 2-3 is typical."
        ),
    )


class ProposerConfig(BaseModel):
    """Configuration for Proposer tuning parameters."""

    max_summary_tokens: int = Field(
        default=80_000,
        description="Max tokens the token-budget summarizer may use.",
    )


class Proposer(Agent, llm=get_smart_model()):
    """Propose the next round's isolated optimization candidates."""

    def __init__(
        self,
        workspace: Path,
        config: ProposerConfig | None = None,
        framework_skills_dirs: list[Path] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._config = config or ProposerConfig()
        self._workspace_path = workspace.resolve()
        self.workspace = WorkspaceTool(workspace=self._workspace_path)
        self.context["workspace_tool_documentation"] = doc(WorkspaceTool)

        self.skills: SkillRegistry = SkillRegistry(self)
        spec(self, "skills", hidden=True)
        load_framework_skills(self.skills, framework_skills_dirs or [])

        self.optimize = Optimize()
        TokenBudgetSummarizer.install(
            self,
            llm=get_fast_model(),
            config=TokenBudgetConfig(max_tokens=self._config.max_summary_tokens),
        )

    async def run(
        self,
        analysis: str,
        evolution_history: str,
        evolution_tree: EvolutionTree,
        round_num: int,
        phase: Literal["exploration", "exploitation"],
        max_candidates: int,
    ) -> list[Improvement]:
        """Return up to max_candidates targeted improvement proposals.

        Args:
            analysis: merged round analysis markdown with root causes already enumerated.
            evolution_history: markdown table of prior rounds for context.
            evolution_tree: live tree used to derive survivors and tried optimization types.
            round_num: current optimization round number; used to filter survivors.
            phase: "exploration" for novel directions, "exploitation" to refine the best.
            max_candidates: maximum number of Improvement objects to return.

        Returns:
            list[Improvement]: up to max_candidates targeted improvement proposals.

        """
        all_types = set(get_args(OptimizationType))
        tried_types = sorted(
            {
                n.optimization_type
                for n in evolution_tree.nodes.values()
                if n.optimization_type and n.optimization_type in all_types
            }
        )
        available_types = sorted(all_types - set(tried_types))
        proposal_survivors = evolution_tree.survivors(round_num)

        agents_dir = self._workspace_path / "eval-and-optimize" / "agents"
        survivor_context: list[dict[str, Any]] = []
        for s in proposal_survivors:
            arch_path = agents_dir / s.label / "architecture.md"
            try:
                arch_text = arch_path.read_text()
            except OSError:
                arch_text = f"(architecture.md missing for {s.label})"
            try:
                candidate = self.workspace.get_metadata(s.label)
                meta = candidate.slim().model_dump(exclude={"artifacts"})
            except Exception:  # noqa: BLE001
                meta = {}
            survivor_context.append(
                {
                    "id": s.label,
                    "reward": s.validation_reward or {},
                    "trajectory_reward": s.validation_trajectory_reward or {},
                    "metadata": meta,
                    "architecture": arch_text,
                }
            )

        improvements = await self._run_with_context(
            analysis=analysis,
            evolution_history=evolution_history,
            tried_types=tried_types,
            available_types=available_types,
            survivors=survivor_context,
            cards_index=doc(self.optimize),
            phase=phase,
            max_candidates=max_candidates,
        )
        self._validate_improvements(
            improvements=improvements,
            max_candidates=max_candidates,
            allowed_types=set(available_types) or all_types,
        )
        return improvements

    @staticmethod
    def _validate_improvements(
        *,
        improvements: list[Improvement],
        max_candidates: int,
        allowed_types: set[str],
    ) -> None:
        if not improvements:
            raise ValueError("Proposer returned no improvements")
        if len(improvements) > max_candidates:
            raise ValueError(f"Proposer returned {len(improvements)} improvements; maximum is {max_candidates}")
        seen_types: set[str] = set()
        seen_descriptions: set[str] = set()
        for improvement in improvements:
            optimization_type = improvement.optimization_type
            if optimization_type not in allowed_types:
                raise ValueError(
                    f"Proposer returned disallowed optimization_type "
                    f"{optimization_type!r}; allowed: {sorted(allowed_types)}"
                )
            if optimization_type in seen_types:
                raise ValueError(f"Proposer returned duplicate optimization_type {optimization_type!r}")
            seen_types.add(optimization_type)

            description = improvement.optimization.strip()
            if description in seen_descriptions:
                raise ValueError(f"Proposer returned duplicate optimization text: {description!r}")
            seen_descriptions.add(description)

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=20, cell_timeout=3600.0)))
    async def _run_with_context(
        self,
        analysis: str,
        evolution_history: str,
        tried_types: list[str],
        available_types: list[str],
        survivors: list[dict[str, Any]],
        cards_index: str,
        phase: Literal["exploration", "exploitation"],
        max_candidates: int,
    ) -> list[Improvement]:
        """Pick up to `max_candidates` targeted improvements grounded in root causes.

        Args:
        - analysis (str): round analysis with root causes already enumerated
        - evolution_history (str): markdown table of prior rounds, for context
        - tried_types (list[str]): optimization_types already attempted — AVOID these
        - available_types (list[str]): types not yet tried — PICK FROM THESE
        - survivors (list[dict]): each {id, reward, trajectory_reward, metadata,
          architecture}; these are your branching candidates with their architecture.md
          already loaded
        - cards_index (str): pre-rendered `doc(self.optimize)` showing the card index.
          Load a specific card on demand via `print(doc(self.optimize.<name>))`.
        - phase (Literal): "exploration" = novel directions; "exploitation" = improve current best
        - max_candidates (int): max number of Improvements to return (typically 3)

        Returns:
        - list[Improvement]: up to `max_candidates` Improvements.

        ## Working level
        You are a graph-level architect. Reason exclusively from the architecture
        diagrams in `survivors[*].architecture` — do NOT read source files or
        inspect implementation details. Your job is to identify WHAT changes at
        the diagram level, not HOW it is implemented in code.

        ## Per-improvement requirements
        For each Improvement you propose:
        1. Identify ONE root cause from the analysis: the specific reason the agent
           underperforms, stated as a diagnosis ("The agent fails because X is absent /
           misconfigured / too vague"). Do NOT include the proposed remedy here — that
           belongs in `optimization`. If you cannot articulate the failure cause
           independently of the fix, drop the hypothesis.
        2. Pick the ancestor from `survivors` most affected by that root cause.
        3. Load the matching card with `doc(self.optimize.<name>)` and pick ONE
           optimization_type from `available_types` that the card covers.
        4. Read the ancestor's architecture diagram (in `survivors[*].architecture`)
           to understand the current graph shape. If the change touches a skill,
           find it in the diagram — do NOT open source files.
        5. Write `root_cause` (pure diagnosis — why the agent fails, no remedy)
           and `optimization` (the graph-level change that addresses it). These
           must be independently readable: `root_cause` explains the failure,
           `optimization` describes the diagram delta (node added/removed/modified,
           edge changed, prompt rewritten). No file paths, no line numbers, no
           code snippets in either field.
        6. Set `task_ids` to the tasks in the analysis whose failure evidence is
           caused by this `root_cause` — the concrete tasks the coder should use to
           validate the fix. Pick 2-3 tasks the ancestor actually fails (or barely
           passes) for this reason; do not pad with unrelated passing tasks.

        ## Branching rules
        - Branch from any survivor — usually the top scorer, but a lower-scoring
          ancestor is the right base when it uniquely passes tasks the top scorer fails.
        - If two survivors have complementary failures (each passes what the other
          fails), propose a cross-pollination improvement that merges their approaches.

        ## Phase
        - exploration: novel directions, even speculative ones
        - exploitation: refine the current best survivor. When the obvious targeted
          improvements have already been tried, do NOT stop — pick the best untried
          direction from `available_types` and explore it.

        ## MANDATORY
        - Return between 1 and max_candidates Improvements. NEVER return [].
        - Each Improvement.optimization_type MUST be in `available_types`. If
          `available_types` is empty, pick the least-tried type from the tried set.
        - Each improvement in a round should target a different degree of freedom;
          two improvements touching the same axis are only allowed when no other
          viable direction exists.
        - Each Improvement must make exactly ONE targeted change. Do not bundle
          prompt edits with code edits, config changes with tool additions, cleanup
          with behavior changes, or multiple unrelated fixes in one candidate.
        - `optimization` MUST be a graph-level description. Reject any draft that
          names a source file, a line number, or any code construct.
        """
        ...
