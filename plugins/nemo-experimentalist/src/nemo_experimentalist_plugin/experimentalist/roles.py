# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The roles a component can fill, and what each must implement.

Two roles are resolvable in M1: the ``strategy`` the runner runs, and the ``builder`` that
turns one Proposal into one Candidate. The rest — proposer, selector, terminator,
root-cause-analyzer, trajectory-scorer — are still constructed directly by the
evolutionary strategy and become registry citizens in M2.

Each class here sets ``role`` and leaves ``name`` empty, so it declares a slot without
registering as an implementation of it.

A role's *signature* is owned by whatever resolves it, not by this module: an out-of-tree
builder targets the evolutionary strategy's ``builder`` contract, because that strategy is
what calls it. These are the contracts as that strategy states them.
"""

from __future__ import annotations

from typing import ClassVar

from nemo_experimentalist_plugin.entities import Candidate, Proposal
from nemo_experimentalist_plugin.experimentalist.registry import Component
from nemo_experimentalist_plugin.experimentalist.seam import BuilderContext, StrategyContext


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


class Builder(Component):
    """Turn one Proposal into one committed Candidate.

    The Builder owns the whole span: it asks the context for somewhere to work, writes,
    and hands back the committed Candidate. No filesystem path crosses into it from
    outside, which is what lets candidate storage move without changing this signature.

    A build that cannot succeed raises. It leaves no Candidate behind, so there is no
    half-finished record to resurrect on resume and no killed marker to remember to write.
    """

    role: ClassVar[str] = "builder"

    #: Proposal kinds this Builder can build.
    #:
    #: Checked per proposal at build time: the strategy drops one whose ``kind`` no
    #: configured Builder accepts, and logs it. That is weaker than §3.2 wants — it
    #: describes a resolution-time check that every kind the Proposer *produces* is
    #: covered, so a mismatch fails before the run spends anything rather than after
    #: hours. The check cannot exist yet: ``produces`` lives on the Proposer, and the
    #: Proposer is not a resolved component until M2. Until then a mismatched pairing
    #: yields rounds that build nothing.
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
