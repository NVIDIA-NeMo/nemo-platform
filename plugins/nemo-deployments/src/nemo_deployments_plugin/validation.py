# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prerequisite graph validation for DeploymentConfig entities."""

from __future__ import annotations

from collections import defaultdict

from nemo_deployments_plugin.entities import DeploymentConfig, Prerequisite


class PrerequisiteCycleError(ValueError):
    """Raised when deployment prerequisites contain a cycle."""


def detect_prerequisite_cycle(
    *,
    config_name: str,
    prerequisites: list[str],
    existing: dict[str, list[str]],
) -> None:
    """Detect cycles in the prerequisite graph within a workspace."""
    graph: dict[str, list[str]] = {name: list(deps) for name, deps in existing.items()}
    graph[config_name] = list(prerequisites)

    visited: set[str] = set()
    stack: set[str] = set()

    def dfs(node: str) -> None:
        if node in stack:
            raise PrerequisiteCycleError(f"Prerequisite cycle detected involving deployment config '{node}'.")
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        stack.remove(node)

    for node in graph:
        dfs(node)


def prerequisite_names(prerequisites: list[Prerequisite]) -> list[str]:
    return [prerequisite.deployment_name for prerequisite in prerequisites]


def build_existing_prerequisite_map(configs: list[DeploymentConfig]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = defaultdict(list)
    for cfg in configs:
        graph[cfg.name] = prerequisite_names(cfg.prerequisites)
    return dict(graph)
