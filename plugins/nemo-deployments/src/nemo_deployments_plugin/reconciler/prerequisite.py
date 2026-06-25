# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prerequisite DAG evaluation for deployment startup gating."""

from __future__ import annotations

from dataclasses import dataclass

from nemo_deployments_plugin.entities import Deployment, DeploymentConfig, Prerequisite


@dataclass(frozen=True)
class PrerequisiteResult:
    met: bool
    reason: str = ""
    blocking_prerequisite: str | None = None


def _find_prerequisite_deployment(
    prerequisite: Prerequisite,
    deployment: Deployment,
    deployments_by_config: dict[tuple[str, str], Deployment],
    deployments_by_name: dict[tuple[str, str], Deployment],
) -> Deployment | None:
    """Resolve the Deployment entity for a prerequisite DeploymentConfig name."""
    workspace = deployment.workspace
    key_by_config = (workspace, prerequisite.deployment_name)
    target = deployments_by_config.get(key_by_config)
    if target is not None:
        return target
    key_by_name = (workspace, prerequisite.deployment_name)
    target = deployments_by_name.get(key_by_name)
    if target is not None and target.deployment_config == prerequisite.deployment_name:
        return target
    return None


def _condition_met(prerequisite: Prerequisite, target: Deployment) -> bool:
    if prerequisite.condition == "ready":
        return target.status == "READY"
    return target.status == "SUCCEEDED" and target.exit_code == 0


def prerequisites_met(
    deployment: Deployment,
    config: DeploymentConfig,
    *,
    deployments_by_config: dict[tuple[str, str], Deployment],
    deployments_by_name: dict[tuple[str, str], Deployment],
) -> PrerequisiteResult:
    """Evaluate DeploymentConfig.prerequisites against current deployment states."""
    if not config.prerequisites:
        return PrerequisiteResult(met=True)

    for prerequisite in config.prerequisites:
        target = _find_prerequisite_deployment(
            prerequisite,
            deployment,
            deployments_by_config,
            deployments_by_name,
        )
        if target is None:
            return PrerequisiteResult(
                met=False,
                reason=f"Waiting for prerequisite deployment '{prerequisite.deployment_name}'",
                blocking_prerequisite=prerequisite.deployment_name,
            )
        if target.status == "FAILED":
            return PrerequisiteResult(
                met=False,
                reason=f"Prerequisite '{prerequisite.deployment_name}' failed",
                blocking_prerequisite=prerequisite.deployment_name,
            )
        if not _condition_met(prerequisite, target):
            return PrerequisiteResult(
                met=False,
                reason=f"Waiting for prerequisite '{prerequisite.deployment_name}' ({prerequisite.condition})",
                blocking_prerequisite=prerequisite.deployment_name,
            )

    return PrerequisiteResult(met=True)
