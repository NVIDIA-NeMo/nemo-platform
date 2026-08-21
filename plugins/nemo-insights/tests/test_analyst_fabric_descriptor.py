# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The Insights analyst Fabric adapter descriptor and the config built for it.

These exercise the real Fabric planner rather than a hand-rolled schema copy,
so an invalid ``config.accepts`` key or an untranslatable harness kind fails
here instead of inside a running job.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nemo_fabric as fabric
import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.fabric.translator import translate_agent_config
from nemo_fabric_adapter_contract import models as contract
from nemo_insights_plugin import fabric_adapter
from nemo_insights_plugin.analyst.agent_config import ANALYST_ADAPTER_ID, build_analyst_agent_config

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = _PLUGIN_ROOT / "insights-analyst.fabric-adapter.json"


def _installed_descriptor() -> Path:
    import sys

    return Path(sys.prefix) / "share" / "nemo-fabric" / "adapters" / "insights-analyst" / DESCRIPTOR.name


def _built_config(**overrides: Any) -> dict[str, Any]:
    return build_analyst_agent_config(
        agent="demo-agent",
        workspace="default",
        default_model="default/test-default",
        fast_model="default/test-fast",
        **overrides,
    )


def _analyst_config(**overrides: Any) -> AgentConfig:
    return AgentConfig.model_validate(_built_config(**overrides))


def test_descriptor_declares_the_expected_adapter_id() -> None:
    descriptor = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))

    assert descriptor["adapter_id"] == ANALYST_ADAPTER_ID


def test_installed_descriptor_matches_the_source() -> None:
    """Shared-data is copied at install time, not symlinked into the venv.

    ``uv sync`` alone will not refresh it for an unchanged editable package;
    the descriptor only reaches Fabric after a reinstall.
    """
    installed = _installed_descriptor()
    if not installed.exists():
        pytest.skip(f"Adapter descriptor is not installed at {installed}")

    assert json.loads(installed.read_text(encoding="utf-8")) == json.loads(DESCRIPTOR.read_text(encoding="utf-8")), (
        "Stale installed descriptor. Refresh it with: uv sync --reinstall-package nemo-insights-plugin"
    )


def test_built_config_is_a_valid_agent_config() -> None:
    config = _analyst_config()

    assert config.name == "insights-analyst"
    assert config.default_harness == "insights"
    assert config.environment.provider == "local"


def test_built_config_translates_to_the_analyst_adapter() -> None:
    fabric_config = translate_agent_config(_analyst_config())

    assert fabric_config.harness is not None
    assert fabric_config.harness.adapter_id == ANALYST_ADAPTER_ID
    assert fabric_config.harness.settings["agent"] == "demo-agent"


def test_built_config_forwards_both_model_refs() -> None:
    """The analyst runs analysis on ``default`` and context summarization on ``fast``."""
    fabric_config = translate_agent_config(_analyst_config())

    assert set(fabric_config.models) == {"default", "fast"}
    assert fabric_config.models["default"].model == "default/test-default"
    assert fabric_config.models["fast"].model == "default/test-fast"


def test_analyst_adapter_resolves_the_forwarded_pair() -> None:
    """Guards the silent collapse: a missing ``fast`` falls back to ``default``."""
    fabric_config = translate_agent_config(_analyst_config())
    models = {
        key: contract.AgentModelConfig.from_mapping({"provider": "platform", "model": value.model})
        for key, value in fabric_config.models.items()
    }

    assert fabric_adapter._default_model_ref({}, models) == "default/test-default"
    assert fabric_adapter._fast_model_ref({}, models) == "default/test-fast"


def test_optional_read_settings_are_omitted_when_unset() -> None:
    settings = _built_config()["harnesses"]["insights"]["settings"]

    assert set(settings) == {"agent", "workspace"}


def test_optional_read_settings_are_carried_when_set() -> None:
    settings = _built_config(
        since=datetime(2026, 8, 1, tzinfo=timezone.utc),
        evaluation_id="eval-123",
        base_url="http://platform:8080",
        enable_observability=False,
    )["harnesses"]["insights"]["settings"]

    assert settings["since"] == "2026-08-01T00:00:00+00:00"
    assert settings["evaluation_id"] == "eval-123"
    assert settings["base_url"] == "http://platform:8080"
    assert settings["enable_observability"] is False


def test_fabric_plans_the_built_config(tmp_path: Path) -> None:
    """Fabric validates the adapter descriptor while planning; this is the real check."""
    if not _installed_descriptor().exists():
        pytest.skip("Adapter descriptor is not installed; Fabric cannot resolve it.")

    plan = fabric.Fabric().plan(translate_agent_config(_analyst_config()), base_dir=tmp_path)

    assert plan is not None
