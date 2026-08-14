# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Survivors chosen by the selector must resolve back to the live population.

The selector is handed `slim()` copies so per-trial detail never reaches a model
prompt, and the loop then looks the real records back up: carrying a slim copy forward
would erase every other channel's trials the next time one is persisted.

What that lookup is keyed on decides whether the run survives a generated method.
`survivors` can answer either by passing the objects or by re-specifying them as JSON,
and a candidate's id is a computed property over a private attribute -- not a model
field -- so the JSON route cannot carry it and validation mints a fresh one. `label` is
an ordinary field, unique within a run, and survives both routes.

Keyed on id, a JSON answer resolves to nothing. The loop cannot distinguish that from
"the selector chose to keep nothing", so it kills the entire population; every proposal
is then rejected for naming an ancestor outside an empty survivor set, and a run holding
a candidate that had already scored 1.000 ends with no winner. Seen on a real run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from doubles import FakeBackend, make_context
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.entities import Candidate, Proposal
from nemo_experimentalist_plugin.experimentalist.strategies.evolutionary import EvolutionaryStrategy


def _forget_identity(candidate: Candidate) -> Candidate:
    """A candidate as it comes back from a JSON answer: same values, new id."""
    return Candidate.model_validate(json.loads(candidate.model_dump_json(exclude={"id"})))


class _SelectorReturningJson:
    """A selector whose answer crossed the tool-call boundary."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def rank(self, candidates: list[Candidate]) -> list[Candidate]:
        return list(candidates)

    async def survivors(self, candidates: list[Candidate], *, k: int) -> list[Candidate]:
        self.seen = [c.label for c in candidates]
        return [_forget_identity(c) for c in candidates[:k]]

    def winner(self, candidates: list[Candidate]) -> Candidate | None:
        return candidates[0] if candidates else None


async def _two_candidates(*, ctx: Any, config: Any) -> None:
    """Two candidates, because the loop only consults the selector when it has a choice.

    With a single candidate it short-circuits to `list(candidates)` and the resolution
    under test never runs -- which is how a first version of this test passed against
    the very code it was written to catch.
    """
    builder = ctx.component("builder", "import")
    for index in range(2):
        proposal = Proposal(ancestor=None, description=f"candidate {index}", kind="import", payload={})
        await builder.build(ctx, proposal, generation=0)


@pytest.mark.asyncio
async def test_a_survivor_that_lost_its_id_still_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression: keyed on id, this killed the population and lost the run."""
    config = EvolutionaryOptimizerConfig(
        max_rounds=1, max_survivors=1, terminator=None, analyzer=None, trajectory_scorer=None
    )
    loop = EvolutionaryStrategy(working_dir=tmp_path, config=config)
    ctx = make_context(root=tmp_path, backend=FakeBackend())
    selector = _SelectorReturningJson()

    async def _no_evaluations(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {}

    async def _no_analysis(*_a: Any, **_k: Any) -> str:
        return ""

    async def _nothing(*_a: Any, **_k: Any) -> None:
        return None

    async def _no_proposals(*_a: Any, **_k: Any) -> list[Proposal]:
        return []

    monkeypatch.setattr(loop, "_ensure_baseline", _two_candidates)
    monkeypatch.setattr(loop, "_selector", lambda *_a, **_k: selector)
    monkeypatch.setattr(loop, "_evaluate_validation_candidates", _no_evaluations)
    monkeypatch.setattr(loop, "_evaluate_train_candidates", _no_evaluations)
    monkeypatch.setattr(loop, "_record_baseline_validation", _nothing)
    monkeypatch.setattr(loop, "_analyze_round", _no_analysis)
    monkeypatch.setattr(loop, "_propose_improvements", _no_proposals)

    await loop._run(ctx)

    survived = [c for c in await ctx.candidates() if c.killed_generation is None]
    assert survived, (
        "every candidate was killed: the selector's answer did not resolve back to the "
        "population, and 'resolved to nothing' was treated as 'keep nothing'"
    )


def test_the_label_is_what_survives_a_json_answer() -> None:
    """The property the resolution key relies on, pinned directly.

    If a future change makes `id` serialize, this stops being load-bearing -- but until
    then, a lookup keyed on id is keyed on the one thing the boundary drops.
    """
    from doubles import make_candidate

    original = make_candidate(label="agent-1", generation=1)
    returned = _forget_identity(original)

    assert returned.label == original.label, "label is a model field and must survive"
    assert returned.id != original.id, "id is not a model field and cannot survive"
