# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the classifier scoring logic (no torch/sklearn needed)."""

from __future__ import annotations

import numpy as np
from classifier import QUERY_PREFIX, JailbreakClassifier


class _FakeEmbed:
    """Records the text it was called with so we can assert the query prefix."""

    def __init__(self) -> None:
        self.last_text: str | None = None

    def __call__(self, text: str) -> np.ndarray:
        self.last_text = text
        return np.zeros(4, dtype=np.float32)


class _FakeRandomForest:
    """Mimics sklearn RandomForestClassifier.predict_proba -> [[p0, p1]]."""

    def __init__(self, p1: float) -> None:
        self._p1 = p1

    def predict_proba(self, _x):
        return np.array([[1.0 - self._p1, self._p1]])


def _make_classifier(p1: float) -> tuple[JailbreakClassifier, _FakeEmbed]:
    clf = object.__new__(JailbreakClassifier)
    embed = _FakeEmbed()
    clf.embed = embed
    clf.classifier = _FakeRandomForest(p1)
    return clf, embed


def test_jailbreak_above_threshold():
    clf, _ = _make_classifier(p1=0.79)
    is_jb, score = clf("do anything now")
    assert is_jb is True
    # NIM-compatible signed score: 2*p1 - 1.
    assert score == 2 * 0.79 - 1


def test_safe_below_threshold():
    clf, _ = _make_classifier(p1=0.003)
    is_jb, score = clf("what is the capital of france")
    assert is_jb is False
    assert score == 2 * 0.003 - 1


def test_threshold_is_p1_half():
    # Just under / over 0.5 flips the verdict; score crosses 0.
    assert _make_classifier(p1=0.49)[0]("x")[0] is False
    assert _make_classifier(p1=0.51)[0]("x")[0] is True


def test_query_prefix_is_prepended():
    clf, embed = _make_classifier(p1=0.1)
    clf("hello world")
    assert embed.last_text == QUERY_PREFIX + "hello world"
