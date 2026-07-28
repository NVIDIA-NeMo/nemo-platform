# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experimentalist agent factory."""

from pathlib import Path

from nemo_experimentalist_plugin.experimentalist.components.loop import (
    EvolutionaryOptimizer,
    EvolutionaryOptimizerConfig,
)


def build_experimentalist_agent(
    working_dir: Path,
    config: EvolutionaryOptimizerConfig | None = None,
    framework_skills_dirs: list[Path] | None = None,
) -> EvolutionaryOptimizer:
    """Build and return a configured :class:`EvolutionaryOptimizer`.

    Args:
        working_dir: Local temp directory hydrated from the agent's fileset
            before the run starts. The optimizer reads/writes all intermediate
            artifacts here.
        config: Optional optimizer config. When None the optimizer uses its
            built-in defaults.
        framework_skills_dirs: Optional list of directories containing framework
            skills to load into all optimizer agents.
    """
    return EvolutionaryOptimizer(
        working_dir=working_dir, config=config, framework_skills_dirs=framework_skills_dirs or []
    )
