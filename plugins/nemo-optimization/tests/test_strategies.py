# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from nemo_optimization.strategies import (
    OptimizationStrategyDiscoveryError,
    discover_optimization_strategies,
)


@pytest.fixture(autouse=True)
def clear_strategy_cache():
    discover_optimization_strategies.cache_clear()
    yield
    discover_optimization_strategies.cache_clear()


def test_discovers_a_strategy_plugin() -> None:
    strategy = SimpleNamespace(
        name="prompt-master",
        validate_config=lambda config, agent: None,
        run=lambda **kwargs: {"status": "completed"},
    )
    entry = SimpleNamespace(name="prompt-master", load=lambda: strategy)

    with patch("nemo_optimization.strategies.importlib.metadata.entry_points", return_value=[entry]):
        assert discover_optimization_strategies() == {"prompt-master": strategy}


def test_rejects_a_strategy_whose_name_does_not_match_its_entry_point() -> None:
    strategy = SimpleNamespace(
        name="other",
        validate_config=lambda config, agent: None,
        run=lambda **kwargs: {"status": "completed"},
    )
    entry = SimpleNamespace(name="prompt-master", load=lambda: strategy)

    with (
        patch("nemo_optimization.strategies.importlib.metadata.entry_points", return_value=[entry]),
        pytest.raises(OptimizationStrategyDiscoveryError, match="named 'other'"),
    ):
        discover_optimization_strategies()
