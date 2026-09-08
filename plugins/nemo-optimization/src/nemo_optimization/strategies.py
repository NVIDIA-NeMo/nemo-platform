# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discovery contract for non-HPO agent optimization strategies."""

from __future__ import annotations

import importlib.metadata
from functools import cache
from typing import Any, Protocol, runtime_checkable

from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_context import JobContext

OPTIMIZATION_STRATEGIES_GROUP = "nemo.optimization.strategies"
PRIMARY_ARTIFACT_KEY = "_primary_artifact"


class OptimizationStrategyDiscoveryError(RuntimeError):
    """Raised when an optimization strategy plugin cannot be loaded."""


@runtime_checkable
class OptimizationStrategy(Protocol):
    """Plugin contract for a named ``nemo agents optimize`` strategy."""

    name: str

    def validate_config(self, config: dict[str, Any], *, agent: str | None) -> None:
        """Validate strategy configuration before upload or execution."""

    def run(
        self,
        *,
        agent_config: dict[str, Any],
        source_agent_config: dict[str, Any] | None = None,
        config: dict[str, Any],
        ctx: JobContext,
        sdk: NeMoPlatform | None = None,
    ) -> dict[str, Any]:
        """Execute the strategy against a resolved Fabric agent package."""


@cache
def discover_optimization_strategies() -> dict[str, OptimizationStrategy]:
    """Load installed strategy plugins by entry-point name."""
    strategies: dict[str, OptimizationStrategy] = {}
    for entry in importlib.metadata.entry_points(group=OPTIMIZATION_STRATEGIES_GROUP):
        try:
            loaded = entry.load()
            strategy = loaded() if isinstance(loaded, type) else loaded
        except Exception as exc:
            raise OptimizationStrategyDiscoveryError(f"Failed to load optimization strategy {entry.name!r}") from exc
        if not isinstance(strategy, OptimizationStrategy):
            raise OptimizationStrategyDiscoveryError(
                f"Optimization strategy {entry.name!r} must implement OptimizationStrategy"
            )
        if strategy.name != entry.name:
            raise OptimizationStrategyDiscoveryError(
                f"Optimization strategy entry point {entry.name!r} loaded a strategy named {strategy.name!r}"
            )
        strategies[entry.name] = strategy
    return strategies
