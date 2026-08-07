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
from typing import Any

from nemo_experimentalist_plugin.entities import Candidate

# Imported from `resolve` rather than `.loop`, which merely re-exports it: `loop` imports
# this module, so going through it would be circular.
from nemo_experimentalist_plugin.experimentalist import roles
from nemo_experimentalist_plugin.experimentalist.components.models import pareto_front
from nemo_experimentalist_plugin.skills import skills_dir
from nooa import Agent, CodeActStrategy, TextSkill, hidden, strategy
from nooa.agentdoc import doc
from nooa.config import CodeActConfig
from pydantic import BaseModel, Field

from .model_config import ModelTiers

logger = logging.getLogger(__name__)


class TerminatorConfig(BaseModel):
    """Tuning parameters for early stopping."""

    min_rounds_before_stopping: int = Field(
        default=3, description="Scored rounds required before convergence can stop a run."
    )


class TerminationDecision(BaseModel):
    """Structured result of a termination assessment.

    Attributes:
        stop: True when the optimization loop should stop.
        reason: Human-readable explanation; empty string when ``stop`` is False.
    """

    stop: bool
    reason: str = ""


class Terminator(Agent, roles.Terminator):
    """Decides when the evolutionary optimization loop should stop."""

    name = "convergence"

    def __init__(
        self, *, models: ModelTiers | None = None, config: TerminatorConfig | None = None, **kwargs: Any
    ) -> None:
        tiers = models or ModelTiers()
        super().__init__(llm=kwargs.pop("llm", None) or tiers.fast, **kwargs)
        self._models = tiers
        self._config = config or TerminatorConfig()
        self.terminator_skill = TextSkill(path=skills_dir() / "terminator")

    @hidden
    async def run(
        self,
        *,
        round_num: int,
        candidates: list[Candidate],
        prior_analysis: str | None = None,
    ) -> TerminationDecision:
        """Canonical termination decision, consulted once per round at the top of the loop.

        Early stopping only: the round budget belongs to the loop, so a terminator that
        never stops still cannot produce an unbounded run.

        Args:
            round_num: Rounds completed so far.
            candidates: The scored population; convergence is judged from their rewards.
            prior_analysis: Markdown analysis from the previous round, if any.

        Returns:
            A :class:`TerminationDecision`.
        """
        return await self.assess_convergence(candidates=candidates, prior_analysis=prior_analysis)

    @hidden
    async def assess_convergence(
        self,
        *,
        candidates: list[Candidate],
        prior_analysis: str | None,
    ) -> TerminationDecision:
        """Decide whether to early-stop before running another round.

        Returns ``stop=False`` without consulting a model when there is no prior round
        to compare against. Otherwise consults :meth:`_has_converged`.

        Args:
            candidates: The scored population.
            prior_analysis: Markdown analysis from the previous round, if any.

        Returns:
            A :class:`TerminationDecision`.
        """
        if prior_analysis is None:
            return TerminationDecision(stop=False)
        converged = await self._has_converged(
            candidates=candidates,
            prior_analysis=prior_analysis,
            min_rounds_before_stopping=self._config.min_rounds_before_stopping,
        )
        if converged:
            return TerminationDecision(stop=True, reason="optimization converged (Pareto front stagnated)")
        return TerminationDecision(stop=False)

    @hidden
    async def _has_converged(
        self,
        *,
        candidates: list[Candidate],
        prior_analysis: str,
        min_rounds_before_stopping: int,
    ) -> bool:
        """Return True if the optimization has converged and should stop early."""
        # Truthy check, not ``is not None``: an unscored candidate has an empty metrics
        # dict, and counting those would skew both the round cutoff and the front.
        scored = [c for c in candidates if c.rewards["validation"].metrics]
        rounds = sorted({n.generation for n in scored})
        if len(rounds) < min_rounds_before_stopping:
            return False
        cutoff_round = rounds[-min_rounds_before_stopping]
        old = [n for n in scored if n.generation <= cutoff_round]
        if not old:
            return False
        metrics = lambda c: c.rewards["validation"].metrics or {}  # noqa: E731
        old_front_ids = {c.id for c in pareto_front(old, metrics)}
        full_front_ids = {c.id for c in pareto_front(scored, metrics)}
        if full_front_ids.issubset(old_front_ids):
            return True
        return await self.qualitative_stop_check(prior_analysis)

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5)))
    async def qualitative_stop_check(self, analysis: str) -> bool:  # ty: ignore[invalid-return-type]  # pyright: ignore[reportReturnType]
        """Decide whether the optimization has qualitatively plateaued; return True to stop.

        Judge the round ``analysis`` text against the terminator skill's stop
        heuristics (prefilled below). Return True only with concrete textual
        evidence of stagnation in ``analysis``; when in doubt, return False.
        """
        print(doc(self.terminator_skill))
        ...
