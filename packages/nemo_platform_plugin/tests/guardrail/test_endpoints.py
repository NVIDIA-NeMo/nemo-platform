# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Guardrails service endpoint definitions and response types."""

from __future__ import annotations

import json
from typing import Any, get_origin

from nemo_platform_plugin.client.types import Paginated, PreparedRequest
from nemo_platform_plugin.entities.types import DeleteResponse
from nemo_platform_plugin.guardrail import endpoints
from nemo_platform_plugin.guardrail.types import (
    CreateGuardrailConfigRequest,
    GuardrailCheckRequest,
    GuardrailCheckResponse,
    GuardrailConfig,
    UpdateGuardrailConfigRequest,
)

CONFIGS = "/apis/guardrails/v2/workspaces/{workspace}/configs"


def _json_content(prepared: PreparedRequest[Any]) -> Any:
    assert isinstance(prepared.content, bytes)
    return json.loads(prepared.content)


def test_get_guardrail_config() -> None:
    prepared = endpoints.get_guardrail_config(workspace="default", name="safety")

    assert isinstance(prepared, PreparedRequest)
    assert prepared.method == "GET"
    assert prepared.path_template == f"{CONFIGS}/{{name}}"
    assert prepared.path_params == {"workspace": "default", "name": "safety"}
    assert prepared.content is None
    assert prepared.response_type is GuardrailConfig


def test_get_guardrail_config_workspace_optional() -> None:
    prepared = endpoints.get_guardrail_config(name="safety")

    assert prepared.path_params == {"name": "safety"}


def test_list_guardrail_configs() -> None:
    prepared = endpoints.list_guardrail_configs(workspace="default")

    assert prepared.method == "GET"
    assert prepared.path_template == CONFIGS
    assert prepared.path_params == {"workspace": "default"}
    assert prepared.query_params is None
    assert get_origin(prepared.response_type) is Paginated


def test_list_guardrail_configs_with_query_params() -> None:
    prepared = endpoints.list_guardrail_configs(
        workspace="default", query_params={"page": 2, "page_size": 5, "sort": "-name", "filter": '{"name": "x"}'}
    )

    assert prepared.query_params == {"page": 2, "page_size": 5, "sort": "-name", "filter": '{"name": "x"}'}


def test_create_guardrail_config() -> None:
    body = CreateGuardrailConfigRequest(name="safety", description="d", data={"rails": {}})
    prepared = endpoints.create_guardrail_config(workspace="default", body=body)

    assert prepared.method == "POST"
    assert prepared.path_template == CONFIGS
    assert prepared.path_params == {"workspace": "default"}
    assert prepared.content_type == "application/json"
    assert _json_content(prepared) == {"name": "safety", "description": "d", "data": {"rails": {}}}
    assert prepared.response_type is GuardrailConfig


def test_create_guardrail_config_only_sends_set_fields() -> None:
    prepared = endpoints.create_guardrail_config(workspace="default", body=CreateGuardrailConfigRequest(name="s"))

    assert _json_content(prepared) == {"name": "s"}


def test_create_guardrail_config_exist_ok_builds_retrieve_request() -> None:
    body = CreateGuardrailConfigRequest(name="safety")
    prepared = endpoints.create_guardrail_config(workspace="default", body=body, exist_ok=True)

    assert prepared.client_options == {"exist_ok": True}
    assert prepared.on_conflict_get is not None
    assert prepared.on_conflict_get.method == "GET"
    assert prepared.on_conflict_get.path_template == f"{CONFIGS}/{{name}}"
    assert prepared.on_conflict_get.path_params == {"workspace": "default", "name": "safety"}


def test_update_guardrail_config() -> None:
    body = UpdateGuardrailConfigRequest(description="changed")
    prepared = endpoints.update_guardrail_config(workspace="default", name="safety", body=body)

    assert prepared.method == "PATCH"
    assert prepared.path_template == f"{CONFIGS}/{{name}}"
    assert prepared.path_params == {"workspace": "default", "name": "safety"}
    assert _json_content(prepared) == {"description": "changed"}
    assert prepared.response_type is GuardrailConfig


def test_update_guardrail_config_empty_body() -> None:
    prepared = endpoints.update_guardrail_config(
        workspace="default", name="safety", body=UpdateGuardrailConfigRequest()
    )

    assert _json_content(prepared) == {}


def test_delete_guardrail_config() -> None:
    prepared = endpoints.delete_guardrail_config(workspace="default", name="safety")

    assert prepared.method == "DELETE"
    assert prepared.path_template == f"{CONFIGS}/{{name}}"
    assert prepared.path_params == {"workspace": "default", "name": "safety"}
    assert prepared.content is None
    assert prepared.response_type is DeleteResponse


def test_check_guardrail() -> None:
    body = GuardrailCheckRequest(
        model="m", messages=[{"role": "user", "content": "hi"}], guardrails={"config_id": "default/safety"}
    )
    prepared = endpoints.check_guardrail(workspace="default", body=body)

    assert prepared.method == "POST"
    assert prepared.path_template == "/apis/guardrails/v2/workspaces/{workspace}/checks"
    assert prepared.path_params == {"workspace": "default"}
    assert _json_content(prepared) == {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "guardrails": {"config_id": "default/safety"},
    }
    assert prepared.response_type is GuardrailCheckResponse


def test_check_guardrail_passes_through_extra_sampling_params() -> None:
    body = GuardrailCheckRequest.model_validate({"model": "m", "messages": [], "seed": 7, "stop": ["\n"]})
    prepared = endpoints.check_guardrail(workspace="default", body=body)

    assert _json_content(prepared) == {"model": "m", "messages": [], "seed": 7, "stop": ["\n"]}


def test_guardrail_config_accepts_null_data() -> None:
    """The create route returns ``data: null`` for a config created without data."""
    config = GuardrailConfig.model_validate(
        {
            "name": "safety",
            "workspace": "default",
            "project": None,
            "description": None,
            "data": None,
            "id": "guardrail-config-1",
            "created_at": "2026-01-01T00:00:00",
            "created_by": "service:guardrails",
            "updated_at": "2026-01-01T00:00:00",
            "updated_by": "service:guardrails",
            "entity_id": "guardrail-config-1",
            "parent": None,
            "db_version": 1,
        }
    )

    assert config.data is None
    assert config.name == "safety"


def test_guardrail_config_accepts_omitted_data() -> None:
    """GET/list use ``response_model_exclude_none`` and omit ``data`` entirely."""
    config = GuardrailConfig.model_validate(
        {
            "name": "safety",
            "workspace": "default",
            "id": "guardrail-config-1",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
    )

    assert config.data is None
