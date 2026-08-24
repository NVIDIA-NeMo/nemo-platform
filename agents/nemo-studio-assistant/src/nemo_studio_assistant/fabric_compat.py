# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility fixes for the Fabric Deep Agents runtime bundled in the image."""

import inspect
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def virtualize_skill_sources(skill_paths: Iterable[str], workspace_root: Path) -> list[str]:
    """Convert normalized host skill paths under the workspace to virtual paths."""
    resolved_root = workspace_root.resolve()
    normalized: list[str] = []
    for skill_path in skill_paths:
        path = Path(skill_path)
        if not path.is_absolute():
            normalized.append(skill_path)
            continue
        try:
            relative = path.resolve().relative_to(resolved_root)
        except ValueError:
            normalized.append(skill_path)
            continue
        normalized.append(f"/{relative.as_posix()}")
    return normalized


def apply_deepagents_skill_path_compatibility() -> None:
    """Patch legacy Fabric to honor virtual-mode skill paths under its workspace."""
    from nemo_fabric_adapters.deepagents import adapter as adapter_module

    adapter: Any = adapter_module

    # Fabric 0.2 uses typed runtime/config objects and resolves relative skill
    # paths directly against the workspace. Its adapter no longer needs this
    # payload-based compatibility patch.
    if "base_dir" in inspect.signature(adapter.resolve_backend).parameters:
        return

    common_utils = adapter.common_utils

    original_plan = common_utils.capability_plan
    if not getattr(original_plan, "_nemo_studio_virtual_paths", False):

        def capability_plan(payload: dict[str, Any]) -> dict[str, Any]:
            plan = original_plan(payload)
            native = plan.get("native")
            if not isinstance(native, dict) or not native.get("skill_paths"):
                return plan
            environment = common_utils.environment_payload(payload)
            configured_workspace = Path(str(environment.get("workspace") or "."))
            workspace_root = (
                configured_workspace
                if configured_workspace.is_absolute()
                else Path(common_utils.base_dir(payload)) / configured_workspace
            )
            normalized_native = {
                **native,
                "skill_paths": virtualize_skill_sources(native["skill_paths"], workspace_root),
            }
            return {**plan, "native": normalized_native}

        capability_plan._nemo_studio_virtual_paths = True  # type: ignore[attr-defined]
        common_utils.capability_plan = capability_plan

    original = adapter.resolve_skills
    if getattr(original, "_nemo_studio_virtual_paths", False):
        return

    def resolve_skills(payload: dict[str, Any]) -> list[str] | None:
        skill_paths = original(payload)
        if not skill_paths:
            return None
        environment = adapter.common_utils.environment_payload(payload)
        configured_workspace = Path(str(environment.get("workspace") or "."))
        workspace_root = (
            configured_workspace
            if configured_workspace.is_absolute()
            else Path(adapter.common_utils.base_dir(payload)) / configured_workspace
        )
        return virtualize_skill_sources(skill_paths, workspace_root)

    resolve_skills._nemo_studio_virtual_paths = True  # type: ignore[attr-defined]
    adapter.resolve_skills = resolve_skills
