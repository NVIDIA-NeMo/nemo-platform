# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sub-entity (``#fragment``) reference parsing and validation.

A revision is addressed with the platform's standard ``#`` fragment — the same convention filesets
use for a contained file (``workspace/fileset#path``). These tests pin two things: that an absent
fragment means ``latest`` rather than "unpinned", and that existing fragment-unaware callers keep
working against a pinned ref (``parse_entity_ref`` strips it).
"""

from __future__ import annotations

import pytest
from nemo_evaluator.api.schemas import (
    LATEST_TAG,
    MetricRef,
    TaskRef,
    TasksetRef,
    parse_entity_ref,
    parse_subentity_ref,
)
from pydantic import ValidationError

_DIGEST = "a" * 64


# --- Parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("task-a", ("default", "task-a", LATEST_TAG)),
        ("other/task-a", ("other", "task-a", LATEST_TAG)),
        ("task-a#latest", ("default", "task-a", "latest")),
        ("other/task-a#candidate", ("other", "task-a", "candidate")),
        (f"other/task-a#{_DIGEST}", ("other", "task-a", _DIGEST)),
    ],
)
def test_parse_subentity_ref(ref: str, expected: tuple[str, str, str]) -> None:
    assert parse_subentity_ref(ref, "default") == expected


def test_absent_fragment_means_latest_not_unpinned() -> None:
    """A bare ref is "the current revision", which is what makes `#latest` a real default rather
    than a special case the resolver has to guess at."""
    _, _, fragment = parse_subentity_ref("task-a", "default")
    assert fragment == LATEST_TAG


def test_empty_fragment_falls_back_to_latest() -> None:
    """``task-a#`` is degenerate input; treat it as unpinned rather than as a tag named ''."""
    assert parse_subentity_ref("task-a#", "default") == ("default", "task-a", LATEST_TAG)


def test_fragment_is_returned_verbatim() -> None:
    """Parsing does not decide whether a fragment is a tag or a digest — that's resolution's job."""
    _, _, fragment = parse_subentity_ref(f"task-a#{_DIGEST}", "default")
    assert fragment == _DIGEST


# --- Backward compatibility --------------------------------------------------


def test_parse_entity_ref_strips_the_fragment() -> None:
    """Fragment-unaware callers (metric resolution, taskset member existence checks) keep working
    against a pinned ref instead of trying to look up a task literally named 'task-a#<digest>'."""
    assert parse_entity_ref(f"other/task-a#{_DIGEST}", "default") == ("other", "task-a")
    assert parse_entity_ref("task-a#latest", "default") == ("default", "task-a")


def test_pinned_and_bare_refs_resolve_to_the_same_task() -> None:
    """The property taskset duplicate-detection relies on: two refs differing only by fragment are
    the same member, and must not both be admitted."""
    assert parse_entity_ref(f"task-a#{_DIGEST}", "default") == parse_entity_ref("task-a", "default")


# --- Field validation --------------------------------------------------------


@pytest.mark.parametrize("ref", ["task-a", "other/task-a", "task-a#latest", f"other/task-a#{_DIGEST}"])
def test_task_ref_accepts_fragments(ref: str) -> None:
    assert TaskRef(ref).root == ref


@pytest.mark.parametrize("ref", ["task-a#one#two", "task-a#bad/frag", "#latest", "task a#latest"])
def test_task_ref_rejects_malformed_fragments(ref: str) -> None:
    with pytest.raises(ValidationError):
        TaskRef(ref)


@pytest.mark.parametrize("ref_type", [MetricRef, TasksetRef])
def test_sibling_ref_types_still_reject_fragments(ref_type: type) -> None:
    """The fragment pattern is a sibling, not a widening of the shared constant: metrics and
    tasksets have no revisions yet, so admitting a fragment would accept input nothing resolves.
    They move onto it when they gain revisions — deliberately, at that point."""
    with pytest.raises(ValidationError):
        ref_type(f"other/thing#{_DIGEST}")
