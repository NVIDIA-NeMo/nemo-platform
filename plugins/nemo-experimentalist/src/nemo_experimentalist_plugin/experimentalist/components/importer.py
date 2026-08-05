# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The Builder that takes an agent as it arrived and commits it unchanged."""

from nemo_experimentalist_plugin.entities import Candidate, Proposal
from nemo_experimentalist_plugin.experimentalist.roles import Builder
from nemo_experimentalist_plugin.experimentalist.seam import BuilderContext

#: Proposal kind meaning "commit this source as a candidate, changing nothing".
IMPORT = "import"


def import_proposal(description: str = "the agent under test, unchanged") -> Proposal:
    """A Proposal asking for the agent under test to be committed as-is.

    ``ancestor`` is None because nothing precedes it — which is also what makes the
    resulting Candidate the baseline. Nothing else distinguishes it.
    """
    return Proposal(ancestor=None, description=description, kind=IMPORT, payload={})


class Importer(Builder):
    """Commit a candidate that is the agent under test, unchanged.

    The baseline is not a special kind of thing, only the first candidate and the one
    with no parent. Modelling its arrival as a Proposal like any other is what removes
    the alternative creation path: ``commit_candidate`` is the only way a Candidate is
    born, ``generated_from`` is never empty, and a strategy that wants several roots —
    importing three agents to compare — gets that for free rather than working around a
    verb that assumed one.

    It also lands on ``agent-0`` without anyone naming it: the first fork of a run
    reserves the first free handle.
    """

    name = "import"
    accepts = frozenset({IMPORT})

    async def build(self, ctx: BuilderContext, proposal: Proposal, *, generation: int = 0) -> Candidate:
        """Fork the agent under test and commit it with nothing changed."""
        fork = await ctx.fork(proposal)
        return await ctx.commit_candidate(proposal=proposal, artifact=fork.workdir, generation=generation)
