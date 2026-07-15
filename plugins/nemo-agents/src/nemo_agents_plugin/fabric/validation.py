# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plan and preflight validation helpers for Fabric-backed agents."""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FABRIC_VALIDATION_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class FabricValidationResult:
    """Result of Fabric planning and preflight validation."""

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


async def validate_fabric_config(
    fabric_config: Any,
    *,
    base_dir: Path | str,
    fabric: Any | None = None,
) -> FabricValidationResult:
    """Run Fabric plan and doctor for a translated FabricConfig.

    This validates the selected harness and environment without invoking the
    agent. The Fabric SDK import is intentionally local so NAT-backed paths do
    not require Fabric to be installed.
    """

    Fabric, FabricConfigError = _fabric_validation_types()
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


def _fabric_validation_types() -> tuple[type, type[Exception]]:
    # TODO(AIRCORE-896): Keep this import lazy until Fabric SDK/runtime wheels
    # are available to the repo resolver and can be added as plugin dependencies.
    try:
        nemo_fabric = importlib.import_module("nemo_fabric")
    except ImportError as error:
        raise FabricValidationError("NeMo Fabric SDK is required to plan and preflight FabricConfig.") from error

    return getattr(nemo_fabric, "Fabric"), getattr(nemo_fabric, "FabricConfigError")


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
