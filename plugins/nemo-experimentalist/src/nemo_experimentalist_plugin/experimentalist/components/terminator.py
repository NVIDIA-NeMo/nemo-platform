# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Terminator step — decides when the evolutionary optimization loop should stop.

The loop consults :meth:`Terminator.run` once per round; it stops when the round
budget is exhausted or the optimization has converged (a deterministic Pareto-front
check, with a qualitative LLM check as a tie-breaker). Publishing the winner is the
loop's job (``backend.publish_candidate``), not the Terminator's.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from nemo_experimentalist_plugin.skills import skills_dir
from nooa import Agent, CodeActStrategy, TextSkill, hidden, strategy
from nooa.agentdoc import doc
from nooa.config import CodeActConfig
from pydantic import BaseModel

from .model_config import get_fast_model
from .models import pareto_front

if TYPE_CHECKING:
    from .loop import EvolutionaryOptimizerConfig
    from .models import EvolutionTree

logger = logging.getLogger(__name__)


class TerminationDecision(BaseModel):
    """Structured result of a termination assessment.

    Attributes:
        stop: True when the optimization loop should stop.
        reason: Human-readable explanation; empty string when ``stop`` is False.
    """

    stop: bool
    reason: str = ""


class Terminator(Agent, llm=get_fast_model()):
    """Decides when the evolutionary optimization loop should stop."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.terminator_skill = TextSkill(path=skills_dir() / "terminator")

    @hidden
    async def run(
        self,
        *,
        round_num: int,
        evolution_tree: EvolutionTree,
        prior_analysis: str | None,
        config: EvolutionaryOptimizerConfig,
    ) -> TerminationDecision:
        """Canonical termination decision, consulted once per round at the top of the loop.

        Stops when the round budget is exhausted; otherwise stops when the
        optimization has converged. Composes :meth:`assess_round_budget` and
        :meth:`assess_convergence` (budget first — it is cheap and deterministic,
        so an exhausted budget avoids the qualitative LLM call).

        Args:
            round_num: Rounds completed so far.
            evolution_tree: Live tree of scored candidates across rounds.
            prior_analysis: Markdown analysis from the previous round, if any.
            config: Active optimizer config (read-only).

        Returns:
            A :class:`TerminationDecision`.
        """
        budget = self.assess_round_budget(round_num=round_num, config=config)
        if budget.stop:
            return budget
        return await self.assess_convergence(
            evolution_tree=evolution_tree,
            prior_analysis=prior_analysis,
            config=config,
        )

    @hidden
    async def assess_convergence(
        self,
        *,
        evolution_tree: EvolutionTree,
        prior_analysis: str | None,
        config: EvolutionaryOptimizerConfig,
    ) -> TerminationDecision:
        """Decide whether to early-stop before running another round.

        Mirrors the original top-of-loop gating: returns ``stop=False`` immediately
        when there is no prior analysis to reason about or when the convergence
        check is disabled. Otherwise consults :meth:`_has_converged`.

        Args:
            evolution_tree: Live tree of scored candidates across rounds.
            prior_analysis: Markdown analysis from the previous round, if any.
            config: Active optimizer config (read-only).

        Returns:
            A :class:`TerminationDecision`.
        """
        if prior_analysis is None or config.disable_convergence_check:
            return TerminationDecision(stop=False)
        converged = await self._has_converged(
            evolution_tree=evolution_tree,
            prior_analysis=prior_analysis,
            min_rounds_before_stopping=config.min_rounds_before_stopping,
        )
        if converged:
            return TerminationDecision(stop=True, reason="optimization converged (Pareto front stagnated)")
        return TerminationDecision(stop=False)

    @hidden
    def assess_round_budget(
        self,
        *,
        round_num: int,
        config: EvolutionaryOptimizerConfig,
    ) -> TerminationDecision:
        """Decide whether the round budget is exhausted.

        Args:
            round_num: The number of rounds completed so far.
            config: Active optimizer config (read-only).

        Returns:
            A :class:`TerminationDecision` that stops when
            ``round_num >= config.max_rounds``.
        """
        if round_num >= config.max_rounds:
            return TerminationDecision(stop=True, reason=f"reached max_rounds ({config.max_rounds})")
        return TerminationDecision(stop=False)

    @hidden
    async def _has_converged(
        self,
        *,
        evolution_tree: EvolutionTree,
        prior_analysis: str,
        min_rounds_before_stopping: int,
    ) -> bool:
        """Return True if the optimization has converged and should stop early."""
        # Truthy check (not ``is not None``): ``EvolutionNode.val_reward`` returns ``{}`` for
        # unscored nodes, so ``is not None`` would pull them in and skew the round cutoff /
        # Pareto front. Match ``EvolutionTree.get_best()``.
        scored = [n for n in evolution_tree.nodes.values() if n.val_reward]
        rounds = sorted({n.round for n in scored})
        if len(rounds) < min_rounds_before_stopping:
            return False
        cutoff_round = rounds[-min_rounds_before_stopping]
        old = [n for n in scored if n.round <= cutoff_round]
        if not old:
            return False
        old_front_ids = {n.label for n in pareto_front(old, lambda n: n.val_reward)}
        full_front_ids = {n.label for n in pareto_front(scored, lambda n: n.val_reward)}
        if full_front_ids.issubset(old_front_ids):
            return True
        return await self.qualitative_stop_check(prior_analysis)

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5)))
    async def qualitative_stop_check(self, analysis: str) -> bool:  # pyright: ignore[reportReturnType]
        """Decide whether the optimization has qualitatively plateaued; return True to stop.

        Judge the round ``analysis`` text against the terminator skill's stop
        heuristics (prefilled below). Return True only with concrete textual
        evidence of stagnation in ``analysis``; when in doubt, return False.
        """
        print(doc(self.terminator_skill))
        ...
