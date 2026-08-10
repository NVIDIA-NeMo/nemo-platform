# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve the configured optimization strategy."""

from pathlib import Path

from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.experimentalist.registry import get_component
from nemo_experimentalist_plugin.experimentalist.roles import Strategy


def build_experimentalist_agent(
    working_dir: Path,
    config: EvolutionaryOptimizerConfig | None = None,
    framework_skills_dirs: list[Path] | None = None,
) -> Strategy:
    """Resolve ``config.strategy`` by name and construct it.

    Nothing here names a strategy class. Ours is registered and looked up exactly the way
    one from another package is, so pointing ``strategy:`` at a ``pip install``ed
    implementation needs no change in this repository.

    Args:
        working_dir: Local temp directory hydrated from the agent's fileset before the
            run starts. The strategy reads and writes its intermediate artifacts here.
        config: Run configuration. When None the defaults select the evolutionary loop.
        framework_skills_dirs: Directories of framework skills to load into the
            strategy's agents.
        models: The run's resolved model tiers, so the strategy runs on the tiers the
            run record reports rather than re-reading the environment for itself.

    Raises:
        LookupError: if no strategy is registered under ``config.strategy`` — naming one
            that is not installed fails here, before the run spends anything.
    """
    resolved = config or EvolutionaryOptimizerConfig()
    return get_component(
        "strategy",
        resolved.strategy,
        working_dir=working_dir,
        config=resolved,
        framework_skills_dirs=framework_skills_dirs or [],
    )
