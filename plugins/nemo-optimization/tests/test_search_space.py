# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_optimization.backends.optuna.search_space import (
    SearchSpaceError,
    SearchSpaceSpec,
    grid_trial_count,
    parse_search_space,
)


class _FakeTrial:
    def suggest_categorical(self, name: str, choices):  # noqa: ANN001
        return choices[0]

    def suggest_int(self, name, low, high, *, log=False, step=None):  # noqa: ANN001
        return low

    def suggest_float(self, name, low, high, *, log=False, step=None):  # noqa: ANN001
        return low


def test_categorical_suggest() -> None:
    spec = SearchSpaceSpec.from_mapping({"values": [0.7, 0.85, 1.0]})
    assert spec.suggest(_FakeTrial(), "models.default.top_p") == 0.7


def test_float_range_suggest() -> None:
    spec = SearchSpaceSpec.from_mapping({"low": 0.0, "high": 0.8, "step": 0.2})
    assert spec.suggest(_FakeTrial(), "models.default.temperature") == 0.0


def test_grid_values_from_explicit_values() -> None:
    spec = SearchSpaceSpec.from_mapping({"values": [0.7, 0.85, 1.0]})
    assert spec.to_grid_values() == [0.7, 0.85, 1.0]


def test_grid_values_from_int_range() -> None:
    spec = SearchSpaceSpec.from_mapping({"low": 0, "high": 10, "step": 2})
    assert spec.to_grid_values() == [0, 2, 4, 6, 8, 10]


def test_grid_values_from_float_range_includes_high() -> None:
    spec = SearchSpaceSpec.from_mapping({"low": 0.0, "high": 0.8, "step": 0.2})
    assert spec.to_grid_values() == [0.0, 0.2, 0.4, 0.6, 0.8]


def test_grid_requires_step_for_range() -> None:
    spec = SearchSpaceSpec.from_mapping({"low": 0.0, "high": 0.8})
    with pytest.raises(SearchSpaceError, match="requires 'step'"):
        spec.to_grid_values()


def test_parse_search_space_rejects_prompt_entries() -> None:
    with pytest.raises(SearchSpaceError, match="prompt-only"):
        parse_search_space({"search_space": {"prompt": {"is_prompt": True}}})


def test_grid_trial_count_is_cartesian_product() -> None:
    space = parse_search_space(
        {
            "search_space": {
                "models.default.temperature": {"low": 0.0, "high": 0.4, "step": 0.2},
                "models.default.top_p": {"values": [0.7, 0.85, 1.0]},
            }
        }
    )
    assert grid_trial_count(space) == 3 * 3
