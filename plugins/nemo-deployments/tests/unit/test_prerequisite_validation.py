# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_deployments_plugin.validation import PrerequisiteCycleError, detect_prerequisite_cycle


def test_linear_prerequisites_ok() -> None:
    detect_prerequisite_cycle(
        config_name="c",
        prerequisites=["b"],
        existing={"a": [], "b": ["a"]},
    )


def test_self_cycle_rejected() -> None:
    with pytest.raises(PrerequisiteCycleError, match="cycle"):
        detect_prerequisite_cycle(
            config_name="a",
            prerequisites=["a"],
            existing={},
        )


def test_three_node_cycle_rejected() -> None:
    with pytest.raises(PrerequisiteCycleError):
        detect_prerequisite_cycle(
            config_name="a",
            prerequisites=["c"],
            existing={"b": ["a"], "c": ["b"]},
        )
