# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prerequisite graph validation for Deployment entities."""

from __future__ import annotations

from collections import defaultdict

from nemo_deployments_plugin.entities import Deployment, Prerequisite
from nemo_deployments_plugin.reconciler.prerequisite import parse_deployment_ref


class PrerequisiteCycleError(ValueError):
    """Raised when deployment prerequisites contain a cycle."""


def detect_prerequisite_cycle(
    *,
    deployment_name: str,
    prerequisites: list[str],
    existing: dict[str, list[str]],
) -> None:
    """Detect cycles in the prerequisite graph within a workspace."""
    graph: dict[str, list[str]] = {name: list(deps) for name, deps in existing.items()}
    graph[deployment_name] = list(prerequisites)

    visited: set[str] = set()
    stack: set[str] = set()

    def dfs(node: str) -> None:
        if node in stack:
            raise PrerequisiteCycleError(f"Prerequisite cycle detected involving deployment '{node}'.")
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        stack.remove(node)

    for node in graph:
        dfs(node)


def deployment_graph_key(workspace: str, name: str) -> str:
    """Return a stable graph node id for a deployment in prerequisite cycle detection."""
    return f"{workspace}/{name}"


def normalized_prerequisite_name(ref: str, workspace: str) -> str:
    """Return a graph node name for prerequisite cycle detection."""
    ref_workspace, name = parse_deployment_ref(ref, workspace)
    return deployment_graph_key(ref_workspace, name)


def prerequisite_names(prerequisites: list[Prerequisite], workspace: str) -> list[str]:
    return [normalized_prerequisite_name(prerequisite.deployment_name, workspace) for prerequisite in prerequisites]


def build_existing_prerequisite_map(deployments: list[Deployment]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = defaultdict(list)
    for deployment in deployments:
        key = deployment_graph_key(deployment.workspace, deployment.name)
        graph[key] = prerequisite_names(deployment.prerequisites, deployment.workspace)
    return dict(graph)
