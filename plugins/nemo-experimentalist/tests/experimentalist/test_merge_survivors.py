# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Behaviour that arrived from `main` and has no other test on this branch.

This lived in `components/loop.py`, which this refactor deletes, so merging
main dropped them silently: the suite stayed green because nothing here asserted them.
A per-commit audit of the merge is what found them. It is pinned here so the next merge
cannot repeat it. The other loss that audit found -- `allow_empty` for insight runs --
is pinned in `test_dataset_staging_runner.py`, where the staging doubles already live.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from doubles import FakeBackend, make_context
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.entities import Proposal
from nemo_experimentalist_plugin.experimentalist.strategies.evolutionary import EvolutionaryStrategy


@pytest.mark.asyncio
async def test_a_round_with_no_proposals_finalizes_instead_of_buying_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty proposal list means the round produced nothing to build.

    Continuing re-analyzes the same population and pays for it again, so the loop stops
    and finalizes on what it has. Without this the run spends its whole round budget
    producing nothing, which looks like a slow run rather than a stuck one.
    """
    config = EvolutionaryOptimizerConfig(max_rounds=5, terminator=None, analyzer=None, trajectory_scorer=None)
    loop = EvolutionaryStrategy(working_dir=tmp_path, config=config)
    ctx = make_context(root=tmp_path, backend=FakeBackend())
    rounds = 0

    async def _no_proposals(*_a: Any, **_k: Any) -> list[Proposal]:
        nonlocal rounds
        rounds += 1
        return []

    async def _baseline(*, ctx: Any, config: Any) -> None:
        proposal = Proposal(ancestor=None, description="baseline", kind="import", payload={})
        await ctx.component("builder", "import").build(ctx, proposal, generation=0)

    async def _none(*_a: Any, **_k: Any) -> Any:
        return {}

    async def _nothing(*_a: Any, **_k: Any) -> None:
        return None

    async def _no_analysis(*_a: Any, **_k: Any) -> str:
        return ""

    monkeypatch.setattr(loop, "_ensure_baseline", _baseline)
    monkeypatch.setattr(loop, "_propose_improvements", _no_proposals)
    monkeypatch.setattr(loop, "_evaluate_validation_candidates", _none)
    monkeypatch.setattr(loop, "_evaluate_train_candidates", _none)
    monkeypatch.setattr(loop, "_record_baseline_validation", _nothing)
    monkeypatch.setattr(loop, "_analyze_round", _no_analysis)

    await loop._run(ctx)

    assert rounds == 1, f"proposed {rounds} times; an empty proposal list must end the loop"
