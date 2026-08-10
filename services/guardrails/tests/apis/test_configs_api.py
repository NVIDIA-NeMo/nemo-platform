# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Guardrails config API endpoints."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from nmp.common.entities import EntityNotFoundError
from nmp.common.service.dependencies import get_entity_client
from nmp.guardrails.entities import GuardrailConfig


class TestGuardrailConfigsAPI:
    """Tests for guardrail config CRUD operations."""

    def test_list_guardrail_configs(self, client: TestClient):
        """Test listing guardrail configs."""
        response = client.get("/apis/guardrails/v2/workspaces/default/configs")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert "sort" in data

    def test_list_sort_param_is_reflected(self, client: TestClient):
        """The sort query param value is included in the response."""
        response = client.get("/apis/guardrails/v2/workspaces/default/configs?sort=-created_at")
        assert response.status_code == 200
        assert response.json()["sort"] == "-created_at"

    def test_create_config(self, client: TestClient):
        """Test creating a guardrail config."""
        response = client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={
                "name": "test-config",
            },
        )
        assert response.status_code == 201
        json_response = response.json()
        assert "created_at" in json_response
        assert "updated_at" in json_response
        assert json_response["name"] == "test-config"
        assert json_response["workspace"] == "default"  # namespace comes from workspace in URL

    def test_get_guardrail_config(self, client: TestClient):
        """Test getting a guardrail config."""
        # First create a config
        client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={
                "name": "get-test-config",
            },
        )

        # Then get it
        response = client.get("/apis/guardrails/v2/workspaces/default/configs/get-test-config")
        assert response.status_code == 200
        json_response = response.json()
        assert json_response["name"] == "get-test-config"
        assert json_response["workspace"] == "default"  # namespace comes from workspace in URL

    def test_update_config(self, client: TestClient):
        """Test updating a guardrail config."""
        # First create a config
        client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={
                "name": "update-test-config",
                "description": "Original description",
            },
        )

        # Then update it
        response = client.patch(
            "/apis/guardrails/v2/workspaces/default/configs/update-test-config",
            json={"description": "Updated description"},
        )
        assert response.status_code == 200
        json_response = response.json()
        assert json_response["description"] == "Updated description"

    def test_delete_config(self, client: TestClient):
        """Test deleting a guardrail config."""
        # First create a config
        client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={
                "name": "delete-test-config",
            },
        )

        # Then delete it
        response = client.delete("/apis/guardrails/v2/workspaces/default/configs/delete-test-config")
        assert response.status_code == 200
        assert response.json()["message"] == "Resource deleted successfully."

    def test_delete_config_not_found_during_delete(self, client: TestClient):
        """Test a config deleted after lookup returns 404."""
        entities_client = AsyncMock()
        entities_client.get.return_value = GuardrailConfig(name="delete-race-config", workspace="default")
        entities_client.delete.side_effect = EntityNotFoundError("not found")
        dependency_overrides = getattr(client.app, "dependency_overrides")
        dependency_overrides[get_entity_client] = lambda: entities_client
        try:
            response = client.delete("/apis/guardrails/v2/workspaces/default/configs/delete-race-config")
        finally:
            dependency_overrides.pop(get_entity_client, None)

        assert response.status_code == 404
        assert response.json()["detail"] == "Guardrail config not found."

    def test_get_config_not_found(self, client: TestClient):
        """Test getting a non-existent config returns 404."""
        response = client.get("/apis/guardrails/v2/workspaces/default/configs/nonexistent-config")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_config_not_found(self, client: TestClient):
        """Test updating a non-existent config returns 404."""
        response = client.patch(
            "/apis/guardrails/v2/workspaces/default/configs/nonexistent-config",
            json={"description": "Updated description"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.skip(reason="Test requires custom workspace which is not auto-created in test harness")
    def test_create_config_with_custom_namespace(self, client: TestClient):
        """Test creating a config with a custom namespace via workspace in URL."""
        response = client.post(
            "/apis/guardrails/v2/workspaces/nvidia/configs",  # workspace determines namespace
            json={
                "name": "custom-ns-config",
                "description": "Config in custom namespace",
            },
        )
        assert response.status_code == 201
        json_response = response.json()
        assert json_response["name"] == "custom-ns-config"
        assert json_response["workspace"] == "nvidia"  # namespace comes from workspace in URL

    def test_create_config_with_data(self, client: TestClient):
        """Test creating a config with inline data."""
        response = client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={
                "name": "config-with-data",
                "description": "Config with data",
                "data": {
                    "models": [{"type": "main", "engine": "nim", "model": "meta/llama-3.1-8b-instruct"}],
                    "instructions": [{"type": "general", "content": "You are a helpful AI assistant."}],
                },
            },
        )
        assert response.status_code == 201
        json_response = response.json()
        assert json_response["data"] is not None
        assert "models" in json_response["data"]

    def test_create_config_validation_error(self, client: TestClient):
        """Test that invalid config data returns 422 with a user-friendly error message."""
        response = client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={
                "name": "invalid-config",
                "data": {
                    "rails": {"input": {"flows": ["self check input"]}},
                },
            },
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Validation error at data: Missing a `self_check_input` prompt template, which is required for the `self check input` rail."
        }

    def test_update_config_validation_error(self, client: TestClient):
        """Test that updating a config with invalid data returns 422 with a user-friendly error message."""
        # First, create a valid config
        client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={
                "name": "config-to-update",
                "data": {
                    "rails": {"input": {"flows": ["self check input"]}},
                    "prompts": [
                        {
                            "task": "self_check_input",
                            "content": "Check if the input is safe.",
                        }
                    ],
                },
            },
        )

        # Update config with invalid data
        response = client.patch(
            "/apis/guardrails/v2/workspaces/default/configs/config-to-update",
            json={
                "data": {
                    "rails": {"input": {"flows": ["self check input"]}},
                },
            },
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Validation error at data: Missing a `self_check_input` prompt template, which is required for the `self check input` rail."
        }


class TestGuardrailConfigsFilter:
    """Tests for filtering the guardrail configs list endpoint."""

    @staticmethod
    def _seed_config(client: TestClient, name: str, description: str = "") -> None:
        response = client.post(
            "/apis/guardrails/v2/workspaces/default/configs",
            json={"name": name, "description": description} if description else {"name": name},
        )
        assert response.status_code == 201

    def test_filter_by_name_exact_match(self, client: TestClient):
        """filter[name]=<value> returns only configs with that exact name."""
        self._seed_config(client, "filter-alpha")
        self._seed_config(client, "filter-beta")

        response = client.get("/apis/guardrails/v2/workspaces/default/configs?filter[name]=filter-alpha")
        assert response.status_code == 200
        names = [c["name"] for c in response.json()["data"]]
        assert "filter-alpha" in names
        assert "filter-beta" not in names

    def test_filter_by_name_substring(self, client: TestClient):
        """filter[name][$like] returns configs whose name contains the substring."""
        self._seed_config(client, "substr-apple")
        self._seed_config(client, "substr-apricot")
        self._seed_config(client, "substr-banana")

        response = client.get("/apis/guardrails/v2/workspaces/default/configs?filter[name][%24like]=ap")
        assert response.status_code == 200
        names = {c["name"] for c in response.json()["data"]}
        assert {"substr-apple", "substr-apricot"}.issubset(names)
        assert "substr-banana" not in names

    def test_filter_by_description(self, client: TestClient):
        """filter[description]=<value> filters by description field."""
        self._seed_config(client, "desc-one", description="content-safety rails")
        self._seed_config(client, "desc-two", description="pii detection rails")

        response = client.get("/apis/guardrails/v2/workspaces/default/configs?filter[description]=content-safety rails")
        assert response.status_code == 200
        names = [c["name"] for c in response.json()["data"]]
        assert "desc-one" in names
        assert "desc-two" not in names

    def test_filter_rejects_unknown_field(self, client: TestClient):
        """Filter validation rejects fields not declared on GuardrailConfigFilter."""
        response = client.get("/apis/guardrails/v2/workspaces/default/configs?filter[unknown_field]=x")
        assert response.status_code == 400
