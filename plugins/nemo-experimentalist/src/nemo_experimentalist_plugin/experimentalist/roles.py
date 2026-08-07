# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The roles a component can fill, and what each must implement.

Each class sets ``role`` and leaves ``name`` empty, so it declares a slot without
claiming to implement it.

A role's *signature* is owned by whatever resolves it, not by this module: an
out-of-tree builder targets the evolutionary strategy's ``builder`` contract, because
that strategy is what calls it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from nemo_experimentalist_plugin.entities import Candidate, Dataset, EvaluationResult, Proposal, RewardRecord
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import Evaluator, EvaluatorConfig
from nemo_experimentalist_plugin.experimentalist.registry import Component
from nemo_experimentalist_plugin.experimentalist.seam import BuilderContext, StrategyContext

if TYPE_CHECKING:
    from nemo_experimentalist_plugin.experimentalist.components.terminator import TerminationDecision


class Strategy(Component):
    """Optimize the agent under test and return the winner.

    One entry point, not two: a strategy reads ``ctx.resuming`` and one that does not care
    ignores it. ``supports_resume`` is a ``ClassVar`` rather than an optional ``resume()``
    so it is answerable from the class — which is what lets ``strategies list`` report it
    without constructing anything. The runner happens to read it off the instance it
    already resolved.
    """

    role: ClassVar[str] = "strategy"

    #: When False the runner refuses a resume loudly, naming the strategy, rather than
    #: silently starting over. These runs cost hours; the silent restart is the expensive
    #: failure, and preventing it is the whole point of the flag.
    supports_resume: ClassVar[bool] = False

    async def run(self, ctx: StrategyContext) -> Candidate | None:
        """Run the optimization and return the winning Candidate, or None if there is none."""
        raise NotImplementedError


class Evaluation(Component, Evaluator):
    """Measure a candidate's artifact and return an EvaluationResult.

    Named for the role rather than the implementation: it is platform vocabulary
    (`EvaluationResult`, `persist_evaluation`, NeMo Evaluator), and it measures the
    *outcome*, where a trajectory-scorer measures the process of the same run.

    Inherits :class:`Evaluator`, so resolving this role yields something that is both
    constructible (``options``, ``experiment_dir``) and carries the two ClassVars — one
    type rather than an implicit pairing a plugin author has to infer.
    """

    role: ClassVar[str] = "evaluation"

    #: Dataset implementation this evaluator consumes, and the model it validates its
    #: options with. Declared here so resolving the component is enough to build both:
    #: a factory keyed on a hardcoded name cannot be swapped by config, whatever the
    #: registry says.
    dataset_type: ClassVar[type[Dataset]]
    config_type: ClassVar[type[EvaluatorConfig]]

    #: ``run(agent, dataset, ...) -> EvaluationResult`` is inherited from :class:`Evaluator`
    #: rather than redeclared: overriding it here with a stub would shadow the working
    #: implementation every evaluator relies on.


class Proposer(Component):
    """Turn scored candidates into Proposals for the next round."""

    role: ClassVar[str] = "proposer"

    #: Proposal kinds this Proposer emits, checked against the Builder's ``accepts``
    #: before the run starts. Empty means undeclared, and the pairing is only found out
    #: per proposal, a round at a time.
    produces: ClassVar[frozenset[str]] = frozenset()

    async def run(
        self,
        *,
        analysis: str,
        candidates: list[Candidate],
        round_num: int,
        max_candidates: int,
        hint: str | None = None,
    ) -> list[Proposal]:
        """Up to *max_candidates* Proposals for the next round.

        Args:
            analysis: The round's diagnosis, or an empty string when none was produced.
            candidates: The scored population to propose against; lineage is on each one.
            round_num: The round these Proposals are for.
            max_candidates: Upper bound. Returning fewer is normal.
            hint: A free-form steer from the strategy — the evolutionary loop alternates
                "exploration" and "exploitation". Ignorable.
        """
        raise NotImplementedError


class Analyzer(Component):
    """Diagnose why candidates fail, as input to proposing.

    Optional: a strategy that does not reason about failures — numeric search — selects
    none and skips the train evaluation that feeds it.
    """

    role: ClassVar[str] = "root-cause-analyzer"

    async def run(
        self,
        *,
        candidate: Candidate,
        dataset: Dataset,
        evaluation: EvaluationResult,
        peer_evaluations: dict[str, EvaluationResult] | None = None,
        round_num: int | None = None,
        agent_spec: Path | None = None,
    ) -> object:
        """Diagnose why *candidate* scored what it did, for the Proposer to act on.

        Peers are passed so a diagnosis can say what this candidate did differently,
        which is the difference between a root cause and a description.
        """
        raise NotImplementedError


class Terminator(Component):
    """Decide whether to stop before the round budget is spent."""

    role: ClassVar[str] = "terminator"

    async def run(
        self,
        *,
        round_num: int,
        candidates: list[Candidate],
        prior_analysis: str | None = None,
    ) -> "TerminationDecision":
        """Whether to stop *before* spending another round.

        Only early stopping: the round budget is the loop's own and holds regardless, so
        a terminator that never stops cannot produce an unbounded run.
        """
        raise NotImplementedError


class TrajectoryScorer(Component):
    """Score the steps a candidate took, not just its outcome.

    A second measurement of the same run, landing in its own reward channel.
    """

    role: ClassVar[str] = "trajectory-scorer"

    async def run(
        self,
        ctx: "StrategyContext",
        *,
        candidates: list[Candidate],
        round_num: int = 0,
        analysis: str | None = None,
    ) -> dict[Candidate, RewardRecord]:
        """One reward record per candidate, measuring *how* it got there.

        Whatever a scorer needs to decompose a trajectory — the built-in ranks against a
        goal tree it builds and refines itself — is its own state, kept wherever it likes
        under the run. The strategy hands over the population and this round's analysis
        and takes back reward records.

        Returning fewer records than candidates is normal: a candidate with no usable
        traces is skipped rather than scored zero.
        """
        raise NotImplementedError


class Selector(Component):
    """Decide which candidates breed, and which one wins.

    Ranks on reward channels alone and never reads a Proposal or an artifact, which is
    what lets one selector serve a code-optimizing run and a numeric one.
    """

    role: ClassVar[str] = "selector"

    async def survivors(self, candidates: list[Candidate], *, k: int) -> list[Candidate]:
        """Up to *k* candidates to carry into the next round as parents."""
        raise NotImplementedError

    def winner(self, candidates: list[Candidate]) -> Candidate | None:
        """The run's winner, or None when nothing is eligible."""
        raise NotImplementedError


class Builder(Component):
    """Turn one Proposal into one committed Candidate.

    The Builder owns the whole span: it asks the context for somewhere to work, writes,
    and hands back the committed Candidate. No filesystem path crosses into it from
    outside, which is what lets candidate storage move without changing this signature.

    A build that cannot succeed raises. It leaves no Candidate behind, so there is no
    half-finished record to resurrect on resume and no killed marker to remember to write.
    """

    role: ClassVar[str] = "builder"

    #: Proposal kinds this Builder accepts. The strategy drops a proposal no configured
    #: Builder claims, so a Proposer and Builder that disagree produce empty rounds.
    accepts: ClassVar[frozenset[str]] = frozenset()

    async def build(self, ctx: BuilderContext, proposal: Proposal, *, generation: int) -> Candidate:
        """Build *proposal* and return the Candidate committed for it.

        Args:
            ctx: The two verbs a Builder gets — reserve a working copy, commit the result.
            proposal: What to change, and what to change it from.
            generation: Strategy-supplied grouping index, stamped onto the Candidate.
                It travels through rather than being used, because the strategy owns what
                a generation means and the Builder is what holds the commit.
        """
        raise NotImplementedError

    async def describe(self, artifact: Path) -> None:
        """Write whatever a later build of *artifact* will want to read back.

        The Coder documents the architecture here, because the next build's proposal is
        written against that document. The strategy calls this for the baseline; a
        Builder calls it for the candidates it builds. A Builder with nothing to say does
        nothing, which is why this is not abstract.
        """
        return None
