# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A strategy written outside the Experimentalist repository.

Everything it uses is public: the entities, the `Strategy` role, and the context
Protocol. It never imports a private module, and it is selected with
`strategy: random-search` in the run config.

The search itself is deliberately trivial. What it demonstrates is that a package
installed beside the plugin can fill the strategy role, reach the platform only through
the context, and land results in Studio like any other run.
"""

import random

from nemo_experimentalist_plugin.entities import Candidate, Proposal
from nemo_experimentalist_plugin.experimentalist.roles import Strategy
from nemo_experimentalist_plugin.experimentalist.seam import StrategyContext

#: Reuses the code-change Proposal kind, so the built-in Coder can build what this emits.
CODE_CHANGE = "code-change"

_IDEAS = [
    "add a retry around the tool call that fails most often",
    "split the single prompt into a plan step and an execute step",
    "cache the lookup the agent repeats within one task",
]


def _validation_score(candidate: Candidate) -> float:
    """Mean of whatever the evaluator measured on the validation channel.

    Reads `metrics`, not `summary`: `summary` is an optional scalar rollup that nothing
    currently writes, so ranking on it scores every candidate zero.
    """
    metrics = candidate.rewards["validation"].metrics
    return sum(metrics.values()) / len(metrics) if metrics else 0.0


class RandomSearch(Strategy):
    """Propose a random change each round and keep whatever scores best."""

    name = "random-search"
    supports_resume = True

    def __init__(self, working_dir=None, config=None, framework_skills_dirs=None, **_: object) -> None:
        """Accept the arguments the runner constructs a strategy with, and ignore the rest."""
        self._rounds = getattr(config, "max_rounds", 3)
        self._per_round = getattr(config, "max_candidates", 1)
        self._builder = getattr(config, "builder", "coder")

    async def run(self, ctx: StrategyContext) -> Candidate | None:
        """Import the agent, then build and score random variants of it."""
        population = await ctx.candidates()
        if not population:
            population = [await self._import_baseline(ctx)]

        rng = random.Random(0)
        for generation in range(1, self._rounds + 1):
            parent = rng.choice(population)
            for _ in range(self._per_round):
                proposal = Proposal(
                    ancestor=parent.id,
                    description=rng.choice(_IDEAS),
                    kind=CODE_CHANGE,
                    payload={"root_cause": "chosen at random", "optimization_type": "add_method", "task_ids": []},
                )
                builder = ctx.component("builder", self._builder)
                candidate = await builder.build(ctx, proposal, generation=generation)
                result = await ctx.evaluate(candidate)
                await ctx.record_reward(candidate, channel="validation", result=result)
                population.append(candidate)
            await ctx.report_progress(completed=generation, total=self._rounds, unit="round")

        return max(population, key=_validation_score)

    async def _import_baseline(self, ctx: StrategyContext) -> Candidate:
        """Commit the agent under test unchanged, using the built-in import Builder."""
        proposal = Proposal(ancestor=None, description="the agent under test", kind="import", payload={})
        return await ctx.component("builder", "import").build(ctx, proposal, generation=0)
