# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pin what `Proposer._filter_improvements` keeps, drops, and refuses.

This used to be `_validate_improvements`, and every problem was fatal: a
repeated ``optimization_type``, one surplus improvement, or one duplicate
description aborted the whole run. A proposal round is expensive and everything
before it is already paid for, so imperfect output is now salvaged and the round
continues with fewer candidates.

Only an empty result is fatal, because there is then nothing to build.
"""

from __future__ import annotations

import logging

import pytest
from nemo_experimentalist_plugin.experimentalist.components.proposer import Improvement, Proposer

ALLOWED = {"edit_concrete_method", "edit_config", "add_concrete_method"}


def _improvement(optimization_type: str, optimization: str, ancestor: str = "agent-0") -> Improvement:
    return Improvement(
        ancestor=ancestor,
        root_cause="the agent underperforms because a handler is missing",
        optimization=optimization,
        optimization_type=optimization_type,
    )


def _filter(improvements: list[Improvement], max_candidates: int = 3) -> list[Improvement]:
    return Proposer._filter_improvements(
        improvements=improvements,
        max_candidates=max_candidates,
        allowed_types=ALLOWED,
    )


def test_repeated_optimization_type_is_kept() -> None:
    """Two candidates may legitimately need the same kind of edit in different places."""
    kept = _filter(
        [
            _improvement("edit_concrete_method", "widen the name pattern"),
            _improvement("edit_concrete_method", "reorder the dispatch chain"),
        ]
    )
    assert len(kept) == 2


def test_every_candidate_may_share_one_type() -> None:
    """The degenerate case: late rounds often have only one kind of work left."""
    kept = _filter(
        [
            _improvement("edit_config", "raise the input limit"),
            _improvement("edit_config", "raise the retry budget"),
            _improvement("edit_config", "raise the timeout"),
        ]
    )
    assert len(kept) == 3


def test_surplus_improvements_are_truncated() -> None:
    """Keeping the first N assumes the Proposer ordered them by priority."""
    kept = _filter(
        [
            _improvement("edit_config", "first"),
            _improvement("edit_concrete_method", "second"),
            _improvement("add_concrete_method", "third"),
        ],
        max_candidates=2,
    )
    assert [i.optimization for i in kept] == ["first", "second"]


def test_type_outside_the_allowed_set_is_dropped() -> None:
    """A valid OptimizationType the caller did not permit for this run.

    `add_subagent` is a real member of the literal -- an invented string is
    rejected by Pydantic at construction and never reaches this filter.
    """
    kept = _filter(
        [
            _improvement("edit_config", "raise the input limit"),
            _improvement("add_subagent", "delegate to a new agent"),
        ]
    )
    assert [i.optimization for i in kept] == ["raise the input limit"]


def test_duplicate_optimization_text_is_dropped() -> None:
    """Identical proposals are genuinely redundant; the first one survives."""
    kept = _filter(
        [
            _improvement("edit_config", "raise the input limit"),
            _improvement("edit_concrete_method", "raise the input limit"),
            _improvement("add_concrete_method", "add a totals handler"),
        ]
    )
    assert [i.optimization for i in kept] == ["raise the input limit", "add a totals handler"]


def test_drops_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Silent degradation would let a consistently bad Proposer look healthy."""
    with caplog.at_level(logging.WARNING):
        _filter(
            [
                _improvement("edit_config", "raise the input limit"),
                _improvement("add_subagent", "delegate to a new agent"),
                _improvement("edit_concrete_method", "raise the input limit"),
            ]
        )
    assert "disallowed optimization_type" in caplog.text
    assert "duplicate optimization text" in caplog.text


def test_empty_input_is_fatal() -> None:
    with pytest.raises(ValueError, match="no improvements"):
        _filter([])


def test_everything_dropped_is_fatal() -> None:
    """Nothing usable means nothing to build, so the round cannot continue."""
    with pytest.raises(ValueError, match="none of them usable"):
        _filter([_improvement("add_subagent", "delegate to a new agent")])
