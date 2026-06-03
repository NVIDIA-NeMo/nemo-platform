# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Agent/AgentDeployment entity definitions and API schema models.

Entity tests live here alongside schema tests because both cover pure Pydantic
model behaviour — no network, no entity store required.

Entity classes: ``Agent``, ``AgentDeployment``  → ``nemo_agents_plugin.entities``
Request schemas: ``CreateAgentRequest``, ``CreateDeploymentRequest``
                                               → ``nemo_agents_plugin.schema``
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from nemo_agents_plugin.entities import (
    Agent,
    AgentDeployment,
    agent_spec_file_ref,
    agent_spec_fileset_name,
    agent_spec_local_path,
)
from nemo_agents_plugin.schema import (
    CreateAgentRequest,
    CreateDeploymentRequest,
)
from pydantic import ValidationError

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Entity: Agent
# ---------------------------------------------------------------------------


class TestAgentEntity:
    def test_entity_type(self) -> None:
        assert Agent.__entity_type__ == "agent"

    def test_defaults(self) -> None:
        a = Agent(name="calc", workspace="default")
        assert a.name == "calc"
        assert a.workspace == "default"
        assert a.description == ""
        assert a.config == {}
        assert a.config_format == "nat-workflow-v1"

    def test_config_stored(self) -> None:
        config = {"llms": {"my_llm": {"_type": "nim", "model_name": "llama"}}}
        a = Agent(name="calc", workspace="default", config=config)
        assert a.config["llms"]["my_llm"]["_type"] == "nim"

    def test_data_fields_include_domain_fields(self) -> None:
        a = Agent(
            name="calc",
            workspace="default",
            description="A calculator",
            config={"key": "value"},
            config_format="nat-workflow-v1",
        )
        data = a._get_data_fields()
        assert "description" in data
        assert "config" in data
        assert "config_format" in data

    def test_data_fields_exclude_base_fields(self) -> None:
        a = Agent(name="calc", workspace="default")
        data = a._get_data_fields()
        assert "name" not in data
        assert "workspace" not in data

    def test_description_optional(self) -> None:
        a = Agent(name="x", workspace="w", description="hello")
        assert a.description == "hello"

    def test_id_and_created_at_accessible_after_persistence(self) -> None:
        """Entity computed fields include id and created_at for API serialisation."""
        a = Agent(name="calc", workspace="default")
        a._id = "agent-id-123"
        a._created_at = NOW
        assert a.id == "agent-id-123"
        assert a.created_at == NOW

    def test_entity_serialises_with_computed_fields(self) -> None:
        """model_dump() includes id, created_at — these appear in API responses."""
        a = Agent(name="calc", workspace="default", config={"k": "v"})
        a._id = "abc"
        a._created_at = NOW
        data = a.model_dump()
        assert data["id"] == "abc"
        assert data["name"] == "calc"
        assert data["config"] == {"k": "v"}


# ---------------------------------------------------------------------------
# Entity: AgentDeployment
# ---------------------------------------------------------------------------


class TestAgentDeploymentEntity:
    def test_entity_type(self) -> None:
        assert AgentDeployment.__entity_type__ == "agent_deployment"

    def test_defaults(self) -> None:
        d = AgentDeployment(name="dep", workspace="default")
        assert d.agent == ""
        assert d.status == "pending"
        assert d.endpoint == ""
        assert d.port == 0
        assert d.pid == 0
        assert d.error == ""

    def test_status_transitions(self) -> None:
        d = AgentDeployment(name="dep", workspace="default", agent="calc", status="pending")
        d.status = "starting"
        assert d.status == "starting"
        d.status = "running"
        assert d.status == "running"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentDeployment(name="dep", workspace="default", status="unknown")

    def test_data_fields_include_deployment_fields(self) -> None:
        d = AgentDeployment(
            name="dep",
            workspace="default",
            agent="calc",
            status="running",
            endpoint="http://localhost:9001",
            port=9001,
            pid=12345,
        )
        data = d._get_data_fields()
        assert "agent" in data
        assert "status" in data
        assert "endpoint" in data
        assert "port" in data
        assert "pid" in data

    def test_data_fields_exclude_base_fields(self) -> None:
        d = AgentDeployment(name="dep", workspace="default")
        data = d._get_data_fields()
        assert "name" not in data
        assert "workspace" not in data

    def test_entity_serialises_as_api_response(self) -> None:
        """model_dump() produces the full API response shape including base fields."""
        d = AgentDeployment(
            name="dep",
            workspace="default",
            agent="calc",
            status="running",
        )
        d._id = "dep-id"
        d._created_at = NOW
        data = d.model_dump()
        assert data["id"] == "dep-id"
        assert data["name"] == "dep"
        assert data["agent"] == "calc"
        assert data["status"] == "running"


# ---------------------------------------------------------------------------
# API schema: CreateAgentRequest
# ---------------------------------------------------------------------------


class TestCreateAgentRequest:
    def test_required_fields(self) -> None:
        req = CreateAgentRequest(name="calc", config={"llms": {}})
        assert req.name == "calc"
        assert req.config == {"llms": {}}
        assert req.description == ""
        assert req.config_format == "nat-workflow-v1"

    def test_missing_config_raises(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentRequest.model_validate({"name": "calc"})

    def test_custom_format(self) -> None:
        req = CreateAgentRequest(name="x", config={}, config_format="custom-v2")
        assert req.config_format == "custom-v2"


# ---------------------------------------------------------------------------
# Canonical spec-location helpers
# ---------------------------------------------------------------------------


class TestSpecLocationConvention:
    def test_spec_location_convention(self) -> None:
        assert agent_spec_fileset_name("checkout-bot") == "checkout-bot-spec"
        ref = agent_spec_file_ref("default", "checkout-bot")
        assert str(ref) == "default/checkout-bot-spec#AGENT-SPEC.md"
        assert agent_spec_local_path("checkout-bot").as_posix() == "agents/checkout-bot-spec/AGENT-SPEC.md"


# ---------------------------------------------------------------------------
# API schema: CreateDeploymentRequest
# ---------------------------------------------------------------------------


class TestCreateDeploymentRequest:
    def test_required_agent(self) -> None:
        req = CreateDeploymentRequest(agent="calc")
        assert req.agent == "calc"
        assert req.name is None

    def test_optional_name(self) -> None:
        req = CreateDeploymentRequest(agent="calc", name="calc-abc1")
        assert req.name == "calc-abc1"
