# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Fabric plan and preflight validation helpers."""

from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import types
from pathlib import Path
from typing import Any

import nemo_agents_plugin.fabric.validation as validation
import pytest
from nemo_agents_plugin.fabric.validation import (
    FabricPreflightError,
    FabricValidationError,
    validate_fabric_config,
)


class _FakeFabricConfigError(Exception):
    pass


class _FakeDoctorReport:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping

    def to_mapping(self) -> dict[str, Any]:
        return self._mapping


class _FakeFabric:
    def __init__(
        self,
        *,
        plan: Any = "plan",
        doctor_report: Any | None = None,
        plan_error: Exception | None = None,
        doctor_error: Exception | None = None,
        doctor_delay: float = 0.0,
    ) -> None:
        self.plan_result = plan
        self.doctor_report = (
            doctor_report if doctor_report is not None else _FakeDoctorReport({"status": "pass", "checks": []})
        )
        self.plan_error = plan_error
        self.doctor_error = doctor_error
        self.doctor_delay = doctor_delay
        self.plan_calls: list[dict[str, Any]] = []
        self.plan_thread_ids: list[int] = []
        self.doctor_calls: list[dict[str, Any]] = []

    def plan(self, fabric_config: Any, *, base_dir: Path | str) -> Any:
        self.plan_calls.append({"fabric_config": fabric_config, "base_dir": base_dir})
        self.plan_thread_ids.append(threading.get_ident())
        if self.plan_error is not None:
            raise self.plan_error
        return self.plan_result

    async def doctor(self, fabric_config: Any, *, base_dir: Path | str) -> Any:
        self.doctor_calls.append({"fabric_config": fabric_config, "base_dir": base_dir})
        if self.doctor_delay:
            await asyncio.sleep(self.doctor_delay)
        if self.doctor_error is not None:
            raise self.doctor_error
        return self.doctor_report


@pytest.fixture()
def fake_nemo_fabric(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("nemo_fabric")
    setattr(module, "Fabric", _FakeFabric)
    setattr(module, "FabricConfigError", _FakeFabricConfigError)
    monkeypatch.setitem(sys.modules, "nemo_fabric", module)


@pytest.mark.asyncio
class TestValidateFabricConfig:
    async def test_returns_plan_and_doctor_report(self, fake_nemo_fabric: None) -> None:
        fabric_config = object()
        doctor_report = _FakeDoctorReport({"status": "pass", "checks": [{"name": "adapter", "status": "pass"}]})
        fabric = _FakeFabric(plan={"plan": "ok"}, doctor_report=doctor_report)

        result = await validate_fabric_config(fabric_config, base_dir=Path("/tmp/agent"), fabric=fabric)

        assert result.plan == {"plan": "ok"}
        assert result.doctor_report is doctor_report
        assert fabric.plan_calls == [{"fabric_config": fabric_config, "base_dir": Path("/tmp/agent")}]
        assert fabric.doctor_calls == [{"fabric_config": fabric_config, "base_dir": Path("/tmp/agent")}]

    async def test_runs_plan_off_event_loop_thread(self, fake_nemo_fabric: None) -> None:
        main_thread_id = threading.get_ident()
        fabric = _FakeFabric()

        await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=fabric)

        assert fabric.plan_thread_ids
        assert fabric.plan_thread_ids[0] != main_thread_id

    async def test_wraps_plan_errors(self, fake_nemo_fabric: None) -> None:
        fabric = _FakeFabric(plan_error=_FakeFabricConfigError("bad config"))

        with pytest.raises(FabricValidationError, match="Fabric plan failed: bad config"):
            await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=fabric)

    async def test_wraps_doctor_errors(self, fake_nemo_fabric: None) -> None:
        fabric = _FakeFabric(doctor_error=RuntimeError("doctor exploded"))

        with pytest.raises(FabricValidationError, match="Fabric doctor failed: doctor exploded"):
            await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=fabric)

    async def test_wraps_doctor_timeout(self, fake_nemo_fabric: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(validation, "FABRIC_VALIDATION_TIMEOUT_SECONDS", 0.01)
        fabric = _FakeFabric(doctor_delay=1.0)

        with pytest.raises(FabricValidationError, match="Fabric doctor timed out after 0.01s"):
            await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=fabric)

    async def test_preflight_failure_reports_failed_checks(self, fake_nemo_fabric: None) -> None:
        doctor_report = _FakeDoctorReport(
            {
                "status": "fail",
                "checks": [
                    {"name": "adapter_descriptor", "status": "pass", "message": "ok"},
                    {"name": "requirement.binary", "status": "fail", "message": "binary `codex` missing"},
                    {"name": "environment", "status": "warn", "message": "workspace missing"},
                ],
            }
        )
        fabric = _FakeFabric(doctor_report=doctor_report)

        with pytest.raises(FabricPreflightError) as error_info:
            await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=fabric)

        assert error_info.value.status == "fail"
        assert error_info.value.failed_checks == [
            "requirement.binary: fail - binary `codex` missing",
            "environment: warn - workspace missing",
        ]

    async def test_preflight_failure_without_checks_reports_fallback(self, fake_nemo_fabric: None) -> None:
        doctor_report = _FakeDoctorReport({"status": "fail", "checks": []})
        fabric = _FakeFabric(doctor_report=doctor_report)

        with pytest.raises(FabricPreflightError, match="No failing subsection was reported"):
            await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=fabric)

    async def test_dict_doctor_report_is_supported(self, fake_nemo_fabric: None) -> None:
        fabric = _FakeFabric(doctor_report={"status": "pass", "checks": []})

        result = await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=fabric)

        assert result.doctor_report == {"status": "pass", "checks": []}

    async def test_missing_fabric_dependency_reports_actionable_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_import_module = importlib.import_module

        def fake_import_module(name: str, package: str | None = None) -> Any:
            if name == "nemo_fabric":
                raise ImportError("No module named 'nemo_fabric'")
            return real_import_module(name, package)

        monkeypatch.delitem(sys.modules, "nemo_fabric", raising=False)
        monkeypatch.setattr(importlib, "import_module", fake_import_module)

        with pytest.raises(FabricValidationError, match="NeMo Fabric SDK is required"):
            await validate_fabric_config(object(), base_dir=Path("/tmp/agent"), fabric=_FakeFabric())
