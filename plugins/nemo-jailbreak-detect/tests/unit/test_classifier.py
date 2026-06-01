# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the decomposed classifier scoring logic (no torch/onnx needed)."""

from __future__ import annotations

import numpy as np
from nemo_jailbreak_detect.model.classifier import JailbreakClassifier


class _FakeEmbed:
    def __call__(self, text: str) -> np.ndarray:
        return np.zeros(4, dtype=np.float32)


class _FakeOnnx:
    """Mimics onnxruntime InferenceSession.run output shape."""

    def __init__(self, label: int, probs: dict[int, float]) -> None:
        self._label = label
        self._probs = probs

    def run(self, _outputs, _inputs):
        class _Scalar:
            def __init__(self, v: int) -> None:
                self._v = v

            def item(self) -> int:
                return self._v

        return [_Scalar(self._label), [self._probs]]


def _make_classifier(label: int, probs: dict[int, float]) -> JailbreakClassifier:
    clf = object.__new__(JailbreakClassifier)
    clf.embed = _FakeEmbed()
    clf.classifier = _FakeOnnx(label, probs)
    return clf


def test_jailbreak_positive_score_is_positive():
    clf = _make_classifier(label=1, probs={0: 0.1, 1: 0.9})
    is_jb, score = clf("do anything now")
    assert is_jb is True
    assert score == 0.9


def test_safe_score_is_negative():
    clf = _make_classifier(label=0, probs={0: 0.8, 1: 0.2})
    is_jb, score = clf("what is the capital of france")
    assert is_jb is False
    # Upstream signed-probability convention: negative when classified safe.
    assert score == -0.8
