# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rolling a round back so the loop can re-enter it cleanly."""

from pathlib import Path

import pytest
from doubles import FakeBackend, make_context
from nemo_experimentalist_plugin.entities import Proposal
from nemo_experimentalist_plugin.experimentalist.strategies.evolutionary import EvolutionaryStrategy


async def _commit(ctx, description: str, generation: int):
    """Commit a candidate the way a Builder does."""
    proposal = Proposal(ancestor=None, description=description, kind="import", payload={})
    return await ctx.component("builder", "import").build(ctx, proposal, generation=generation)


@pytest.mark.asyncio
async def test_rollback_discards_later_candidates_and_clears_their_evaluator_scratch(tmp_path: Path) -> None:
    """Which candidates go comes from the stored records, not a directory walk.

    The candidate itself is discarded rather than deleted — the record and artifact both
    survive so a wrong rollback stays recoverable. Evaluator scratch *is* removed, since
    it is keyed by label and the re-run would otherwise read the previous round's results.
    """
    ctx = make_context(root=tmp_path, backend=FakeBackend())
    kept = await _commit(ctx, "from the round we roll back to", generation=1)
    rolled_back = await _commit(ctx, "from the round being discarded", generation=2)

    eo = tmp_path / "eval-and-optimize"
    for sub in ("results", "smoke-results", "smoke-dataset", "analysis"):
        (eo / sub).mkdir(parents=True, exist_ok=True)
    scratch = [
        eo / "results" / f"{rolled_back.label}-validation",
        eo / "smoke-results" / rolled_back.label,
        eo / "smoke-dataset" / rolled_back.label,
    ]
    survivor_scratch = eo / "results" / f"{kept.label}-validation"
    for d in [*scratch, survivor_scratch]:
        d.mkdir(parents=True, exist_ok=True)

    strategy = EvolutionaryStrategy(working_dir=tmp_path)
    await strategy._roll_back_to(ctx=ctx, from_round=1)

    assert [c.id for c in await ctx.candidates()] == [kept.id], "the later candidate is still live"
    discarded = next(c for c in await ctx.candidates(include_discarded=True) if c.id == rolled_back.id)
    assert discarded.discarded is True
    assert ctx.candidate_dir(discarded).exists(), "the artifact must survive a rollback"
    assert not any(d.exists() for d in scratch), "stale evaluator scratch would be read on re-run"
    assert survivor_scratch.exists(), "a survivor's results must not be swept up"
