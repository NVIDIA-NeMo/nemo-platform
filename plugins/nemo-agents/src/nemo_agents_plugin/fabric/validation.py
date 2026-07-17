# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plan and preflight validation helpers for Fabric-backed agents."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.translator import FabricTranslationError, translate_agent_config
from nemo_fabric import Fabric, FabricConfigError
from pydantic import ValidationError

FABRIC_VALIDATION_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class FabricValidationResult:
    """Result of Fabric planning and preflight validation."""

    plan: Any
    doctor_report: Any


@dataclass(frozen=True, slots=True)
class PlatformFabricValidationResult:
    """Result of Platform config translation and Fabric validation."""

    agent_config: AgentConfig
    fabric_config: Any
    plan: Any
    doctor_report: Any


class FabricValidationError(ValueError):
    """Raised when Fabric planning or preflight validation fails."""


class FabricPreflightError(FabricValidationError):
    """Raised when Fabric doctor reports a non-passing preflight status."""

    def __init__(self, status: str | None, failed_checks: list[str]) -> None:
        self.status = status
        self.failed_checks = failed_checks
        details = "; ".join(failed_checks)
        super().__init__(f"Fabric preflight failed with status {status!r}: {details}")


async def validate_platform_agent_config(
    config: AgentConfig | Mapping[str, Any],
    *,
    base_dir: Path | str,
    harness_name: str | None = None,
    fabric: Any | None = None,
) -> PlatformFabricValidationResult:
    """Translate and validate a Platform-owned agent config with Fabric."""

    agent_config = _coerce_agent_config(config)
    try:
        fabric_config = translate_agent_config(agent_config, harness_name=harness_name)
    except FabricTranslationError as error:
        raise FabricValidationError(f"Fabric config translation failed: {error}") from error

    validation_result = await validate_fabric_config(fabric_config, base_dir=base_dir, fabric=fabric)
    return PlatformFabricValidationResult(
        agent_config=agent_config,
        fabric_config=fabric_config,
        plan=validation_result.plan,
        doctor_report=validation_result.doctor_report,
    )


async def validate_fabric_config(
    fabric_config: Any,
    *,
    base_dir: Path | str,
    fabric: Any | None = None,
) -> FabricValidationResult:
    """Run Fabric plan and doctor for a translated FabricConfig.

    This validates the selected harness and environment without invoking the
    agent. Fabric is a required dependency of the ``nemo-agents`` plugin.
    """

    fabric_client = fabric or Fabric()

    try:
        plan = await asyncio.to_thread(fabric_client.plan, fabric_config, base_dir=base_dir)
    except FabricConfigError as error:
        raise FabricValidationError(f"Fabric plan failed: {error}") from error

    try:
        doctor_report = await asyncio.wait_for(
            fabric_client.doctor(fabric_config, base_dir=base_dir),
            timeout=FABRIC_VALIDATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as error:
        raise FabricValidationError(f"Fabric doctor timed out after {FABRIC_VALIDATION_TIMEOUT_SECONDS:g}s.") from error
    except Exception as error:
        raise FabricValidationError(f"Fabric doctor failed: {error}") from error

    _ensure_doctor_passed(_to_mapping(doctor_report))
    return FabricValidationResult(plan=plan, doctor_report=doctor_report)


def _coerce_agent_config(config: AgentConfig | Mapping[str, Any]) -> AgentConfig:
    if isinstance(config, AgentConfig):
        return config

    try:
        return AgentConfig.model_validate(config)
    except ValidationError as error:
        raise FabricValidationError(f"Invalid Platform agent config: {error}") from error


def _ensure_doctor_passed(report: dict[str, Any]) -> None:
    status = report.get("status")
    if status == "pass":
        return

    failed_checks: list[str] = []
    for check in report.get("checks", []):
        check_status = check.get("status")
        if check_status == "pass":
            continue

        name = check.get("name", "unknown")
        message = check.get("message", "No diagnostic message provided.")
        failed_checks.append(f"{name}: {check_status} - {message}")

    if not failed_checks:
        failed_checks.append("No failing subsection was reported.")

    raise FabricPreflightError(status, failed_checks)


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_mapping"):
        mapping = value.to_mapping()
        if isinstance(mapping, dict):
            return mapping
    if hasattr(value, "model_dump"):
        mapping = value.model_dump(mode="json")
        if isinstance(mapping, dict):
            return mapping
    raise FabricValidationError("Fabric doctor returned a report that could not be converted to a mapping.")
