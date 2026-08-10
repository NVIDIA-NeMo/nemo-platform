# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pin the parts of the scorer's contract that a turn-less trace depends on.

`GroupLeafScorer.score_group` is a CodeAct prompt, so its docstring is the instruction the
model follows. The only sanctioned evidence lookups are indexed by turn, so a trace
with zero turns needs the contract to name that case, permit an empty `span_ids`,
and point at evidence the scorer can actually reach. These tests keep that escape
hatch present and keep the schema able to represent it.
"""

from __future__ import annotations

import inspect

from nemo_experimentalist_plugin.experimentalist.components.trace_scorer import (
    GroupLeafScore,
    GroupLeafScorer,
)


def _run_contract() -> str:
    """The prompt with whitespace collapsed, so assertions do not hinge on where it wraps."""
    doc = inspect.getdoc(GroupLeafScorer.score_group)
    assert doc is not None, "GroupLeafScorer.score_group must keep its docstring; it is the prompt"
    return " ".join(doc.lower().split())


def test_contract_tells_the_scorer_what_to_do_with_no_turns() -> None:
    """Without this, the only permitted evidence source is unreachable and the run dies."""
    contract = _run_contract()
    assert "turns: 0" in contract, "the contract must name the condition the scorer can observe"
    assert "no turns" in contract
    assert "leave `span_ids` empty" in contract, "the contract must say what to return instead"


def test_contract_offers_an_alternative_grounding() -> None:
    """Permission to return nothing is not enough; the reason must still be evidence-backed."""
    contract = _run_contract()
    assert "call graph" in contract, "a turn-less trace still carries a call graph to cite"
    for required in ("methods that ran", "order they ran in", "status"):
        assert required in contract, f"the contract must name {required!r} as evidence to cite"


def test_contract_still_forbids_inventing_span_ids() -> None:
    """Relaxing the requirement must not license guessed or abbreviated IDs."""
    contract = _run_contract()
    for forbidden in ("never abbreviated, guessed", "do not put the abbreviated ids"):
        assert forbidden in contract, f"the contract must still refuse {forbidden!r}"


def test_score_is_valid_without_span_ids() -> None:
    """The schema has to accept what the contract now asks for in the turn-less case."""
    score = GroupLeafScore(score=0.6, reason="handle_lookup ran and returned OK; solve dispatched to it")
    assert score.span_ids == []


def test_score_still_accepts_span_ids() -> None:
    """The turn-less path must not become the only path."""
    score = GroupLeafScore(score=0.9, reason="cited", span_ids=["abc123"])
    assert score.span_ids == ["abc123"]
