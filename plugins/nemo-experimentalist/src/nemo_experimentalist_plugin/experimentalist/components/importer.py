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

    ``ancestor`` is None, which is the only thing that makes the result the baseline.
    """
    return Proposal(ancestor=None, description=description, kind=IMPORT, payload={})


class Importer(Builder):
    """Commit a candidate that is the agent under test, unchanged.

    An ordinary build of an ordinary Proposal, so ``commit_candidate`` stays the only way
    a Candidate is born and a strategy wanting several roots gets that for free. It lands
    on ``agent-0`` without anyone naming it: the first fork takes the first free handle.
    """

    name = "import"
    accepts = frozenset({IMPORT})

    async def build(self, ctx: BuilderContext, proposal: Proposal, *, generation: int = 0) -> Candidate:
        """Fork the agent under test and commit it with nothing changed."""
        fork = await ctx.fork(proposal)
        return await ctx.commit_candidate(proposal=proposal, artifact=fork.workdir, generation=generation)
