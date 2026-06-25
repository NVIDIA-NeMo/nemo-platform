# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prerequisite DAG evaluation for deployment startup gating."""

from __future__ import annotations

from dataclasses import dataclass

from nemo_deployments_plugin.entities import Deployment, Prerequisite


@dataclass(frozen=True)
class PrerequisiteResult:
    met: bool
    reason: str = ""
    blocking_prerequisite: str | None = None
    blocking_workspace: str | None = None
    blocking_name: str | None = None


def parse_deployment_ref(ref: str, default_workspace: str) -> tuple[str, str]:
    """Return (workspace, deployment_name) from a bare name or workspace/name ref."""
    if "/" in ref:
        workspace, name = ref.split("/", 1)
        if not workspace or not name:
            raise ValueError(f"Invalid deployment ref '{ref}'; expected 'name' or 'workspace/name'.")
        return workspace, name
    return default_workspace, ref


def _condition_met(prerequisite: Prerequisite, target: Deployment) -> bool:
    if prerequisite.condition == "ready":
        return target.status == "READY"
    return target.status == "SUCCEEDED" and target.exit_code == 0


def prerequisites_met(
    deployment: Deployment,
    *,
    deployments_by_name: dict[tuple[str, str], Deployment],
) -> PrerequisiteResult:
    """Evaluate Deployment.prerequisites against current deployment states."""
    if not deployment.prerequisites:
        return PrerequisiteResult(met=True)

    for prerequisite in deployment.prerequisites:
        try:
            workspace, name = parse_deployment_ref(prerequisite.deployment_name, deployment.workspace)
        except ValueError:
            return PrerequisiteResult(
                met=False,
                reason=f"Invalid prerequisite ref '{prerequisite.deployment_name}'",
                blocking_prerequisite=prerequisite.deployment_name,
            )
        target = deployments_by_name.get((workspace, name))
        if target is None:
            return PrerequisiteResult(
                met=False,
                reason=f"Waiting for prerequisite deployment '{prerequisite.deployment_name}'",
                blocking_prerequisite=prerequisite.deployment_name,
                blocking_workspace=workspace,
                blocking_name=name,
            )
        if target.status == "FAILED":
            return PrerequisiteResult(
                met=False,
                reason=f"Prerequisite '{prerequisite.deployment_name}' failed",
                blocking_prerequisite=prerequisite.deployment_name,
                blocking_workspace=workspace,
                blocking_name=name,
            )
        if not _condition_met(prerequisite, target):
            return PrerequisiteResult(
                met=False,
                reason=f"Waiting for prerequisite '{prerequisite.deployment_name}' ({prerequisite.condition})",
                blocking_prerequisite=prerequisite.deployment_name,
                blocking_workspace=workspace,
                blocking_name=name,
            )

    return PrerequisiteResult(met=True)
