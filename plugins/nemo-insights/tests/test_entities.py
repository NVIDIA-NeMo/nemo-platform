# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for entity instantiation, defaults, and name composition."""

from __future__ import annotations

import pytest
from nemo_insights_plugin.entities import (
    AgentRegistration,
    CloudAgentType,
    Insight,
    InsightStatus,
    InsightTrace,
    InsightTraceRole,
    compose_insight_trace_name,
)
from pydantic import ValidationError


class TestAgentRegistration:
    def test_minimal_construction(self) -> None:
        reg = AgentRegistration(name="my-agent", workspace="default")
        assert reg.name == "my-agent"
        assert reg.workspace == "default"
        assert reg.description == ""
        assert reg.repo_url == ""
        assert reg.agent_description_path == "AGENT_DESCRIPTION.md"
        assert reg.agent_description_content == ""
        assert reg.agent_description_uploaded_at is None
        assert reg.eval_command == ""
        assert reg.cloud_agent_type is None
        assert reg.cloud_agent_config == {}

    def test_cloud_agent_type_accepts_known_values(self) -> None:
        reg = AgentRegistration(name="x", workspace="default", cloud_agent_type=CloudAgentType.CLAUDE_CODE)
        assert reg.cloud_agent_type == CloudAgentType.CLAUDE_CODE

    def test_entity_type_is_agent_registration(self) -> None:
        assert AgentRegistration.__entity_type__ == "agent_registration"


class TestInsight:
    def test_minimal_construction(self) -> None:
        ins = Insight(name="x", workspace="default", agent="my-agent", description="d")
        assert ins.agent == "my-agent"
        assert ins.description == "d"
        assert ins.hypothesis == ""
        assert ins.status == InsightStatus.OPEN
        assert ins.impact_estimate is None
        assert ins.eval_dataset_row_refs == []
        assert ins.experiment_refs == []

    def test_status_enum_values(self) -> None:
        # POR specifies open, in_progress, resolved, deleted — no cancelled.
        assert {s.value for s in InsightStatus} == {"open", "in_progress", "resolved", "deleted"}

    def test_missing_required_fields_raise(self) -> None:
        with pytest.raises(ValidationError):
            Insight.model_validate({"name": "x", "workspace": "default"})

    def test_entity_type_is_insight(self) -> None:
        assert Insight.__entity_type__ == "insight"


class TestInsightTrace:
    def test_minimal_construction(self) -> None:
        link = InsightTrace(
            name="my-insight--trace-abc",
            workspace="default",
            insight="my-insight",
            trace_id="trace-abc",
        )
        assert link.insight == "my-insight"
        assert link.trace_id == "trace-abc"
        assert link.role == InsightTraceRole.EVIDENCE
        assert link.note == ""

    def test_compose_name(self) -> None:
        assert compose_insight_trace_name("my-insight", "trace-abc") == "my-insight--trace-abc"

    def test_role_enum_values(self) -> None:
        assert {r.value for r in InsightTraceRole} == {"evidence", "regression_test_candidate"}

    def test_entity_type_is_insight_trace(self) -> None:
        assert InsightTrace.__entity_type__ == "insight_trace"
