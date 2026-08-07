# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Which candidates breed, and which one wins."""

from typing import Any

from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist import roles
from nemo_experimentalist_plugin.experimentalist.components.model_config import ModelTiers
from nemo_experimentalist_plugin.experimentalist.components.models import pareto_front, pareto_sort
from nooa import Agent, CodeActStrategy, strategy
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from pydantic import BaseModel, Field


class SelectorConfig(BaseModel):
    """Tuning parameters for survivor selection."""

    max_summary_tokens: int = Field(default=80_000, description="Max tokens the token-budget summarizer may use.")
    objectives: list[str] = Field(
        default_factory=lambda: ["validation"],
        description=(
            "Reward channels ranked on. Selection policy lives here rather than on the "
            "entity: 'insight rewards must never feed Pareto selection' is a selector "
            "concern, and a flag on the channel would be wrong for anyone ranking on train."
        ),
    )


# Selection is two questions, and only the first needs a model: Pareto ranking is
# arithmetic over reward channels, while choosing among incomparable candidates inside one
# front is a judgement about architectural diversity. Splitting them is what lets a
# numeric strategy reuse the ranking and skip the model entirely.
class ParetoDiversitySelector(Agent, roles.Selector):
    """Pareto-rank on the configured objectives, then pick diverse survivors with a model."""

    name = "pareto-llm-diversity"

    def __init__(
        self,
        config: SelectorConfig | None = None,
        models: ModelTiers | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the selector."""
        tiers = models or ModelTiers()
        super().__init__(llm=kwargs.pop("llm", None) or tiers.smart, **kwargs)
        self._config = config or SelectorConfig()
        TokenBudgetSummarizer.install(
            self, llm=tiers.fast, config=TokenBudgetConfig(max_tokens=self._config.max_summary_tokens)
        )

    def rank(self, candidates: list[Candidate]) -> list[Candidate]:
        """Sort by non-domination rank over the configured objective channels."""
        return pareto_sort(candidates, self._objective_metrics)

    async def survivors(self, candidates: list[Candidate], *, k: int) -> list[Candidate]:
        """Up to *k* candidates to carry into the next round as parents."""
        return await self.select_diverse_survivors(self.rank(candidates), k)

    def winner(self, candidates: list[Candidate]) -> Candidate | None:
        """The best of the still-alive candidates that carry a measured objective.

        A candidate eliminated in an earlier round cannot win, and one with no measurement
        on the ranked channel cannot be compared.
        """
        eligible = [c for c in candidates if c.killed_generation is None and self._objective_metrics(c)]
        front = pareto_front(eligible, self._objective_metrics) if eligible else []
        return front[0] if front else None

    def _objective_metrics(self, candidate: Candidate) -> dict[str, float]:
        """The metrics this selector ranks on, merged across its objective channels."""
        merged: dict[str, float] = {}
        for channel in self._config.objectives:
            merged.update(candidate.rewards[channel].metrics or {})
        return merged

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=100, cell_timeout=3600.0)))
    async def select_diverse_survivors(self, ranked: list[Candidate], k: int) -> list[Candidate]:  # pyright: ignore[reportReturnType]
        """Choose up to k survivors from Pareto-ranked candidates.

        ``ranked`` is already Pareto-sorted using outcome and trajectory scores:
        front 0 (non-dominated) first, then front 1, etc. Inside a front,
        candidates are incomparable, so prefer agents with distinct architecture
        changes, complementary task coverage, and different trajectory strengths.

        To avoid getting stuck on the same agents round after round:
        - Prefer a mix of recent and older lineages over k agents from one branch.
        - Prefer an agent whose failures differ from the others already chosen.
        - Read each candidate's `description` and `generated_from` to tell what
          actually changed; two agents with near-identical changes are one choice.

        Return exactly the candidates you choose, in preference order, at most k.
        """
        ...
